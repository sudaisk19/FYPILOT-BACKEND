# app/models/group.py
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.db import Base


class Group(Base):
    __tablename__ = "groups"
    group_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    fyp_stage = Column(Text, nullable=False, default="ideation")
    fyp_cycle = Column(Text, nullable=False, default="fyp1")
    cohort_year = Column(Integer, nullable=True)
    max_members = Column(
        Integer, nullable=False, default=3, comment="Maximum number of members (1-3)"
    )
    milestone_template_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("milestone_templates.template_id"),
        nullable=True,
    )
    supervisor_id = Column(
        PGUUID(as_uuid=True), ForeignKey("supervisors.user_id"), nullable=True
    )
    cosupervisor_id = Column(
        PGUUID(as_uuid=True), ForeignKey("supervisors.user_id"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "max_members >= 1 AND max_members <= 3", name="check_max_members_range"
        ),
    )

    members = relationship(
        "GroupMember", back_populates="group", cascade="all, delete-orphan"
    )
    # Access students through members relationship instead of direct relationship
    students = relationship(
        "Student",
        secondary="group_members",
        back_populates="groups",
        viewonly=True,
        primaryjoin="Group.group_id == group_members.c.group_id",
        secondaryjoin="group_members.c.student_id == Student.user_id",
    )


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
    group = relationship("Group", back_populates="members", overlaps="groups,students")
    student = relationship(
        "Student", back_populates="group_membership", overlaps="groups,students"
    )


class GroupInvite(Base):
    __tablename__ = "group_invites"
    invite_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.group_id"), nullable=False)
    inviter_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    invitee_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    token = Column(Text, nullable=False, unique=True)
    status = Column(Text, nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
