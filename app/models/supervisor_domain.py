# app/models/supervisor_domain.py
from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db import Base


class SupervisorDomain(Base):
    __tablename__ = "supervisor_domains"

    supervisor_id = Column(
        PGUUID(as_uuid=True), ForeignKey("supervisors.user_id"), primary_key=True
    )
    domain_id = Column(
        PGUUID(as_uuid=True), ForeignKey("domains.domain_id"), primary_key=True
    )
