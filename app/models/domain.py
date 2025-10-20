# app/models/domain.py
import uuid

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.db import Base


class Domain(Base):
    __tablename__ = "domains"

    domain_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False, unique=True)

    # Relationships - use string references to avoid circular imports
    projects = relationship(
        "Project", secondary="project_domains", back_populates="domains"
    )
    supervisors = relationship(
        "Supervisor", secondary="supervisor_domains", back_populates="domains"
    )
