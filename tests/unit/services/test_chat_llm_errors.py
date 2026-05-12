"""Unit tests for LLM stream error formatting (SSE / WebSocket clients)."""

import httpx

from app.services.chat_llm_errors import format_chat_stream_llm_error


def test_413_maps_to_payload_too_large() -> None:
    req = httpx.Request("POST", "https://example.com/v1")
    resp = httpx.Response(413, request=req)
    exc = httpx.HTTPStatusError("payload too large", request=req, response=resp)
    detail, code = format_chat_stream_llm_error(exc)
    assert code == "payload_too_large"
    assert "too large" in detail.lower()


def test_429_maps_to_rate_limited() -> None:
    req = httpx.Request("POST", "https://example.com/v1")
    resp = httpx.Response(429, request=req)
    exc = httpx.HTTPStatusError("too many", request=req, response=resp)
    detail, code = format_chat_stream_llm_error(exc)
    assert code == "rate_limited"
    assert "rate limit" in detail.lower()


def test_generic_exception_returns_str() -> None:
    detail, code = format_chat_stream_llm_error(ValueError("boom"))
    assert "boom" in detail
    assert code is None
