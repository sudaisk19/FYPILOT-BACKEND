# app/models/request.py
import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db import Base
from app.models.group import InviteStatusEnum


class RequestTypeEnum(str, enum.Enum):
    """Enum for request type values."""

    supervisor = "supervisor"
    cosupervisor = "cosupervisor"


class Request(Base):
    __tablename__ = "requests"

    request_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.group_id", ondelete="CASCADE"),
        nullable=False,
    )
    faculty_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("faculty.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    request_type = Column(
        SQLEnum(RequestTypeEnum, name="request_type_enum", create_type=False),
        nullable=False,
    )
    status = Column(
        SQLEnum(InviteStatusEnum, name="invite_status_enum", create_type=False),
        nullable=False,
        default=InviteStatusEnum.pending,
    )
    message = Column(Text, nullable=True)
    feedback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(
        PGUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
