# app/models/group.py
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.db import Base


class Group(Base):
    __tablename__ = "groups"
    group_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    fyp_stage = Column(
        Enum(
            "ideation",
            "proposal",
            "approval",
            "implementation",
            "evaluation",
            "completed",
            name="fyp_stage_enum",
        ),
        nullable=False,
        default="ideation",
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship(
        "GroupMember", back_populates="group", cascade="all, delete-orphan"
    )
    students = relationship("Student", back_populates="group")


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.group_id", ondelete="CASCADE"),
        primary_key=True,
    )
    student_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "students.user_id", ondelete="CASCADE"
        ),  # ← must reference students.user_id
        primary_key=True,
    )
    joined_at = Column(DateTime, default=datetime.utcnow)

    # now SQLAlchemy can wire this relationship:
    group = relationship("Group", back_populates="members")
    student = relationship("Student", back_populates="group_membership")


class GroupInvite(Base):
    __tablename__ = "group_invites"
    invite_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.group_id"), nullable=False)
    inviter_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    invitee_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    token = Column(Text, nullable=False, unique=True)
    status = Column(
        Enum("pending", "accepted", "expired", "revoked", name="invite_status"),
        nullable=False,
        default="pending",
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
