"""TipTap / HTML snippets → plain text for LLM context (token-efficient)."""

from __future__ import annotations

import re
from html import unescape
from typing import Any, Optional

_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)


def tip_tap_html_from_content(content: Any) -> Optional[str]:
    """Return TipTap `content.html` string when present and non-empty."""
    if not isinstance(content, dict):
        return None
    html = content.get("html")
    if isinstance(html, str):
        stripped = html.strip()
        return stripped or None
    return None


def html_to_plaintext(html: str) -> str:
    """Strip tags and collapse whitespace."""
    text = _TAG_RE.sub(" ", html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
