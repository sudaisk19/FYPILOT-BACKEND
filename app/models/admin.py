# Import required libraries
import uuid

from sqlalchemy import TIMESTAMP, Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class Admin(Base):
    """
    Admin model representing the 'admins' table in the database.
    Extends the base user with admin-specific attributes.
    Note: Profile picture is handled by the User model's avatar field.
    """

    __tablename__ = "admins"  # Explicitly set table name in database

    # Primary key that links to User model
    user_id = Column(
        PGUUID(as_uuid=True),  # PostgreSQL UUID type
        ForeignKey(  # Foreign key constraint
            "users.user_id",  # References users table's user_id
            ondelete="CASCADE",  # Delete admin when user is deleted
        ),
        primary_key=True,  # This is the primary key
        default=uuid.uuid4,  # Auto-generate UUIDs for new records
    )

    # Contact Information
    phone = Column(Text, nullable=True)  # Text type for phone numbers  # Optional field

    # Profile picture (separate from User.profile_avatar)
    profile_pic = Column(
        Text, nullable=True  # Text type for profile picture URL  # Optional field
    )

    # Timestamps for record tracking
    created_at = Column(
        TIMESTAMP(timezone=True),  # Timestamp with timezone
        server_default=func.now(),  # Automatically set to current time
        nullable=False,  # Required field
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),  # Timestamp with timezone
        server_default=func.now(),  # Default to current time
        onupdate=func.now(),  # Auto-update on record change
        nullable=False,  # Required field
    )

    # Relationship to User model (bidirectional)
    user = relationship(
        "User",  # References User model
        back_populates="admin_profile",  # Name of relationship in User model
    )
