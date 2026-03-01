# app/models/__init__.py

# Import all models to ensure they are registered with SQLAlchemy
# Import order matters to avoid circular import issues

from .admin import Admin

# Submission and Announcement models
from .announcement import (
    AnnouncementFile,
    AnnouncementRoleEnum,
    AnnouncementTarget,
)

# Bulk import models
from .bulk_import import (
    BulkImportItem,
    BulkImportJob,
    BulkItemStatus,
    BulkJobStatus,
    TargetRoleEnum,
)

# Domain and Industry models (base models)
from .domain import Domain

# Group models (depend on User and Student)
from .group import Group, GroupInvite, GroupMember
from .group_milestone import GroupMilestone, SprintStatusEnum
from .industry import Industry

# Other models
from .password_reset import PasswordResetToken

# Project models (depend on Group, Domain, Industry)
from .project import Project, ProjectDomain

# Request and Shortlist models
from .request import Request, RequestTypeEnum
from .shortlisted_supervisor import ShortlistedSupervisor

# Profile models (depend on User)
from .student import Student
from .submission import (
    Submission,
    SubmissionFile,
    SubmissionStatusEnum,
    SubmissionTypeEnum,
)
from .supervisor import Supervisor
from .task import Task, TaskPriorityEnum, TaskStatusEnum
from .task_attachment import TaskAttachment
from .supervisor_evaluation import SupervisorEvaluation

# Supervisor relationship models (junction tables)
from .supervisor_domain import SupervisorDomain
from .supervisor_industry import SupervisorIndustry

# Base models first
from .user import RoleEnum, User

# Milestone Model

# Jury Assignment models


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
    "Request",
    "RequestTypeEnum",
    "ShortlistedSupervisor",
    "Project",
    "ProjectDomain",
    "ProjectDomain",
    "AdminMilestone",
    "GroupMilestone",
    "SprintStatusEnum",
    "Task",
    "TaskPriorityEnum",
    "TaskStatusEnum",
    "TaskAttachment",
    "SupervisorEvaluation",
    # Submission and Announcement models
    "Announcement",
    "AnnouncementFile",
    "AnnouncementTarget",
    "AnnouncementRoleEnum",
    "Submission",
    "SubmissionFile",
    "SubmissionTypeEnum",
    "SubmissionStatusEnum",
    "Domain",
    "Industry",
    "SupervisorDomain",
    "SupervisorIndustry",
    "PasswordResetToken",
    # Bulk import models
    "BulkImportJob",
    "BulkImportItem",
    "BulkJobStatus",
    "BulkItemStatus",
    "TargetRoleEnum",
]
