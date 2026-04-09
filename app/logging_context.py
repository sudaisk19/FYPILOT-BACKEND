from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional

request_id_context: ContextVar[Optional[str]] = ContextVar(
    "request_id_context", default=None
)
user_id_context: ContextVar[Optional[str]] = ContextVar("user_id_context", default=None)
client_ip_context: ContextVar[Optional[str]] = ContextVar(
    "client_ip_context", default=None
)


def set_logging_context(
    *,
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> tuple[Token[Optional[str]], Token[Optional[str]], Token[Optional[str]]]:
    request_id_token = request_id_context.set(request_id)
    user_id_token = user_id_context.set(user_id)
    client_ip_token = client_ip_context.set(client_ip)
    return request_id_token, user_id_token, client_ip_token


def reset_logging_context(
    tokens: tuple[Token[Optional[str]], Token[Optional[str]], Token[Optional[str]]],
) -> None:
    request_id_context.reset(tokens[0])
    user_id_context.reset(tokens[1])
    client_ip_context.reset(tokens[2])


def get_logging_context() -> dict[str, Optional[str]]:
    return {
        "request_id": request_id_context.get(),
        "user_id": user_id_context.get(),
        "client_ip": client_ip_context.get(),
    }
