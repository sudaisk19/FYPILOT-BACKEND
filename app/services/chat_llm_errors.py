"""
Map LLM / HTTP provider failures to short client-facing messages.

Collaborative chat SSE and WebSocket surfaces use these strings so UIs can
show actionable text instead of raw httpx tracebacks.
"""

from __future__ import annotations

from typing import Optional, Tuple

import httpx


def format_chat_stream_llm_error(exc: BaseException) -> Tuple[str, Optional[str]]:
    """
    Returns (detail_for_client, optional_error_code).

    ``error_code`` is stable for frontends (e.g. ``payload_too_large``).
    """
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 413:
            return (
                "The AI could not run because the request was too large. "
                "For Modify, try a shorter document, fewer chat messages above, "
                "or smaller edits at a time.",
                "payload_too_large",
            )
        if code == 429:
            return (
                "The AI provider rate limit was hit. Wait a moment and retry.",
                "rate_limited",
            )
        if code >= 500:
            return (
                "The AI provider had a temporary error. Please retry in a moment.",
                f"http_{code}",
            )
        return (
            f"The AI provider returned an error ({code}). Please retry or change the request.",
            f"http_{code}",
        )
    if isinstance(exc, httpx.TimeoutException):
        return (
            "The AI request timed out. Try again with a shorter message or document context.",
            "timeout",
        )
    return (str(exc), None)
