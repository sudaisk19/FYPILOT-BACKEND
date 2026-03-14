# app/models/__init__.py

# Import all models to ensure they are registered with SQLAlchemy
# Import order matters to avoid circular import issues

from .admin import Admin

# Submission and Announcement models
from .announcement import (
    AnnouncementFile,
    AnnouncementRoleEnum,
    AnnouncementTarget,
    TargetRoleEnum,
)

# Bulk import models
from .bulk_import import (
    BulkImportItem,
    BulkImportJob,
    BulkItemStatus,
    BulkJobStatus,
)

# Domain and Industry models (base models)
from .domain import Domain
from .faculty import Faculty

# Faculty relationship models (junction tables)
from .faculty_domain import FacultyDomain
from .faculty_industry import FacultyIndustry

# Group models (depend on User and Student)
from .group import Group, GroupInvite, GroupMember
from .group_milestone import GroupMilestone, SprintStatusEnum
from .industry import Industry

# Jury Assignment models
from .jury_assignment import JuryAssignment, JuryAssignmentBatch, JuryBatchStatusEnum
from .jury_pair import JuryPair

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
from .supervisor_evaluation import SupervisorEvaluation
from .task import Task, TaskPriorityEnum, TaskStatusEnum
from .task_attachment import TaskAttachment

# Base models first
from .user import RoleEnum, User

# Milestone Model


# Export all models
__all__ = [
    "User",
    "RoleEnum",
    "Student",
    "Faculty",
    "Admin",
    "Group",
    "GroupMember",
    "GroupInvite",
    "Request",
    "RequestTypeEnum",
    "ShortlistedSupervisor",
    "Project",
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
    "TargetRoleEnum",
    "Submission",
    "SubmissionFile",
    "SubmissionTypeEnum",
    "SubmissionStatusEnum",
    "Domain",
    "Industry",
    "FacultyDomain",
    "FacultyIndustry",
    "PasswordResetToken",
    # Bulk import models
    "BulkImportJob",
    "BulkImportItem",
    "BulkJobStatus",
    "BulkItemStatus",
    # Jury models
    "JuryPair",
    "JuryAssignment",
    "JuryAssignmentBatch",
    "JuryBatchStatusEnum",
]
