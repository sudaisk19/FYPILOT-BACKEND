# app/models/project.py
import uuid
from enum import Enum

from sqlalchemy import CheckConstraint, Column, Date, DateTime
from sqlalchemy import ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from app.db import Base


class ProjectTypeEnum(str, Enum):
    """Enum values as stored in Postgres.

    The DB may contain either underscored ('product_and_research') or
    legacy spaced ('product and research') forms.  Both map to the same
    Python member.
    """

    research = "research"
    product = "product"
    product_and_research = "product_and_research"


# Mapping of legacy DB values (with spaces) → canonical enum value
_LEGACY_PROJECT_TYPE_MAP = {
    "product and research": "product_and_research",
}


class ProjectTypeColumn(TypeDecorator):
    """A TypeDecorator that reads/writes ``project_type_enum`` while
    transparently normalising legacy values that contain spaces."""

    impl = String          # underlying DB type (Postgres enum stored as text)
    cache_ok = True        # safe to cache compiled forms

    def process_bind_param(self, value, dialect):
        """Python → DB: send the canonical underscore form."""
        if value is None:
            return None
        if isinstance(value, ProjectTypeEnum):
            return value.value
        normalised = _normalise_project_type(str(value))
        return normalised

    def process_result_value(self, value, dialect):
        """DB → Python: convert any variant into ``ProjectTypeEnum``."""
        if value is None:
            return None
        normalised = _normalise_project_type(str(value))
        return ProjectTypeEnum(normalised)


def _normalise_project_type(raw: str) -> str:
    """Return the canonical enum value string for *raw*."""
    stripped = raw.strip().lower()
    if stripped in _LEGACY_PROJECT_TYPE_MAP:
        return _LEGACY_PROJECT_TYPE_MAP[stripped]
    underscored = stripped.replace(" ", "_")
    for member in ProjectTypeEnum:
        if underscored == member.value or stripped == member.name.lower():
            return member.value
    return stripped  # fall through – will raise on enum() if truly unknown


def parse_project_type(value):
    """Normalise any input to a ``ProjectTypeEnum`` member."""
    if value is None:
        raise ValueError("project type is None")
    if isinstance(value, ProjectTypeEnum):
        return value
    return ProjectTypeEnum(_normalise_project_type(str(value)))


def project_type_value(pt):
    """Return a user-facing string with spaces (e.g. 'product and research')."""
    if pt is None:
        return None
    member = parse_project_type(pt)
    return member.value.replace("_", " ")


class Project(Base):
    __tablename__ = "projects"

    project_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    group_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.group_id", ondelete="CASCADE"),
        unique=True,  # One project per group
        nullable=True,
    )

    fyp_id = Column(Text, unique=True, nullable=True)

    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    objectives = Column(JSONB, nullable=True)
    tech_stack = Column(JSONB, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    project_type = Column(
        ProjectTypeColumn(),
        nullable=False,
        default=ProjectTypeEnum.research,
        server_default=text("'research'::project_type_enum"),
    )
    industry_id = Column(
        PGUUID(as_uuid=True), ForeignKey("industries.industry_id"), nullable=True
    )
    repo_links = Column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(repo_links) = 'array'",
            name="ck_projects_repo_links_array",
        ),
    )

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
