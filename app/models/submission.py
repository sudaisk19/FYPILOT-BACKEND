import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.announcement import Announcement
    from app.models.group import Group
    from app.models.user import User


class SubmissionTypeEnum(str, enum.Enum):
    official = "official"
    unofficial = "unofficial"


class SubmissionStatusEnum(str, enum.Enum):
    pending = "pending"
    missing = "missing"
    submitted = "submitted"
    graded = "graded"


class Submission(Base):
    __tablename__ = "submissions"

    submission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    group_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("groups.group_id", ondelete="CASCADE")
    )

    created_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)

    type: Mapped[SubmissionTypeEnum] = mapped_column(
        Enum(SubmissionTypeEnum, name="submission_type_enum"),
        nullable=False,
        default=SubmissionTypeEnum.unofficial,
    )
    status: Mapped[SubmissionStatusEnum] = mapped_column(
        Enum(SubmissionStatusEnum, name="submission_status_enum"),
        default=SubmissionStatusEnum.submitted,
    )

    linked_announcement_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("announcements.announcement_id", ondelete="SET NULL"),
    )

    # Grading - Supervisor
    supervisor_marks: Mapped[Optional[float]] = mapped_column(Numeric)
    supervisor_feedback: Mapped[Optional[str]] = mapped_column(Text)
    supervisor_graded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # Grading - Admin
    admin_marks: Mapped[Optional[float]] = mapped_column(Numeric)
    admin_feedback: Mapped[Optional[str]] = mapped_column(Text)
    admin_graded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    group: Mapped["Group"] = relationship("Group", back_populates="submissions")
    creator: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by], lazy="joined"
    )
    linked_announcement: Mapped[Optional["Announcement"]] = relationship(
        "Announcement",
        back_populates="submissions",
        foreign_keys=[linked_announcement_id],
    )
    files: Mapped[List["SubmissionFile"]] = relationship(
        "SubmissionFile", back_populates="submission", cascade="all, delete-orphan"
    )

    # ── Explicit indexes ──────────────────────────────────────────────────────
    __table_args__ = (
        # Most critical: submissions for a group filtered by status
        # Avoids full table scan when loading a group's submission history
        Index("ix_submissions_group_status", "group_id", "status"),
        # Admin view: all submissions with a specific status (e.g., pending review)
        Index("ix_submissions_status", "status"),
        # Range queries on submitted_at — avoids CAST which breaks index usage
        Index("ix_submissions_submitted_at", "submitted_at"),
    )


class SubmissionFile(Base):
    __tablename__ = "submission_files"

    file_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    submission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("submissions.submission_id", ondelete="CASCADE"),
    )

    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(Text)
    size_bytes: Mapped[Optional[int]] = mapped_column(BIGINT)

    supervisor_comment: Mapped[Optional[str]] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    submission: Mapped["Submission"] = relationship(
        "Submission", back_populates="files"
    )
