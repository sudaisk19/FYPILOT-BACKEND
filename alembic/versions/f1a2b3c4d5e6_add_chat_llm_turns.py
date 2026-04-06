"""add chat_llm_turns for collaborative chat observability

Revision ID: f1a2b3c4d5e6
Revises: e8824ab04c3b
Create Date: 2026-04-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e8824ab04c3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_llm_turns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("room_id", sa.String(length=80), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("user_message_id", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_count_estimate", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_chat_llm_turns_room_id", "chat_llm_turns", ["room_id"])
    op.create_index("ix_chat_llm_turns_request_id", "chat_llm_turns", ["request_id"])
    op.create_index("ix_chat_llm_turns_user_id", "chat_llm_turns", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_llm_turns_user_id", table_name="chat_llm_turns")
    op.drop_index("ix_chat_llm_turns_request_id", table_name="chat_llm_turns")
    op.drop_index("ix_chat_llm_turns_room_id", table_name="chat_llm_turns")
    op.drop_table("chat_llm_turns")
