"""
SSE fan-out for collaborative workspace chat.

- In-process: each SSE client registers an asyncio.Queue per room_id.
- Cross-worker: events are published on Redis channel fyp:chat:sse:{room_id};
  a subscriber pushes them into local queues.

SSE payload format: one JSON object per event as `data: {...}\\n\\n`.
Heartbeats are sent by the endpoint (`: heartbeat\\n\\n`), not Redis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


def sse_stream_status(request_id: str, phase: str) -> Dict[str, Any]:
    """Unified chat.stream.status payload; `status` mirrors `phase` for clients that expect either key."""
    return {
        "type": "chat.stream.status",
        "request_id": request_id,
        "phase": phase,
        "status": phase,
        "timestamp": time.time(),
    }


def sse_stream_error(request_id: str, detail: str) -> Dict[str, Any]:
    """Unified chat.stream.error payload; `error` mirrors `detail`."""
    return {
        "type": "chat.stream.error",
        "request_id": request_id,
        "detail": detail,
        "error": detail,
        "timestamp": time.time(),
    }


REDIS_CHANNEL_PREFIX = "fyp:chat:sse:"

# room_id -> set of asyncio.Queue[dict]
_queues: Dict[str, Set[asyncio.Queue]] = {}
_lock = asyncio.Lock()

_subscriber_task: Optional[asyncio.Task] = None


def format_sse_data(obj: Dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


async def register(room_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    async with _lock:
        if room_id not in _queues:
            _queues[room_id] = set()
        _queues[room_id].add(q)
    return q


async def unregister(room_id: str, q: asyncio.Queue) -> None:
    async with _lock:
        subs = _queues.get(room_id)
        if not subs:
            return
        subs.discard(q)
        if not subs:
            _queues.pop(room_id, None)


async def broadcast_local(room_id: str, event: Dict[str, Any]) -> None:
    async with _lock:
        subs = list(_queues.get(room_id, set()))
    for q in subs:
        try:
            q.put_nowait(event)
        except Exception as e:
            logger.debug("SSE queue push failed: %s", e)


async def publish(room_id: str, event: Dict[str, Any]) -> None:
    """Deliver to local SSE clients and Redis subscribers on other workers."""
    await broadcast_local(room_id, event)
    from app.services.cache import cache

    if not cache.is_available:
        return
    try:
        ch = f"{REDIS_CHANNEL_PREFIX}{room_id}"
        await cache.client.publish(ch, json.dumps(event, ensure_ascii=False))
    except Exception as e:
        logger.debug("Redis chat SSE publish failed: %s", e)


async def _redis_listener_loop() -> None:
    from redis.asyncio import Redis

    from app.core.config import settings

    r = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    pubsub = r.pubsub()
    try:
        await pubsub.psubscribe(f"{REDIS_CHANNEL_PREFIX}*")
        logger.info("Chat SSE Redis subscriber on %s*", REDIS_CHANNEL_PREFIX)
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue
            ch = message["channel"]
            raw = message["data"]
            if not ch.startswith(REDIS_CHANNEL_PREFIX):
                continue
            room_id = ch[len(REDIS_CHANNEL_PREFIX) :]
            try:
                evt = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await broadcast_local(room_id, evt)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("Chat SSE Redis listener stopped: %s", e)
    finally:
        try:
            await pubsub.punsubscribe()
            await pubsub.close()
        except Exception:
            pass
        try:
            await r.close()
        except Exception:
            pass


def start_chat_sse_redis_subscriber() -> None:
    global _subscriber_task
    if _subscriber_task is not None and not _subscriber_task.done():
        return
    from app.services.cache import cache

    if not cache.is_available:
        return
    _subscriber_task = asyncio.create_task(_redis_listener_loop())
