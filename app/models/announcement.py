# app/models/announcement.py

import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean as SQLBoolean
from sqlalchemy import (
    CheckConstraint,
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
    from app.models.group import Group
    from app.models.submission import Submission
    from app.models.user import User


class AnnouncementRoleEnum(str, enum.Enum):
    admin = "admin"
    supervisor = "supervisor"
    faculty = "faculty"  # legacy value retained for backward compatibility

    @classmethod
    def supervisor_values(cls):
        """Return all enum values that should be treated as supervisor roles."""
        return (cls.supervisor, cls.faculty)

    @classmethod
    def normalize(cls, value):
        """Map legacy values to the canonical enum used by the API."""
        if value is None:
            return None
        if value == cls.faculty:
            return cls.supervisor
        return value


class TargetRoleEnum(str, enum.Enum):
    all_students = "all_students"
    all_supervisors = "all_supervisors"
    all_faculty = "all_faculty"
    both = "both"  # Added from sumaiya-dev to preserve functionality
    fyp1_students = "fyp1_students"
    fyp2_students = "fyp2_students"


class FileTypeEnum(str, enum.Enum):
    Template = "Template"
    Document = "Document"


class Announcement(Base):
    __tablename__ = "announcements"

    announcement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    created_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL")
    )
    created_by_role: Mapped[AnnouncementRoleEnum] = mapped_column(
        Enum(AnnouncementRoleEnum, name="announcement_role_enum"), nullable=False
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    is_submission_request: Mapped[bool] = mapped_column(SQLBoolean, default=False)

    # Submission request fields
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    total_marks: Mapped[Optional[float]] = mapped_column(Numeric)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    creator: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by], lazy="joined"
    )
    targets: Mapped[List["AnnouncementTarget"]] = relationship(
        "AnnouncementTarget",
        back_populates="announcement",
        cascade="all, delete-orphan",
    )
    files: Mapped[List["AnnouncementFile"]] = relationship(
        "AnnouncementFile", back_populates="announcement", cascade="all, delete-orphan"
    )
    submissions: Mapped[List["Submission"]] = relationship(
        "Submission",
        back_populates="linked_announcement",
        foreign_keys="Submission.linked_announcement_id",
    )

    # ── Explicit indexes ──────────────────────────────────────────────────────
    __table_args__ = (
        # FK lookup: all announcements created by a specific admin/supervisor
        Index("ix_announcements_created_by", "created_by"),
        # Deadline queries: upcoming submission requests ordered by due_at
        Index("ix_announcements_due_at", "due_at"),
        # Combined: "show active submission requests with upcoming deadlines"
        Index("ix_announcements_submission_due", "is_submission_request", "due_at"),
    )


class AnnouncementTarget(Base):
    __tablename__ = "announcement_targets"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    announcement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("announcements.announcement_id", ondelete="CASCADE"),
    )

    group_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("groups.group_id", ondelete="CASCADE")
    )
    target_role: Mapped[Optional[TargetRoleEnum]] = mapped_column(
        Enum(TargetRoleEnum, name="target_role_enum")
    )

    # Relationships
    announcement: Mapped["Announcement"] = relationship(
        "Announcement", back_populates="targets"
    )
    group: Mapped[Optional["Group"]] = relationship("Group")

    __table_args__ = (
        CheckConstraint(
            "(group_id IS NOT NULL AND target_role IS NULL) OR (group_id IS NULL AND target_role IS NOT NULL)",
            name="check_target_exclusivity",
        ),
    )


class AnnouncementFile(Base):
    __tablename__ = "announcement_files"

    file_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    announcement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("announcements.announcement_id", ondelete="CASCADE"),
    )

    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(Text)
    size_bytes: Mapped[Optional[int]] = mapped_column(BIGINT)

    file_type: Mapped[FileTypeEnum] = mapped_column(
        Enum(FileTypeEnum, name="file_type_enum"), default=FileTypeEnum.Document
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    announcement: Mapped["Announcement"] = relationship(
        "Announcement", back_populates="files"
    )
