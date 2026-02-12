# app/models/announcement.py

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, Text, Boolean, ForeignKey, DateTime, Numeric, BigInteger
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.db import Base

class AnnouncementRoleEnum(str, enum.Enum):
    """Enum for who created the announcement."""
    admin = "admin"
    supervisor = "supervisor"

class TargetRoleEnum(str, enum.Enum):
    """Enum for the three targets you mentioned: Students, Supervisors, and Both."""
    all_students = "all_students"
    all_supervisors = "all_supervisors"
    both = "both"

class FileTypeEnum(str, enum.Enum):
    """Enum for types of files attached.""" 
    Template = "Template"
    Document = "Document"


# --- MODELS ---

class Announcement(Base):
    __tablename__ = "announcements"

    announcement_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"))
    
    # Consistent Enum usage
    created_by_role = Column(
        SQLEnum(AnnouncementRoleEnum, name="announcement_role_enum", create_type=False),
        nullable=False,
        default=AnnouncementRoleEnum.admin
    )
    
    title = Column(Text, nullable=False)
    description = Column(Text)
    is_submission_request = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    due_at = Column(DateTime)
    total_marks = Column(Numeric)

    # Relationships
    targets = relationship("AnnouncementTarget", back_populates="announcement", cascade="all, delete-orphan")
    files = relationship("AnnouncementFile", back_populates="announcement", cascade="all, delete-orphan")


class AnnouncementTarget(Base):
    __tablename__ = "announcement_targets"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    announcement_id = Column(PGUUID(as_uuid=True), ForeignKey("announcements.announcement_id", ondelete="CASCADE"))
    
    # Consistent with group.py where table name is "groups"
    group_id = Column(PGUUID(as_uuid=True), ForeignKey("groups.group_id", ondelete="CASCADE"), nullable=True)
    
    target_role = Column(
        SQLEnum(TargetRoleEnum, name="target_role_enum", create_type=False),
        nullable=True
    )

    announcement = relationship("Announcement", back_populates="targets")


class AnnouncementFile(Base):
    __tablename__ = "announcement_files"

    file_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    announcement_id = Column(PGUUID(as_uuid=True), ForeignKey("announcements.announcement_id", ondelete="CASCADE"))
    file_name = Column(Text, nullable=False)
    storage_key = Column(Text, nullable=False)
    mime_type = Column(Text)
    size_bytes = Column(BigInteger)
    
    file_type = Column(
        SQLEnum(FileTypeEnum, name="file_type_enum", create_type=False),
        default=FileTypeEnum.Document
    )
    module = Column(Text)
    
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    announcement = relationship("Announcement", back_populates="files")