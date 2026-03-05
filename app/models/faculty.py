# Import required libraries
import uuid

from sqlalchemy import Boolean, CheckConstraint, Column
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.db import Base


class Faculty(Base):
    """
    Faculty model representing the 'faculty' table in the database.
    Handles faculty members who may supervise student projects and/or
    serve as jury members. The is_supervisor and is_jury flags determine
    what a faculty member can do.
    """

    __tablename__ = "faculty"

    # Primary key that links to User model
    user_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Academic/Professional Information
    department = Column(Text, nullable=True)
    designation = Column(Text, nullable=True)
    office = Column(Text, nullable=True)

    # Project Preferences and Requirements
    requirements = Column(
        ARRAY(Text),
        nullable=True,
        default=list,
    )

    project_type = Column(
        SQLEnum(
            "research",
            "product",
            "product and research",
            name="project_type_enum",
            create_type=False,
        ),
        nullable=False,
        default="research",
    )

    # Role flags — determine what the faculty member can do
    is_supervisor = Column(
        Boolean,
        nullable=False,
        server_default="true",
        default=True,
    )

    is_jury = Column(
        Boolean,
        nullable=False,
        server_default="true",
        default=True,
    )

    is_active = Column(
        Boolean,
        nullable=False,
        server_default="true",
        default=True,
    )

    # Capacity Management
    capacity_max = Column(
        Integer,
        nullable=False,
        default=8,
    )

    capacity_filled = Column(
        Integer,
        nullable=False,
        default=0,
    )

    # Capacity Constraints
    __table_args__ = (
        CheckConstraint("capacity_max >= 0", name="check_capacity_max_positive"),
        CheckConstraint("capacity_filled >= 0", name="check_capacity_filled_positive"),
        CheckConstraint("capacity_filled <= capacity_max", name="check_capacity_valid"),
    )

    # Relationship to User model (bidirectional)
    user = relationship(
        "User",
        back_populates="faculty_profile",
    )

    # Relationships to domains and industries
    domains = relationship(
        "Domain", secondary="faculty_domains", back_populates="faculty_members"
    )
    industries = relationship(
        "Industry", secondary="faculty_industries", back_populates="faculty_members"
    )

    supervised_groups = relationship(
        "Group",
        foreign_keys="[Group.supervisor_id]",
        back_populates="supervisor",
    )

    # Co-Supervised Groups (using Array containment)
    co_supervised_groups = relationship(
        "Group",
        primaryjoin="Faculty.user_id == func.any(foreign(Group.cosupervisor_ids))",
        viewonly=True,
    )
