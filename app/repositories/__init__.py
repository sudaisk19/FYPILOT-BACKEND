# app/repositories/__init__.py
"""
Repository Layer

This module exports all repository classes and singleton instances
for database operations. Repositories provide a clean abstraction
over SQLAlchemy queries, enabling:

- Separation of concerns (routes don't do DB work)
- Testability (mock repositories instead of DB)
- Consistency (centralized query patterns)
- Maintainability (change queries in one place)

Usage:
    from app.repositories import user_repository, group_repository

    # In a route or service:
    user = await user_repository.get_by_email(db, email)
    group = await group_repository.get_by_id(db, group_id)
"""

# Repository classes
from .admin_repository import AdminRepository, admin_repository

# Base repository
from .announcement_repository import AnnouncementRepository, announcement_repository
from .base import BaseRepository
from .domain_repository import DomainRepository, domain_repository
from .group_repository import GroupRepository, group_repository
from .project_repository import ProjectRepository, project_repository
from .request_repository import RequestRepository, request_repository
from .shortlist_repository import ShortlistRepository, shortlist_repository
from .student_repository import StudentRepository, student_repository
from .supervisor_repository import SupervisorRepository, supervisor_repository
from .user_repository import UserRepository, user_repository

__all__ = [
    # Base
    "BaseRepository",
    # Classes (for type hints and custom instantiation)
    "AnnouncementRepository",
    "UserRepository",
    "StudentRepository",
    "SupervisorRepository",
    "GroupRepository",
    "ShortlistRepository",
    "RequestRepository",
    "ProjectRepository",
    "DomainRepository",
    "AdminRepository",
    # Singleton instances (for convenience)
    "announcement_repository",
    "user_repository",
    "student_repository",
    "supervisor_repository",
    "group_repository",
    "shortlist_repository",
    "request_repository",
    "project_repository",
    "domain_repository",
    "admin_repository",
]
