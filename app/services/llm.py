"""
LLM Service
Async wrapper around GitHub Models inference (GPT-4o).
Handles document-context injection for the document workspace feature.
"""

import os
from typing import Any, Dict, List, Optional

import httpx

GITHUB_OPENAI_TOKEN = os.getenv("GITHUB_OPENAI_TOKEN", "")
BASE_URL = "https://models.github.ai/inference"
MODEL = "openai/gpt-4o"
TIMEOUT = 60.0


async def call_llm(
    history: List[Dict[str, Any]],
    document_content: Optional[str] = None,
    system_extra: Optional[str] = None,
) -> str:
    """
    Call GPT-4o with optional document context grounding.

    Args:
        history:          List of {role, content} dicts (student + llm turns).
        document_content: JSON-serialised content of the active document tab.
                          If provided, injected into the system prompt.
        system_extra:     Any additional system-level instruction.

    Returns:
        The LLM's reply as a plain string.

    Raises:
        RuntimeError: On HTTP error or unexpected API response.
    """
    system_parts = [
        "You are an expert academic writing assistant helping university students "
        "draft and improve their Final Year Project (FYP) documents."
    ]
    if document_content:
        system_parts.append(
            f"\n\nThe student currently has the following document open:\n"
            f"---\n{document_content}\n---\n"
            "Use this content as context when answering. "
            "If asked to improve or rewrite a section, return only the revised text."
        )
    if system_extra:
        system_parts.append(system_extra)

    messages = [{"role": "system", "content": "\n".join(system_parts)}]
    messages.extend(history)

    headers = {
        "Authorization": f"Bearer {GITHUB_OPENAI_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BASE_URL}/chat/completions", headers=headers, json=body
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
