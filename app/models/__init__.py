# app/models/__init__.py

# Import all models to ensure they are registered with SQLAlchemy
# Import order matters to avoid circular import issues

from .admin import Admin

# Domain and Industry models (base models)
from .domain import Domain

# Group models (depend on User and Student)
from .group import Group, GroupInvite, GroupMember
from .industry import Industry

# Other models
from .password_reset import PasswordResetToken

# Project models (depend on Group, Domain, Industry)
from .project import Project, ProjectDomain

# Profile models (depend on User)
from .student import Student
from .supervisor import Supervisor

# Supervisor relationship models (junction tables)
from .supervisor_domain import SupervisorDomain
from .supervisor_industry import SupervisorIndustry

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
    "Project",
    "ProjectDomain",
    "Domain",
    "Industry",
    "SupervisorDomain",
    "SupervisorIndustry",
    "PasswordResetToken",
]
