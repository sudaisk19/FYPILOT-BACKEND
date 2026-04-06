# app/models/faculty_industry.py
from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db import Base


class FacultyIndustry(Base):
    __tablename__ = "faculty_industries"

    faculty_id = Column(
        PGUUID(as_uuid=True), ForeignKey("faculty.user_id"), primary_key=True
    )
    industry_id = Column(
        PGUUID(as_uuid=True), ForeignKey("industries.industry_id"), primary_key=True
    )
