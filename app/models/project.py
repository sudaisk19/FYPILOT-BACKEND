# app/models/project.py
import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.db import Base


class ProjectTypeEnum(str, enum.Enum):
    """Enum for valid project type values."""

    research = "research"
    product = "product"
    both = "both"


class Project(Base):
    __tablename__ = "projects"

    project_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    group_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.group_id", ondelete="CASCADE"),
        unique=True,  # One project per group
        nullable=True,
    )

    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    objectives = Column(JSONB, nullable=True)
    tech_stack = Column(JSONB, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    project_type = Column(
        SQLEnum(ProjectTypeEnum, name="project_type_enum", create_type=False),
        nullable=True,
        default=None,
    )
    industry_id = Column(
        PGUUID(as_uuid=True), ForeignKey("industries.industry_id"), nullable=True
    )
    repo_links = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    group = relationship("Group", backref="project")
    industry = relationship("Industry", back_populates="projects")
    domains = relationship(
        "Domain", secondary="project_domains", back_populates="projects"
    )


class ProjectDomain(Base):
    __tablename__ = "project_domains"

    project_id = Column(
        PGUUID(as_uuid=True), ForeignKey("projects.project_id"), primary_key=True
    )
    domain_id = Column(
        PGUUID(as_uuid=True), ForeignKey("domains.domain_id"), primary_key=True
    )
