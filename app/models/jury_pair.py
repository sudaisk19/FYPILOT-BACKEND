import uuid

from sqlalchemy import TIMESTAMP, CheckConstraint, Column, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class JuryPair(Base):
    """Represents a pair of faculty members acting as a jury unit."""

    __tablename__ = "jury_pairs"

    jury_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    faculty_1_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("faculty.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    faculty_2_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("faculty.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    jury_number = Column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "faculty_1_id <> faculty_2_id", name="jury_pairs_diff_supervisors"
        ),
    )

    assignments = relationship(
        "JuryAssignment",
        back_populates="pair",
        cascade="all, delete-orphan",
    )
