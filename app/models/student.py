# Import required libraries
import uuid

from sqlalchemy import Column, ForeignKey, Numeric, Text  # SQLAlchemy column types
from sqlalchemy.dialects.postgresql import (
    ARRAY,
    JSONB,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID  # Postgres-specific types
from sqlalchemy.ext.hybrid import hybrid_property  # For hybrid properties
from sqlalchemy.orm import relationship  # For ORM relationships

from app.db import Base  # Base class for declarative models


class Student(Base):
    """
    Student model representing the 'students' table in the database.
    Extends the Base class for SQLAlchemy ORM functionality.
    """

    __tablename__ = "students"  # Explicitly set table name in database

    # Primary key that links to User model
    user_id = Column(
        PGUUID(as_uuid=True),  # PostgreSQL UUID type
        ForeignKey(  # Foreign key constraint
            "users.user_id",  # References users table's user_id
            ondelete="CASCADE",  # Delete student when user is deleted
        ),
        primary_key=True,  # This is the primary key
        default=uuid.uuid4,  # Auto-generate UUIDs for new records
    )

    # Student's academic information
    roll_number = Column(
        Text,  # Text type for flexibility
        unique=True,  # No duplicate roll numbers
        nullable=False,  # Required field as per database schema
    )

    department = Column(
        Text, nullable=True  # Text type for department names  # Optional field
    )

    cgpa = Column(
        Numeric(3, 2),  # Precise decimal for GPA (e.g., 3.75)
        nullable=True,  # Optional field
    )

    # Student's professional information
    interests = Column(
        ARRAY(Text),  # Array of text for multiple interests
        nullable=True,  # Optional field
        default=list,  # Initialize as empty list
    )

    experience = Column(
        Text, nullable=True  # Text type for experience description  # Optional field
    )

    portfolio_projects = Column(
        JSONB,  # JSON type for structured project data
        nullable=True,  # Optional field
        default=dict,  # Initialize as empty dict
    )

    skills = Column(
        ARRAY(Text),  # Array of text for multiple skills
        nullable=True,  # Optional field
        default=list,  # Initialize as empty list
    )

    skills_levels = Column(
        JSONB,  # JSONB for per-skill level mapping (e.g., {"React": 5, "Python": 3})
        nullable=False,  # Required field
        default=dict,  # Initialize as empty dict
    )

    @hybrid_property
    def skills_levels_normalized(self):
        """
        Returns skills_levels with all skills having a default level of 1 if not specified.
        This ensures consistency: if a skill exists in the skills array but not in skills_levels,
        it defaults to level 1.

        Returns:
            dict: Normalized skills_levels mapping with default 1 for missing skills
        """
        levels = self.skills_levels or {}
        normalized = levels.copy()

        # Add default level 1 for any skills not in the mapping
        if self.skills:
            for skill in self.skills:
                if skill not in normalized:
                    normalized[skill] = 1

        return normalized

    def normalize_skills_levels_for_save(self):
        """
        Call this before saving to ensure skills_levels in DB has default 1 for all skills.
        Updates the skills_levels column in place.
        """
        if self.skills:
            normalized = self.skills_levels.copy() if self.skills_levels else {}
            for skill in self.skills:
                if skill not in normalized:
                    normalized[skill] = 1
            self.skills_levels = normalized

    # Relationship to User model (bidirectional)
    user = relationship(
        "User",  # References User model
        back_populates="student_profile",  # Name of relationship in User model
    )

    # Relationship to groups through group_members
    group_membership = relationship("GroupMember", back_populates="student")

    # Convenience relationship to access groups directly
    groups = relationship(
        "Group",
        secondary="group_members",
        back_populates="students",
        viewonly=True,
        primaryjoin="Student.user_id == group_members.c.student_id",
        secondaryjoin="group_members.c.group_id == Group.group_id",
    )

    tasks = relationship(
        "Task",
        back_populates="assignee",
        cascade="all, delete-orphan",
    )
