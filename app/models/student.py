# Import required libraries
import uuid

from sqlalchemy import Column, ForeignKey, Numeric, Text  # SQLAlchemy column types
from sqlalchemy.dialects.postgresql import (
    ARRAY,
    JSONB,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID  # Postgres-specific types
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
