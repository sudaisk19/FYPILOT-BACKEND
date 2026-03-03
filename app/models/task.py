# app/models/task.py
import enum
import uuid
from sqlalchemy import Column, Date, ForeignKey, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class TaskPriorityEnum(str, enum.Enum):
    Low = "Low"
    Medium = "Medium"
    High = "High"
    Critical = "Critical"


class TaskStatusEnum(str, enum.Enum):
    ToDo = "ToDo"
    InProgress = "InProgress"
    Review = "Review"
    Done = "Done"
    Blocked = "Blocked"


class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(
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
    milestone_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("group_milestones.milestone_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assignee_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("students.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(
        SQLEnum(TaskPriorityEnum, name="task_priority_enum", create_type=False),
        nullable=False,
        default=TaskPriorityEnum.Medium,
    )
    status = Column(
        SQLEnum(TaskStatusEnum, name="task_status_enum", create_type=False),
        nullable=False,
        default=TaskStatusEnum.ToDo,
    )
    due_date = Column(Date, nullable=True)
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    group = relationship("Group", back_populates="tasks")
    milestone = relationship("GroupMilestone", back_populates="tasks")
    assignee = relationship("Student", back_populates="tasks")
    attachments = relationship(
        "TaskAttachment",
        back_populates="task",
        cascade="all, delete-orphan",
    )