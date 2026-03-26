import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.group import Group
    from app.models.user import User


class DocTypeEnum(str, enum.Enum):
    srs = "srs"
    proposal = "proposal"
    progress_report = "progress_report"
    literature_review = "literature_review"
    meeting_minutes = "meeting_minutes"


class SaveTriggerEnum(str, enum.Enum):
    student = "student"
    llm = "llm"


class FilePurposeEnum(str, enum.Enum):
    export = "export"
    attachment = "attachment"


class GroupDocument(Base):
    """
    Live draft of a student group document.
    Content is continuously autosaved (incrementing lock_version).
    Multiple documents can share the same chat_session_id (workspace model).
    """

    __tablename__ = "group_documents"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    group_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.group_id", ondelete="CASCADE"),
        nullable=False,
    )
    # Links to the MongoDB workspace session — NOT unique (many docs per session)
    chat_session_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    doc_type: Mapped[DocTypeEnum] = mapped_column(
        Enum(DocTypeEnum, name="doc_type_enum", create_type=False),
        nullable=False,
        default=DocTypeEnum.srs,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)

    # JSONB live draft — continuously autosaved by the frontend
    content: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Optimistic concurrency — incremented on every autosave
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Optional: which announcement file / template seeded this doc
    source_file_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("announcement_files.file_id", ondelete="SET NULL"),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    created_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    group: Mapped["Group"] = relationship("Group", back_populates="documents")
    creator: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by], lazy="selectin"
    )
    updater: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[updated_by], lazy="selectin"
    )
    versions: Mapped[List["DocumentVersion"]] = relationship(
        "DocumentVersion", back_populates="document", cascade="all, delete-orphan"
    )
    files: Mapped[List["DocumentFile"]] = relationship(
        "DocumentFile", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_group_documents_group_id", "group_id"),
        Index("idx_group_documents_group_doc_type", "group_id", "doc_type"),
        Index("idx_group_documents_chat_session_id", "chat_session_id"),
        Index("idx_group_documents_group_active", "group_id", "is_active"),
    )


class DocumentVersion(Base):
    """
    Immutable snapshot of a document at a point in time.
    Created only on major events (manual save, accepted AI edit, PDF export).
    """

    __tablename__ = "document_versions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("group_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Sequential snapshot number per document
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Immutable JSON-serialised snapshot of content at this point
    content: Mapped[str] = mapped_column(Text, nullable=False)

    save_trigger: Mapped[SaveTriggerEnum] = mapped_column(
        Enum(SaveTriggerEnum, name="save_trigger_enum", create_type=False),
        nullable=False,
        default=SaveTriggerEnum.student,
    )
    created_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    document: Mapped["GroupDocument"] = relationship(
        "GroupDocument", back_populates="versions"
    )
    creator: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by], lazy="selectin"
    )

    __table_args__ = (
        Index("idx_document_versions_doc_version", "document_id", "version_number"),
        Index("idx_document_versions_save_trigger", "document_id", "save_trigger"),
    )


class DocumentFile(Base):
    """
    Files attached to or exported from a document.
    Stored in the 'group_document_files' Supabase storage bucket.
    Path convention: {group_id}/{document_id}/{file_id}.{ext}
    """

    __tablename__ = "document_files"

    file_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("group_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploaded_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    file_purpose: Mapped[FilePurposeEnum] = mapped_column(
        Enum(FilePurposeEnum, name="file_purpose_enum", create_type=False),
        nullable=False,
    )
    # Which version snapshot this file is associated with (for exports)
    version_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    document: Mapped["GroupDocument"] = relationship(
        "GroupDocument", back_populates="files"
    )
    uploader: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[uploaded_by], lazy="selectin"
    )

    __table_args__ = (
        Index("idx_document_files_document_id", "document_id"),
        Index("idx_document_files_document_purpose", "document_id", "file_purpose"),
    )
