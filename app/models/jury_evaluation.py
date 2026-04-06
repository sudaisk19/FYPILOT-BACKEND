# app/models/jury_evaluation.py
"""SQLAlchemy models for jury and proposal evaluation workflows."""

import enum
import uuid

from sqlalchemy import (
    TIMESTAMP,
    Column,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy import (
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class JuryGradeEnum(str, enum.Enum):
    """Letter grades a jury member can assign."""

    A_plus = "A+"
    A = "A"
    A_minus = "A-"
    B_plus = "B+"
    B = "B"
    B_minus = "B-"
    C_plus = "C+"
    C = "C"
    C_minus = "C-"
    D_plus = "D+"
    D = "D"
    F = "F"


class ProposalStatusEnum(str, enum.Enum):
    """Overall proposal decision for proposal evaluation form."""

    accepted = "accepted"
    accepted_with_changes = "accepted_with_changes"
    rejected = "rejected"


class JuryEvaluation(Base):
    __tablename__ = "jury_evaluations"

    evaluation_id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    group_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.group_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    jury_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("faculty.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    milestone_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("admin_milestone.milestone_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    letter_grade = Column(
        SAEnum(JuryGradeEnum, name="jury_grade_enum"),
        nullable=False,
    )
    numeric_marks = Column(Numeric(5, 2), nullable=True)
    comments = Column(Text, nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "jury_id",
            "milestone_id",
            name="uq_jury_evaluation_unique",
        ),
    )

    group = relationship("Group")
    milestone = relationship("AdminMilestone")


class ProposalEvaluation(Base):
    __tablename__ = "proposal_evaluations"

    evaluation_id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    group_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.group_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    jury_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("faculty.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    milestone_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("admin_milestone.milestone_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    introduction = Column(Numeric(3, 1), nullable=True)
    literature_review = Column(Numeric(3, 1), nullable=True)
    methodology = Column(Numeric(3, 1), nullable=True)
    planning = Column(Numeric(3, 1), nullable=True)
    system_diagram = Column(Numeric(3, 1), nullable=True)
    total_marks = Column(Numeric(3, 1), nullable=True)
    deliverables = Column(Text, nullable=True)

    recommended_changes = Column(Text, nullable=True)
    project_status = Column(
        SAEnum(ProposalStatusEnum, name="proposal_status_enum"),
        nullable=True,
    )

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "jury_id",
            "milestone_id",
            name="uq_proposal_evaluation_unique",
        ),
    )

    group = relationship("Group")
    milestone = relationship("AdminMilestone")


class ProposalEvaluationConfig(Base):
    __tablename__ = "proposal_evaluation_config"

    id = Column(Integer, primary_key=True, default=1)
    intro_max = Column(Numeric(3, 1), nullable=False, default=2)
    literature_max = Column(Numeric(3, 1), nullable=False, default=2)
    methodology_max = Column(Numeric(3, 1), nullable=False, default=2)
    planning_max = Column(Numeric(3, 1), nullable=False, default=2)
    diagram_max = Column(Numeric(3, 1), nullable=False, default=2)

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
