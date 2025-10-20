# app/models/industry.py
import uuid

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.db import Base


class Industry(Base):
    __tablename__ = "industries"

    industry_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Relationships - use string references to avoid circular imports
    projects = relationship("Project", back_populates="industry")
    supervisors = relationship(
        "Supervisor", secondary="supervisor_industries", back_populates="industries"
    )
