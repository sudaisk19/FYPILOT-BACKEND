"""Parse LLM output for document modify (HTML fragment) proposals."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

_KIND = "document_edit_proposal"


def _extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return None
    # Strip optional markdown fence
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try first {...} block
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        else:
            return None
    return data if isinstance(data, dict) else None


def parse_document_edit_proposal(
    raw: str,
) -> Optional[Tuple[str, str, List[str]]]:
    """
    Parse assistant text into (summary, html_fragment, warnings).

    Returns None if JSON invalid or not a document_edit_proposal.
    """
    data = _extract_json_object(raw)
    if not data:
        return None
    if data.get("kind") != _KIND:
        return None
    summary = data.get("summary_markdown") or data.get("summary") or ""
    if isinstance(summary, str):
        summary = summary.strip()
    else:
        summary = str(summary)
    frag = data.get("html_fragment")
    if not isinstance(frag, str) or not frag.strip():
        return None
    warnings = data.get("warnings") or []
    if not isinstance(warnings, list):
        warnings = []
    warnings = [str(w) for w in warnings]
    return (summary, frag.strip(), warnings)
