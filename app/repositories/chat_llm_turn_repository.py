from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_llm_turn import ChatLlmTurn


class ChatLlmTurnRepository:
    async def record_turn(
        self,
        db: AsyncSession,
        *,
        room_id: str,
        request_id: str,
        user_id: Optional[UUID],
        user_message_id: Optional[str],
        model: Optional[str],
        latency_ms: Optional[int],
        token_count_estimate: Optional[int],
        status: str,
        error_detail: Optional[str] = None,
    ) -> ChatLlmTurn:
        row = ChatLlmTurn(
            room_id=room_id,
            request_id=request_id,
            user_id=user_id,
            user_message_id=user_message_id,
            model=model,
            latency_ms=latency_ms,
            token_count_estimate=token_count_estimate,
            status=status,
            error_detail=error_detail,
        )
        db.add(row)
        await db.flush()
        return row


chat_llm_turn_repo = ChatLlmTurnRepository()
