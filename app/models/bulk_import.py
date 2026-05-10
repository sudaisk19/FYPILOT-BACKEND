# app/models/bulk_import.py

"""
Bulk Import Models for batch user registration.

These models support the DB-queued job processing system for
bulk student/supervisor registration via CSV/Excel upload.
"""

import enum
import uuid

from sqlalchemy import TIMESTAMP, Column
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base
from app.models.user import RoleEnum


class BulkJobStatus(str, enum.Enum):
    """Status enum for bulk import jobs."""

    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class BulkItemStatus(str, enum.Enum):
    """Status enum for individual bulk import items."""

    pending = "pending"
    success = "success"
    failed = "failed"
    skipped = "skipped"


class BulkImportJob(Base):
    """
    Represents a bulk import job created when admin uploads a CSV/Excel file.

    Tracks overall progress and status of the import operation.
    """

    __tablename__ = "bulk_import_jobs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Admin who created this job
    created_by = Column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    # Target role for all users in this batch
    target_role = Column(
        SAEnum(
            RoleEnum,
            name="user_role_enum",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
    )

    # Job status
    status = Column(
        SAEnum(
            BulkJobStatus,
            name="bulk_job_status_enum",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
        default=BulkJobStatus.pending,
    )

    # Progress counters
    total_rows = Column(Integer, nullable=False, default=0)
    processed_rows = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    items = relationship(
        "BulkImportItem",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="BulkImportItem.row_number",
    )
    creator = relationship("User", foreign_keys=[created_by])


class BulkImportItem(Base):
    """
    Represents a single row from the uploaded CSV/Excel file.

    Stores the original payload data, processing status, and
    encrypted temporary password for admin download.
    """

    __tablename__ = "bulk_import_items"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Parent job
    job_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("bulk_import_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Row number from original file (1-indexed)
    row_number = Column(Integer, nullable=False)

    # Original row data as JSON
    payload = Column(JSONB, nullable=False)

    # Processing status
    status = Column(
        SAEnum(
            BulkItemStatus,
            name="bulk_item_status_enum",
            native_enum=False,
            create_constraint=False,
        ),
        nullable=False,
        default=BulkItemStatus.pending,
    )

    # Error message if failed
    error = Column(Text, nullable=True)

    # Created user reference (if success)
    created_user_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Encrypted temporary password for admin download
    temp_password_enc = Column(Text, nullable=True)

    # Expiry time for temp password download
    expires_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Timestamp
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    job = relationship("BulkImportJob", back_populates="items")
    created_user = relationship("User", foreign_keys=[created_user_id])
