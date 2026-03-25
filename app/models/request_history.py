# app/models/request_history.py
import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from app.db import Base
from app.models.group import InviteStatusEnum



class RequestHistory(Base):
    __tablename__ = "request_history"

    history_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(PGUUID(as_uuid=True), ForeignKey("requests.request_id", ondelete="CASCADE"), nullable=False)
    group_id = Column(PGUUID(as_uuid=True), nullable=True)
    faculty_id = Column(PGUUID(as_uuid=True), nullable=True)
    action = Column(SQLEnum(InviteStatusEnum, name="invite_status_enum", create_type=False), nullable=False)
    message = Column(Text, nullable=True)
    feedback = Column(Text, nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
