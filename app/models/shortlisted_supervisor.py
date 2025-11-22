# app/models/shortlisted_supervisor.py
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db import Base


class ShortlistedSupervisor(Base):
    __tablename__ = "shortlisted_supervisors"

    shortlist_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id = Column(PGUUID(as_uuid=True), ForeignKey("groups.group_id"), nullable=False)
    supervisor_id = Column(PGUUID(as_uuid=True), ForeignKey("supervisors.user_id"), nullable=False)
    added_by = Column(PGUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)







