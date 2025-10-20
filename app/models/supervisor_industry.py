# app/models/supervisor_industry.py
from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db import Base


class SupervisorIndustry(Base):
    __tablename__ = "supervisor_industries"

    supervisor_id = Column(
        PGUUID(as_uuid=True), ForeignKey("supervisors.user_id"), primary_key=True
    )
    industry_id = Column(
        PGUUID(as_uuid=True), ForeignKey("industries.industry_id"), primary_key=True
    )
