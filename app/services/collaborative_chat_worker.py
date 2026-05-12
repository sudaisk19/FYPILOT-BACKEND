"""
Background workers for collaborative chat LLM turns.

Jobs are stored in Redis list `fyp:chat:jobs` when Redis is available; otherwise
an in-process asyncio.Queue is used (single-instance deployments).

Cross-instance serialization for the same room uses Redis SET NX `fyp:chat:busy:{room_id}`.
In-process fallback uses an asyncio.Lock per room_id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional
from uuid import UUID

from app.core.config import settings
from app.db import AsyncSessionLocal
from app.db.mongo import mongo_db
from app.repositories.chat_llm_turn_repository import chat_llm_turn_repo
from app.repositories.chat_session_repository import chat_session_repo
from app.repositories.group_document_repository import group_document_repo
from app.services.chat_sse_hub import publish, sse_stream_error, sse_stream_status
from app.services.html_plaintext import html_to_plaintext, tip_tap_html_from_content
from app.services.llm import stream_llm

logger = logging.getLogger(__name__)

CHAT_JOBS_KEY = "fyp:chat:jobs"
CHAT_BUSY_PREFIX = "fyp:chat:busy:"

_local_queue: Optional[asyncio.Queue[str]] = None
_room_async_locks: Dict[str, asyncio.Lock] = {}
_worker_tasks: list[asyncio.Task] = []


def _local_jobs() -> asyncio.Queue[str]:
    global _local_queue
    if _local_queue is None:
        _local_queue = asyncio.Queue()
    return _local_queue


def _room_lock(room_id: str) -> asyncio.Lock:
    if room_id not in _room_async_locks:
        _room_async_locks[room_id] = asyncio.Lock()
    return _room_async_locks[room_id]


async def enqueue_chat_job(job: Dict[str, Any]) -> None:
    raw = json.dumps(job, separators=(",", ":"))
    from app.services.cache import cache

    if cache.is_available:
        await cache.client.rpush(CHAT_JOBS_KEY, raw)
    else:
        await _local_jobs().put(raw)


async def rate_limit_allow(user_id: str, room_id: str) -> bool:
    from app.services.cache import cache

    if not cache.is_available:
        return True
    try:
        client = cache.client
        ukey = f"fyp:chat:rl:user:{user_id}"
        rkey = f"fyp:chat:rl:room:{room_id}"
        nu = await client.incr(ukey)
        if nu == 1:
            await client.expire(ukey, 60)
        nr = await client.incr(rkey)
        if nr == 1:
            await client.expire(rkey, 60)
        if nu > settings.chat_rate_limit_per_minute_user:
            return False
        if nr > settings.chat_rate_limit_per_minute_room:
            return False
        return True
    except Exception as e:
        logger.debug("chat rate limit check failed open: %s", e)
        return True


async def _run_turn(job: Dict[str, Any]) -> None:
    room_id = job["room_id"]
    request_id = job["request_id"]
    user_id = job.get("user_id")
    user_message_id = job.get("user_message_id")
    model_choice = job.get("model") or "gpt-4o"
    active_document_id: Optional[str] = job.get("active_document_id")
    t0 = time.perf_counter()
    token_count = 0

    doc_context = None
    doc_type_str = None
    leading_document_context: Optional[str] = None

    if active_document_id:
        try:
            doc_uuid = UUID(active_document_id.strip())
        except ValueError:
            logger.debug(
                "active_document_id invalid UUID, skipping document context: %s",
                active_document_id,
            )
        else:
            try:
                async with AsyncSessionLocal() as pg:
                    doc = await group_document_repo.get_by_id(pg, doc_uuid)
                    if not doc:
                        logger.debug(
                            "active_document_id provided but document not found: %s",
                            active_document_id,
                        )
                    else:
                        doc_type_str = doc.doc_type.value if doc.doc_type else None
                        doc_context = {
                            "active_document_id": active_document_id,
                            "version_number": doc.lock_version,
                        }
                        html_raw = tip_tap_html_from_content(doc.content)
                        if not html_raw:
                            logger.debug(
                                "active_document_id provided but content has no "
                                "usable html: %s",
                                active_document_id,
                            )
                        else:
                            leading_document_context = html_to_plaintext(html_raw)
            except Exception as e:
                logger.warning(
                    "active_document_id document lookup failed, skipping context: %s",
                    e,
                )

    await publish(room_id, sse_stream_status(request_id, "thinking"))

    recent = await chat_session_repo.get_recent_messages_for_context(
        mongo_db,
        room_id,
        n=settings.chat_context_message_limit,
    )
    history = []
    for msg in recent:
        role = "assistant" if msg["sender_type"] == "llm" else "user"
        history.append({"role": role, "content": msg["content"]})

    full_parts: list[str] = []
    seq = 0
    streaming_started = False

    try:
        async for token_chunk in stream_llm(
            history=history,
            document_content=None,
            model_choice=model_choice,
            doc_type=doc_type_str,
            leading_document_context=leading_document_context,
        ):
            if not streaming_started:
                streaming_started = True
                await publish(room_id, sse_stream_status(request_id, "streaming"))
            seq += 1
            token_count += len(token_chunk) // 4 + 1
            full_parts.append(token_chunk)
            await publish(
                room_id,
                {
                    "type": "chat.stream.token",
                    "request_id": request_id,
                    "token": token_chunk,
                    "seq": seq,
                },
            )

        full_reply = "".join(full_parts)
        assistant_mid = await chat_session_repo.save_message(
            mongo_db,
            chat_session_id=room_id,
            sender_id="llm",
            sender_type="llm",
            content=full_reply,
            doc_context=doc_context,
            sender_name="Assistant",
            request_id=request_id,
            metadata={"model": model_choice, "request_id": request_id},
        )

        latency_ms = int((time.perf_counter() - t0) * 1000)

        await publish(
            room_id,
            {
                "type": "chat.stream.end",
                "request_id": request_id,
                "assistant_message_id": assistant_mid,
                "reply_length": len(full_reply),
            },
        )
        await publish(room_id, sse_stream_status(request_id, "complete"))

        async with AsyncSessionLocal() as pg:
            await chat_llm_turn_repo.record_turn(
                pg,
                room_id=room_id,
                request_id=request_id,
                user_id=UUID(user_id) if user_id else None,
                user_message_id=user_message_id,
                model=model_choice,
                latency_ms=latency_ms,
                token_count_estimate=token_count,
                status="done",
            )
            await pg.commit()

        logger.info(
            "chat_llm_turn_done room_id=%s request_id=%s user_id=%s model=%s "
            "latency_ms=%s token_est=%s",
            room_id,
            request_id,
            user_id,
            model_choice,
            latency_ms,
            token_count,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.exception(
            "chat_llm_turn_error room_id=%s request_id=%s", room_id, request_id
        )
        await publish(room_id, sse_stream_error(request_id, str(exc)))
        await publish(room_id, sse_stream_status(request_id, "error"))
        try:
            async with AsyncSessionLocal() as pg:
                await chat_llm_turn_repo.record_turn(
                    pg,
                    room_id=room_id,
                    request_id=request_id,
                    user_id=UUID(user_id) if user_id else None,
                    user_message_id=user_message_id,
                    model=model_choice,
                    latency_ms=latency_ms,
                    token_count_estimate=token_count,
                    status="error",
                    error_detail=str(exc)[:2000],
                )
                await pg.commit()
        except Exception as db_exc:
            logger.warning("chat_llm_turn audit insert failed: %s", db_exc)


async def _process_job_raw(job_raw: str) -> None:
    job = json.loads(job_raw)
    room_id = job["room_id"]
    from app.services.cache import cache

    if cache.is_available:
        key = f"{CHAT_BUSY_PREFIX}{room_id}"
        ok = await cache.client.set(key, job["request_id"], nx=True, ex=600)
        if not ok:
            await asyncio.sleep(0.05)
            await cache.client.rpush(CHAT_JOBS_KEY, job_raw)
            return
        try:
            await _run_turn(job)
        finally:
            await cache.client.delete(key)
    else:
        async with _room_lock(room_id):
            await _run_turn(job)


async def _worker_loop(worker_id: int) -> None:
    from app.services.cache import cache

    logger.info("Collaborative chat worker %s started", worker_id)
    while True:
        try:
            if cache.is_available:
                item = await cache.client.brpop(CHAT_JOBS_KEY, timeout=5)
                if item is None:
                    continue
                _, raw = item
                await _process_job_raw(raw)
            else:
                raw = await _local_jobs().get()
                await _process_job_raw(raw)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("chat worker %s loop error: %s", worker_id, e)
            await asyncio.sleep(1.0)


def start_chat_workers() -> None:
    global _worker_tasks
    if _worker_tasks:
        return
    n = max(1, settings.chat_worker_tasks)
    for i in range(n):
        _worker_tasks.append(asyncio.create_task(_worker_loop(i)))
