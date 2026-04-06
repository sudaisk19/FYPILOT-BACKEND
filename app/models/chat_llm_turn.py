"""Postgres audit row for collaborative chat LLM turns (observability / cost)."""

import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ChatLlmTurn(Base):
    """
    One row per collaborative chat LLM generation (per request_id).
    Chat messages themselves live in MongoDB; this table is analytics only.
    """

    __tablename__ = "chat_llm_turns"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    room_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    user_message_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_count_estimate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
