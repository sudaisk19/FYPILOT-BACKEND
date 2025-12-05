# app/models/project.py
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column, Date, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.db import Base


class ProjectTypeEnum(str, Enum):
    """Enum for project types"""

    research = "research"
    product = "product"
    product_and_research = "product and research"
<<<<<<< HEAD
    
def parse_project_type(value):
    """Normalize input and return ProjectTypeEnum.

    Accepts enum member, the member name (e.g. 'product_and_research'),
    or the member value (e.g. 'product and research'), case-insensitively.
    Raises ValueError for unknown values.
    """
    if value is None:
        raise ValueError("project type is None")
    if isinstance(value, ProjectTypeEnum):
        return value
    s = str(value).strip().lower()
    s_norm = s.replace("_", " ").replace("-", " ")
    for member in ProjectTypeEnum:
        if s_norm == member.value.lower() or s_norm == member.name.lower():
            return member
    raise ValueError(f"Unknown project type: {value}")


def project_type_value(pt):
    """Return the user-facing string (enum.value) or None."""
    if pt is None:
        return None
    if isinstance(pt, ProjectTypeEnum):
        return pt.value
    try:
        return parse_project_type(pt).value
    except ValueError:
        return str(pt)
=======
>>>>>>> bf3f867 (bugs fixing)


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
<<<<<<< HEAD
    project_type = Column(
        SQLEnum(
            "research",
            "product",
            "product and research",
            name="project_type_enum",
            create_type=False,
        ),
        nullable=False,
        default="research",
    )
=======
    project_type = Column(Text, nullable=False, default=ProjectTypeEnum.research.value)
>>>>>>> bf3f867 (bugs fixing)
    industry_id = Column(
        PGUUID(as_uuid=True), ForeignKey("industries.industry_id"), nullable=True
    )
    repo_links = Column(JSONB, nullable=False, default=list)
    fyp_id = Column(Text, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    group = relationship("Group", back_populates="project")
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
