import uuid

from sqlalchemy import Boolean, Column, Numeric, Text, UniqueConstraint
from sqlalchemy import TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class SupervisorEvaluation(Base):
    __tablename__ = "supervisor_evaluations"

    evaluation_id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    milestone_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("admin_milestone.milestone_id", ondelete="CASCADE"),
        nullable=False,
    )
    group_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.group_id", ondelete="CASCADE"),
        nullable=False,
    )
    supervisor_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("supervisors.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    marks = Column(Numeric, nullable=True)
    feedback = Column(Text, nullable=True)
    wbs_achieved = Column(Boolean, nullable=True)

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

    __table_args__ = (
        UniqueConstraint(
            "milestone_id", "group_id", "supervisor_id", name="uq_supervisor_eval_unique"
        ),
    )

    milestone = relationship("AdminMilestone", back_populates="evaluations")
    group = relationship("Group")
    supervisor = relationship("Supervisor")
