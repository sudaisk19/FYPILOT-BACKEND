# app/models/student.py
import uuid

from sqlalchemy import ARRAY, Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.db import Base


class Student(Base):
    __tablename__ = "students"

    user_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
        default=uuid.uuid4,
    )
    roll_number = Column(Text, unique=True, nullable=False)
    department = Column(Text)
    group_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.group_id", ondelete="SET NULL"),
        nullable=True,
    )
    skills = Column(ARRAY(Text))

    # relationships
    user = relationship("User", back_populates="student_profile")
    group = relationship("Group", back_populates="students")
    group_membership = relationship(
        "GroupMember",
        back_populates="student",
        cascade="all, delete-orphan",
    )
