from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth.utils import decode_access_token
from app.logging_context import reset_logging_context, set_logging_context

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        request_id = str(uuid4())
        client_ip = self._get_client_ip(request)
        user_id = self._get_user_id(request)

        request.state.request_id = request_id
        request.state.client_ip = client_ip
        if user_id is not None:
            request.state.user_id = user_id

        context_tokens = set_logging_context(
            request_id=request_id, user_id=user_id, client_ip=client_ip
        )

        status_code = 500
        start_time = perf_counter()

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("utf-8")))
                message = dict(message)
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = round((perf_counter() - start_time) * 1000, 2)
            final_user_id = getattr(request.state, "user_id", None) or user_id
            logger.info(
                "request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                    "user_id": (
                        str(final_user_id) if final_user_id is not None else None
                    ),
                    "client_ip": client_ip,
                },
            )
            reset_logging_context(context_tokens)

    def _get_client_ip(self, request: Request) -> str | None:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip() or None

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip() or None

        if request.client is not None:
            return request.client.host
        return None

    def _get_user_id(self, request: Request) -> str | None:
        authorization = request.headers.get("authorization")
        if not authorization:
            return None

        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None

        try:
            claims = decode_access_token(token)
            user_id = claims.get("sub")
            return str(user_id) if user_id else None
        except Exception:
            return None
