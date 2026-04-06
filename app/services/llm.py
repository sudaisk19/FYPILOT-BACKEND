"""
LLM Service
Async wrapper around GitHub Models inference.
Handles document-context injection for the document workspace feature.
Supports multiple models via distinct tokens from environment.

Provides two call modes:
  - call_llm()   : Blocking, returns full reply string (used by HTTP endpoints).
  - stream_llm() : Async generator, yields token chunks (used by WebSocket endpoints).
"""

import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.core.config import settings
from app.services.prompts import build_chat_system_prompt

TIMEOUT = 60.0


def get_model_config(model_choice: str) -> tuple[str, str]:
    """
    Returns the appropriate (model_id, token) based on the requested model name.
    Falls back to GPT-4o if the specific token is missing.
    """
    if model_choice == "deepseek" and settings.github_deepseek_token:
        return ("DeepSeek-R1", settings.github_deepseek_token)
    elif (
        model_choice in ("gpt-4o-mini", "gpt-4o-mini")
        and settings.github_gpto4mini_token
    ):
        return ("gpt-4o-mini", settings.github_gpto4mini_token)
    elif "llama" in model_choice.lower() and settings.github_llama4_token:
        # Using a widely available Llama model ID on GitHub Models
        return ("Meta-Llama-3.1-405B-Instruct", settings.github_llama4_token)

    # Default fallback
    return ("gpt-4o", settings.github_openai_token or "")


async def call_llm(
    history: List[Dict[str, Any]],
    document_content: Optional[str] = None,
    system_extra: Optional[str] = None,
    model_choice: str = "gpt-4o",
    doc_type: Optional[str] = None,
) -> str:
    """
    Call GitHub Models inference with optional document context grounding.

    Args:
        history:          List of {role, content} dicts (student + llm turns).
        document_content: JSON-serialised content of the active document tab.
                          If provided, injected into the system prompt.
        system_extra:     Any additional system-level instruction.
        model_choice:     Key representing the model to use (e.g. gpt-4o, deepseek, llama, gpt-4o-mini)
        doc_type:         Optional document type (e.g. 'proposal', 'literature_review')

    Returns:
        The LLM's reply as a plain string.

    Raises:
        RuntimeError: On HTTP error or unexpected API response.
    """
    messages = [
        {
            "role": "system",
            "content": build_chat_system_prompt(
                document_content=document_content,
                doc_type=doc_type,
                system_extra=system_extra,
            ),
        }
    ]
    messages.extend(history)

    model_id, token = get_model_config(model_choice)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{settings.github_openai_base_url}/chat/completions",
            headers=headers,
            json=body,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def stream_llm(
    history: List[Dict[str, Any]],
    document_content: Optional[str] = None,
    system_extra: Optional[str] = None,
    model_choice: str = "gpt-4o",
    doc_type: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Stream tokens from GitHub Models inference via Server-Sent Events.

    Async generator — yields individual token strings as they arrive.
    Designed for WebSocket endpoints that broadcast tokens in real-time.

    Usage:
        async for token in stream_llm(history, ...):
            await ws.send_json({"type": "llm_token", "token": token})
    """
    messages = [
        {
            "role": "system",
            "content": build_chat_system_prompt(
                document_content=document_content,
                doc_type=doc_type,
                system_extra=system_extra,
            ),
        }
    ]
    messages.extend(history)

    model_id, token = get_model_config(model_choice)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048,
        "stream": True,  # ← SSE streaming
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{settings.github_openai_base_url}/chat/completions",
            headers=headers,
            json=body,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                raw = line[len("data: ") :]
                if raw.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                    token_text = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if token_text:
                        yield token_text
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue
