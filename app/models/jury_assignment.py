# app/models/jury_assignment.py

"""
Jury Assignment Models (Lean Schema).

- JuryAssignmentBatch: tracker for background job + container for easy deletion
- JuryAssignment: the actual jury↔project assignment data
"""

import enum
import uuid

from sqlalchemy import CheckConstraint, Integer, TIMESTAMP, Column
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class JuryBatchStatusEnum(str, enum.Enum):
    """Status of a jury assignment batch job."""

    processing = "processing"
    completed = "completed"
    failed = "failed"


class JuryAssignmentBatch(Base):
    """
    Tracker for a background jury assignment job.

    Purpose:
    1. Background Waiter — holds the status flag for frontend polling
    2. Undo Button — DELETE batch_id cascades to all child assignments
    """

    __tablename__ = "jury_assignment_batches"

    batch_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Job status (PROCESSING → COMPLETED / FAILED)
    status = Column(
        SAEnum(JuryBatchStatusEnum, name="jury_batch_status_enum", native_enum=True),
        nullable=False,
        default=JuryBatchStatusEnum.processing,
    )

    # Error details (if failed)
    error_log = Column(Text, nullable=True)

    # Timestamp
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    assignments = relationship(
        "JuryAssignment",
        back_populates="batch",
        cascade="all, delete-orphan",
    )


class JuryPair(Base):
    """Represents a pair of faculty members acting as a jury unit."""

    __tablename__ = "jury_pairs"

    jury_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    faculty_1_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("faculty.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    faculty_2_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("faculty.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    jury_number = Column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "faculty_1_id <> faculty_2_id", name="jury_pairs_diff_supervisors"
        ),
    )

    assignments = relationship(
        "JuryAssignment",
        back_populates="pair",
        cascade="all, delete-orphan",
    )


class JuryAssignment(Base):
    """A single jury pair assigned to evaluate a project within a batch."""

    __tablename__ = "jury_assignments"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    batch_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("jury_assignment_batches.batch_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    project_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.project_id"),
        nullable=False,
    )

    pair_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("jury_pairs.jury_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    score = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "batch_id", "project_id", "pair_id",
            name="uq_jury_assignment_batch_project_pair",
        ),
    )

    batch = relationship("JuryAssignmentBatch", back_populates="assignments")
    project = relationship("Project", foreign_keys=[project_id])
    pair = relationship("JuryPair", back_populates="assignments")
