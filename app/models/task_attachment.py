import uuid

from sqlalchemy import Column, ForeignKey, Text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class TaskAttachment(Base):
    __tablename__ = "task_attachments"

    attachment_id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks.task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_name = Column(Text, nullable=False)
    storage_key = Column(Text, nullable=False)
    mime_type = Column(Text, nullable=True)
    size_bytes = Column(BIGINT, nullable=True)
    uploaded_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    task = relationship("Task", back_populates="attachments")
