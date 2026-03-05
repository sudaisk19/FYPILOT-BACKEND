import enum
import uuid

from sqlalchemy import TIMESTAMP, Column
from sqlalchemy import Enum as SAEnum
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


# Must match your Postgres enum "user_role_enum"
class RoleEnum(str, enum.Enum):
    student = "student"
    faculty = "faculty"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    user_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(
        SAEnum(RoleEnum, name="user_role_enum", native_enum=True), nullable=False
    )
    profile_avatar = Column(Text, nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 1-to-1 profiles (PK=FK to users.user_id)
    student_profile = relationship(
        "Student", uselist=False, back_populates="user", cascade="all, delete-orphan"
    )
    faculty_profile = relationship(
        "Faculty", uselist=False, back_populates="user", cascade="all, delete-orphan"
    )
    admin_profile = relationship(
        "Admin", uselist=False, back_populates="user", cascade="all, delete-orphan"
    )
