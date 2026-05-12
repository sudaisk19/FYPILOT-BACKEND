"""Persist modify-mode LLM replies (document edit proposals) for collaborative chat."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.document_edit_proposal_repository import (
    document_edit_proposal_repo,
)
from app.services.edit_proposal_parser import parse_document_edit_proposal

logger = logging.getLogger(__name__)


async def finalize_modify_mode_reply(
    mongo_db: AsyncIOMotorDatabase,
    *,
    chat_session_id: str,
    user_id: str,
    full_reply: str,
    is_modify: bool,
    active_document_id: Optional[str],
    baseline_lock_version: Optional[int],
    doc_context: Optional[Dict[str, Any]],
    request_id: Optional[str],
    model_choice: str,
) -> Tuple[str, Dict[str, Any], Optional[str]]:
    """
    If ``is_modify``, parse JSON proposal; on success insert Mongo proposal and
    attach ``proposal_id`` to assistant metadata.

    Returns ``(content, metadata, proposal_id)`` where ``proposal_id`` is set only
    when a pending proposal row was created.
    """
    meta: Dict[str, Any] = {"model": model_choice}
    if request_id:
        meta["request_id"] = request_id

    if not is_modify:
        return full_reply, meta, None

    parsed = parse_document_edit_proposal(full_reply)
    if not parsed:
        err = (
            "[Modify] The model did not return valid proposal JSON "
            "(expected kind=document_edit_proposal with html_fragment). "
            "Please try again."
        )
        meta["modify_parse_error"] = True
        return err, meta, None

    summary, html_fragment, warnings = parsed
    if not active_document_id or baseline_lock_version is None:
        meta["modify_parse_error"] = True
        return (
            "[Modify] Missing document context; cannot create a proposal.",
            meta,
            None,
        )

    try:
        proposal_id = await document_edit_proposal_repo.create_proposal(
            mongo_db,
            chat_session_id=chat_session_id,
            active_document_id=active_document_id,
            baseline_lock_version=int(baseline_lock_version),
            html_fragment=html_fragment,
            summary=summary,
            warnings=warnings,
            user_id=user_id,
            request_id=request_id,
        )
    except Exception as exc:
        logger.exception("create_proposal failed: %s", exc)
        meta["modify_parse_error"] = True
        return (
            "[Modify] Could not save the proposal. Please try again.",
            meta,
            None,
        )

    meta["proposal_id"] = proposal_id
    meta["modify_proposal"] = True
    meta["proposal_summary"] = summary
    return full_reply, meta, proposal_id


async def link_proposal_to_assistant_message(
    mongo_db: AsyncIOMotorDatabase,
    proposal_id: str,
    assistant_message_id: str,
) -> None:
    await document_edit_proposal_repo.set_assistant_message_id(
        mongo_db, proposal_id, assistant_message_id
    )
