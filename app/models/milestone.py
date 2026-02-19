# app/models/milestone.py
import uuid
from sqlalchemy import Boolean, Column, Date, Numeric, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base
from app.models.group import FYPCycleEnum  # existing enum (“fyp1”, “fyp2”)


class AdminMilestone(Base):
    __tablename__ = "admin_milestone"

    milestone_id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    admin_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("admins.user_id"),
        nullable=True,
    )
    title = Column(Text, nullable=False)
    weightage = Column(Numeric, nullable=True)
    due_date = Column(Date, nullable=True)
    evaluator = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="false")
    activated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    marks_visible_to_students = Column(Boolean, nullable=False, server_default="false")
    fyp_cycle = Column(
        SQLEnum(FYPCycleEnum, name="fyp_cycle_enum", create_type=False),
        nullable=False,
        default=FYPCycleEnum.fyp1,
    )
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    admin = relationship("Admin", backref="milestones")
    evaluations = relationship(
        "SupervisorEvaluation",
        back_populates="milestone",
        cascade="all, delete-orphan",
    )