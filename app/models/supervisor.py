# Import required libraries
import uuid

from sqlalchemy import CheckConstraint, Column, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.db import Base


class Supervisor(Base):
    """
    Supervisor model representing the 'supervisors' table in the database.
    Handles faculty members who supervise student projects.
    Includes capacity management and project preferences.
    """

    __tablename__ = "supervisors"  # Explicitly set table name in database

    # Primary key that links to User model
    user_id = Column(
        PGUUID(as_uuid=True),  # PostgreSQL UUID type
        ForeignKey(  # Foreign key constraint
            "users.user_id",  # References users table's user_id
            ondelete="CASCADE",  # Delete supervisor when user is deleted
        ),
        primary_key=True,  # This is the primary key
        default=uuid.uuid4,  # Auto-generate UUIDs for new records
    )

    # Academic/Professional Information
    department = Column(
        Text, nullable=True  # Text type for department names  # Optional field
    )

    designation = Column(
        Text, nullable=True  # Text type for job titles  # Optional field
    )

    office = Column(
        Text, nullable=True  # Text type for office location  # Optional field
    )

    # Project Preferences and Requirements
    requirements = Column(
        ARRAY(Text),  # Array of text for multiple requirements
        nullable=True,  # Optional field
        default=list,  # Initialize as empty list
    )

<<<<<<< HEAD
<<<<<<< HEAD
    project_type = Column(
        SQLEnum(
=======
    project_type = Column(
        Enum(
>>>>>>> 4c72848 (chore: bugs fixing)
            "research",
            "product",
            "product and research",
            name="project_type_enum",
<<<<<<< HEAD
            create_type=False,
        ),
        nullable=False,
        default="research",
    )
=======
    project_type = Column(Text, nullable=False)
=======
            native_enum=False,
        ),
        nullable=False,
    )
>>>>>>> 4c72848 (chore: bugs fixing)

>>>>>>> bf3f867 (bugs fixing)
    # Capacity Management
    capacity_max = Column(
        Integer,  # Integer type for max students
        nullable=False,  # Required field
        default=8,  # Default maximum capacity
    )

    capacity_filled = Column(
        Integer,  # Integer type for current students
        nullable=False,  # Required field
        default=0,  # Start with 0 students
    )

    # Capacity Constraints
    __table_args__ = (
        CheckConstraint("capacity_max >= 0", name="check_capacity_max_positive"),
        CheckConstraint("capacity_filled >= 0", name="check_capacity_filled_positive"),
        CheckConstraint("capacity_filled <= capacity_max", name="check_capacity_valid"),
    )

    # Relationship to User model (bidirectional)
    user = relationship(
        "User",  # References User model
        back_populates="supervisor_profile",  # Name of relationship in User model
    )

    # Relationships to domains and industries
    domains = relationship(
        "Domain", secondary="supervisor_domains", back_populates="supervisors"
    )
    industries = relationship(
        "Industry", secondary="supervisor_industries", back_populates="supervisors"
    )

    supervised_groups = relationship(
        "Group",
        foreign_keys="[Group.supervisor_id]",  # Explicitly link to the main supervisor field
        back_populates="supervisor",
    )

    # Added relationship for Co-Supervised Groups (using Array containment)
    # Uses SQL: user_id = ANY(cosupervisor_ids)
    co_supervised_groups = relationship(
        "Group",
        primaryjoin="Supervisor.user_id == func.any(foreign(Group.cosupervisor_ids))",
        viewonly=True,
    )
