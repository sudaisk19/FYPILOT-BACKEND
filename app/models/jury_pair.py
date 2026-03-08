# app/models/jury_pair.py

"""
Jury Pair Model.

Represents a pair of faculty members who evaluate projects together.
The AI service generates these pairs; the backend stores them.
"""

import uuid

from sqlalchemy import Column, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.db import Base


class JuryPair(Base):
    """
    A jury pair = two faculty members who evaluate projects together.

    The jury_id is the PK (matches the existing Supabase table).
    jury_number is a sequential label for display (Jury 1, Jury 2, …).
    """

    __tablename__ = "jury_pairs"

    jury_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    faculty_1_id = Column(PGUUID(as_uuid=True), nullable=False)
    faculty_2_id = Column(PGUUID(as_uuid=True), nullable=False)

    # Sequential number for display: "Jury 1", "Jury 2", etc.
    jury_number = Column(Integer, nullable=True)

    # Relationships (no FK in Supabase schema, so use primaryjoin)
    assignments = relationship(
        "JuryAssignment",
        back_populates="jury_pair",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "faculty_1_id",
            "faculty_2_id",
            name="uq_jury_pair_faculty",
        ),
    )
