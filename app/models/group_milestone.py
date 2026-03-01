import enum
import uuid

from sqlalchemy import Column, Date, ForeignKey, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class SprintStatusEnum(str, enum.Enum):
    Planned = "Planned"
    Active = "Active"
    Completed = "Completed"


class GroupMilestone(Base):
    __tablename__ = "group_milestones"

    milestone_id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    group_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.group_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(Text, nullable=False)
    sprint_goal = Column(Text, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    status = Column(
        SQLEnum(SprintStatusEnum, name="sprint_status_enum", create_type=False),
        nullable=False,
        default=SprintStatusEnum.Planned,
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

    group = relationship("Group", back_populates="milestones")
    tasks = relationship(
        "Task",
        back_populates="milestone",
        cascade="all, delete-orphan",
    )
