# app/models/faculty_domain.py
from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db import Base


class FacultyDomain(Base):
    __tablename__ = "faculty_domains"

    faculty_id = Column(
        PGUUID(as_uuid=True), ForeignKey("faculty.user_id"), primary_key=True
    )
    domain_id = Column(
        PGUUID(as_uuid=True), ForeignKey("domains.domain_id"), primary_key=True
    )
