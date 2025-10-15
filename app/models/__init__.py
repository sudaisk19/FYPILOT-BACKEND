# app/models/__init__.py

# Import all models to ensure they are registered with SQLAlchemy
# Import order matters to avoid circular import issues

from .admin import Admin

# Group models (depend on User and Student)
from .group import Group, GroupInvite, GroupMember

# Other models
from .password_reset import PasswordResetToken

# Profile models (depend on User)
from .student import Student
from .supervisor import Supervisor

# Base models first
from .user import RoleEnum, User

# Export all models
__all__ = [
    "User",
    "RoleEnum",
    "Student",
    "Supervisor",
    "Admin",
    "Group",
    "GroupMember",
    "GroupInvite",
    "PasswordResetToken",
]
