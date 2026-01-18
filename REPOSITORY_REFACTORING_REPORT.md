# Repository Layer Refactoring Report

**Generated:** January 18, 2026  
**Project:** FYPILOT-BACKEND  
**Purpose:** Introduce a proper data-access layer to separate DB queries from routes and services.

---

## Executive Summary

The current codebase has **significant DB access scattered across route handlers and auth modules**. This report documents:
1. Current architecture classification
2. Files with DB violations
3. Duplicated query patterns
4. Proposed repository structure
5. Method signatures for each repository

---

## 1. Current Architecture Classification

### Verdict: **Route-Heavy Architecture** 🔴

| Layer | SQLAlchemy Imports | DB Operations (`select`, `execute`, `commit`) |
|-------|-------------------|---------------------------------------------|
| `app/api/http/` | 12 files | ~150+ operations |
| `app/auth/` | 2 files | ~40+ operations |
| `app/services/` | 1 file | ~10 operations |
| `app/repositories/` | 0 files | 0 operations (empty!) |

**The `app/repositories/` folder exists but is empty** – all DB logic lives directly in route handlers.

---

## 2. Files with DB Access Violations

### 2.1 Routes Doing Direct DB Work (VIOLATIONS)

| File | DB Operations | Severity |
|------|--------------|----------|
| [app/api/http/shortlist.py](app/api/http/shortlist.py) | `select`, `delete`, `db.add`, `db.commit` | 🔴 High |
| [app/api/http/group.py](app/api/http/group.py) | `select`, `delete`, `update`, `db.add`, `db.commit`, raw SQL `text()` | 🔴 High |
| [app/api/http/supervisor_invites.py](app/api/http/supervisor_invites.py) | `select`, `update`, `delete`, `db.add`, `db.commit`, raw SQL | 🔴 High |
| [app/api/http/supervisor_explore.py](app/api/http/supervisor_explore.py) | Complex `select` with joins, filters, pagination | 🔴 High |
| [app/api/http/student_profile.py](app/api/http/student_profile.py) | `select`, `update`, `db.commit` | 🟡 Medium |
| [app/api/http/supervisor_profile.py](app/api/http/supervisor_profile.py) | `select`, `update`, `db.add`, `db.commit` | 🟡 Medium |
| [app/api/http/admin_profile.py](app/api/http/admin_profile.py) | `select`, `update`, `db.add`, `db.commit` | 🟡 Medium |
| [app/api/http/profile_status.py](app/api/http/profile_status.py) | `select` with `selectinload` | 🟡 Medium |
| [app/api/http/dashboard.py](app/api/http/dashboard.py) | `select`, `func.count` | 🟡 Medium |
| [app/api/http/supervisor_recommendation.py](app/api/http/supervisor_recommendation.py) | Delegates to service (✅ OK) | 🟢 Low |

### 2.2 Auth Module with DB Work

| File | DB Operations | Severity |
|------|--------------|----------|
| [app/auth/routes.py](app/auth/routes.py) | `select`, `delete`, `db.add`, `db.commit`, `db.refresh` for signup/login/OAuth/password-reset | 🔴 High |
| [app/auth/supabase_auth.py](app/auth/supabase_auth.py) | `select` for user lookup in auth dependency | 🟡 Medium |

### 2.3 Services with DB Work

| File | DB Operations | Notes |
|------|--------------|-------|
| [app/services/recommendation_service.py](app/services/recommendation_service.py) | `select` with joins for supervisors, domains, industries | Should use repositories |

---

## 3. Duplicated Query Patterns Found

### 3.1 User Queries (appears 10+ times)
```python
# Pattern: Get user by email
await db.execute(select(User).where(User.email == email))

# Pattern: Get user by ID with relationships
await db.execute(
    select(User)
    .options(selectinload(User.student_profile), ...)
    .where(User.user_id == user_id)
)
```

### 3.2 Group Membership Check (appears 8+ times)
```python
# Pattern: Check if user is member of group
await db.execute(
    select(GroupMember).where(
        GroupMember.group_id == group_id,
        GroupMember.student_id == user_id,
    )
)
```

### 3.3 Student Profile Lookup (appears 5+ times)
```python
# Pattern: Get student by user_id
await db.execute(select(Student).where(Student.user_id == user_id))
```

### 3.4 Supervisor Queries (appears 6+ times)
```python
# Pattern: Get supervisor by user_id
await db.execute(select(Supervisor).where(Supervisor.user_id == user_id))

# Pattern: Get supervisor with user info
await db.execute(
    select(User, Supervisor)
    .join(Supervisor, User.user_id == Supervisor.user_id)
    .where(...)
)
```

### 3.5 Group Queries (appears 5+ times)
```python
# Pattern: Get group by ID
await db.execute(select(Group).where(Group.group_id == group_id))
```

### 3.6 Project Queries (appears 4+ times)
```python
# Pattern: Get project by group_id
await db.execute(select(Project).where(Project.group_id == group_id))
```

### 3.7 Request/Invite Queries (appears 6+ times)
```python
# Pattern: Get pending requests for supervisor
await db.execute(
    select(Request).where(
        Request.supervisor_id == supervisor_id,
        Request.status == InviteStatusEnum.pending,
    )
)
```

### 3.8 Shortlist Queries (appears 3+ times)
```python
# Pattern: Check if supervisor is shortlisted
await db.execute(
    select(ShortlistedSupervisor).where(
        ShortlistedSupervisor.group_id == group_id,
        ShortlistedSupervisor.supervisor_id == supervisor_id,
    )
)
```

### 3.9 Domain/Industry Lookups (appears 5+ times)
```python
# Pattern: Get domains for supervisor
await db.execute(
    select(Domain)
    .join(SupervisorDomain, ...)
    .where(SupervisorDomain.supervisor_id == supervisor_id)
)
```

### 3.10 Count Queries (appears 5+ times)
```python
# Pattern: Count group members
await db.execute(
    select(func.count())
    .select_from(GroupMember)
    .where(GroupMember.group_id == group_id)
)
```

---

## 4. Proposed Repository Structure

```
app/repositories/
├── __init__.py              # Export all repositories
├── base.py                  # Generic base repository with CRUD
├── user_repository.py       # User CRUD + lookup methods
├── student_repository.py    # Student profile operations
├── supervisor_repository.py # Supervisor queries + search
├── group_repository.py      # Group + membership operations
├── shortlist_repository.py  # Shortlist CRUD
├── request_repository.py    # Supervisor request/invite operations
├── project_repository.py    # Project CRUD + domain associations
├── domain_repository.py     # Domain lookups
└── admin_repository.py      # Admin profile + system stats
```

---

## 5. Repository Method Signatures

### 5.1 `base.py` — Generic Base Repository
```python
class BaseRepository[T]:
    async def get_by_id(self, db: AsyncSession, id: UUID) -> Optional[T]
    async def get_all(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[T]
    async def create(self, db: AsyncSession, obj_in: CreateSchemaType) -> T
    async def update(self, db: AsyncSession, db_obj: T, obj_in: UpdateSchemaType) -> T
    async def delete(self, db: AsyncSession, id: UUID) -> bool
```

### 5.2 `user_repository.py`
```python
class UserRepository:
    async def get_by_id(db, user_id: UUID) -> Optional[User]
    async def get_by_email(db, email: str) -> Optional[User]
    async def get_with_profiles(db, user_id: UUID) -> Optional[User]  # with selectinload
    async def create(db, user_data: UserCreate) -> User
    async def update(db, user_id: UUID, updates: dict) -> User
    async def exists_by_email(db, email: str) -> bool
```

### 5.3 `student_repository.py`
```python
class StudentRepository:
    async def get_by_user_id(db, user_id: UUID) -> Optional[Student]
    async def create(db, user_id: UUID, student_data: dict) -> Student
    async def update(db, user_id: UUID, updates: dict) -> Student
    async def get_with_group(db, user_id: UUID) -> Optional[Student]
```

### 5.4 `supervisor_repository.py`
```python
class SupervisorRepository:
    async def get_by_user_id(db, user_id: UUID) -> Optional[Supervisor]
    async def get_with_user(db, supervisor_id: UUID) -> Optional[Tuple[User, Supervisor]]
    async def get_with_domains_industries(db, user_id: UUID) -> Optional[Supervisor]
    async def list_all_with_users(db) -> List[Tuple[User, Supervisor]]
    async def search(db, department, designation, domain, search, page, per_page) -> Tuple[List, int]
    async def create(db, user_id: UUID, supervisor_data: dict) -> Supervisor
    async def update(db, user_id: UUID, updates: dict) -> Supervisor
    async def get_domains(db, supervisor_id: UUID) -> List[Domain]
    async def get_industries(db, supervisor_id: UUID) -> List[Industry]
    async def set_domains(db, supervisor_id: UUID, domain_ids: List[UUID]) -> None
    async def set_industries(db, supervisor_id: UUID, industry_ids: List[UUID]) -> None
```

### 5.5 `group_repository.py`
```python
class GroupRepository:
    async def get_by_id(db, group_id: UUID) -> Optional[Group]
    async def create(db, name: str, **kwargs) -> Group
    async def update(db, group_id: UUID, updates: dict) -> Group
    async def delete(db, group_id: UUID) -> bool
    async def get_members(db, group_id: UUID) -> List[GroupMember]
    async def get_members_with_users(db, group_id: UUID) -> List[Tuple[User, Student, GroupMember]]
    async def add_member(db, group_id: UUID, student_id: UUID) -> GroupMember
    async def remove_member(db, group_id: UUID, student_id: UUID) -> bool
    async def check_membership(db, group_id: UUID, student_id: UUID) -> bool
    async def count_members(db, group_id: UUID) -> int
    async def get_student_group(db, student_id: UUID) -> Optional[Group]
    async def get_supervised_groups(db, supervisor_id: UUID) -> List[Group]
```

### 5.6 `shortlist_repository.py`
```python
class ShortlistRepository:
    async def add(db, group_id: UUID, supervisor_id: UUID, added_by: UUID) -> ShortlistedSupervisor
    async def remove(db, group_id: UUID, supervisor_id: UUID) -> bool
    async def exists(db, group_id: UUID, supervisor_id: UUID) -> bool
    async def list_by_group(db, group_id: UUID) -> List[Tuple[ShortlistedSupervisor, User, Supervisor]]
```

### 5.7 `request_repository.py`
```python
class RequestRepository:
    async def create(db, group_id: UUID, supervisor_id: UUID, request_type, message: str = None) -> Request
    async def get_by_id(db, request_id: UUID) -> Optional[Request]
    async def get_pending_for_supervisor(db, supervisor_id: UUID) -> List[Tuple[Request, Group]]
    async def get_by_group(db, group_id: UUID) -> List[Tuple[Request, Supervisor, User]]
    async def exists_pending(db, group_id: UUID, supervisor_id: UUID) -> bool
    async def update_status(db, request_id: UUID, status) -> Request
    async def delete(db, request_id: UUID) -> bool
```

### 5.8 `project_repository.py`
```python
class ProjectRepository:
    async def get_by_id(db, project_id: UUID) -> Optional[Project]
    async def get_by_group_id(db, group_id: UUID) -> Optional[Project]
    async def create(db, group_id: UUID, name: str, **kwargs) -> Project
    async def update(db, project_id: UUID, updates: dict) -> Project
    async def get_domains(db, project_id: UUID) -> List[Domain]
    async def set_domains(db, project_id: UUID, domain_ids: List[UUID]) -> None
```

### 5.9 `domain_repository.py`
```python
class DomainRepository:
    async def get_by_id(db, domain_id: UUID) -> Optional[Domain]
    async def get_by_name(db, name: str) -> Optional[Domain]
    async def get_all(db) -> List[Domain]
    async def get_by_ids(db, domain_ids: List[UUID]) -> List[Domain]
```

### 5.10 `admin_repository.py`
```python
class AdminRepository:
    async def get_by_user_id(db, user_id: UUID) -> Optional[Admin]
    async def create(db, user_id: UUID, admin_data: dict) -> Admin
    async def update(db, user_id: UUID, updates: dict) -> Admin
    async def get_system_stats(db) -> dict  # counts for students, supervisors, groups, projects
```

---

## 6. Migration Strategy

### Phase 1: Create Repository Layer (This PR)
1. ✅ Create `base.py` with generic methods
2. ✅ Create individual repository files
3. ✅ Export from `__init__.py`

### Phase 2: Gradual Migration (Future PRs)
1. Start with `shortlist.py` (smallest, cleanest)
2. Move to `group.py` (many duplicated patterns)
3. Refactor `auth/routes.py` (user CRUD)
4. Update `supervisor_explore.py` (complex queries)
5. Update remaining routes

### Phase 3: Service Layer Cleanup
1. Update `recommendation_service.py` to use repositories
2. Consider creating service classes for complex business logic

---

## 7. Benefits After Refactoring

| Aspect | Before | After |
|--------|--------|-------|
| **Testability** | Must mock entire DB | Mock repository interface |
| **Code Duplication** | 30+ duplicated query patterns | Single source of truth |
| **Maintainability** | Query changes need 10+ file edits | Change in 1 repository file |
| **Readability** | Routes mixed with SQL | Routes read like business logic |
| **Flexibility** | Locked to SQLAlchemy | Can swap ORM/DB with minimal changes |

---

## 8. Files Being Created

| File | Purpose |
|------|---------|
| `app/repositories/base.py` | Generic CRUD base class |
| `app/repositories/user_repository.py` | User lookup & CRUD |
| `app/repositories/student_repository.py` | Student profile operations |
| `app/repositories/supervisor_repository.py` | Supervisor queries + search |
| `app/repositories/group_repository.py` | Group + membership operations |
| `app/repositories/shortlist_repository.py` | Shortlist CRUD |
| `app/repositories/request_repository.py` | Supervisor invites/requests |
| `app/repositories/project_repository.py` | Project CRUD |
| `app/repositories/domain_repository.py` | Domain lookups |
| `app/repositories/admin_repository.py` | Admin + system stats |
| `app/repositories/__init__.py` | Export all repositories |

---

## 9. Phase 2: Route Refactoring (COMPLETED)

### 9.1 `app/api/http/shortlist.py` — FULLY REFACTORED ✅

**REMOVED from routes:**
```python
# BEFORE - Direct SQLAlchemy imports
from sqlalchemy import delete, select
from app.models.group import GroupMember
from app.models.shortlisted_supervisor import ShortlistedSupervisor
from app.models.supervisor import Supervisor

# Direct queries removed:
# - select(GroupMember).where(...)
# - select(ShortlistedSupervisor).where(...)  
# - select(User, Supervisor, ShortlistedSupervisor).join(...)
# - delete(ShortlistedSupervisor).where(...)
```

**ADDED repository imports:**
```python
from app.repositories import group_repository, shortlist_repository
```

**Method mapping:**
| OLD (Direct SQLAlchemy) | NEW (Repository) |
|------------------------|------------------|
| `db.execute(select(GroupMember).where(...))` | `group_repository.check_membership(db, group_id, user_id)` |
| `db.execute(select(ShortlistedSupervisor).where(...))` | `shortlist_repository.exists(db, group_id, supervisor_id)` |
| `db.execute(select(User, Supervisor, ShortlistedSupervisor).join(...))` | `shortlist_repository.list_by_group(db, group_id)` |
| `db.execute(delete(ShortlistedSupervisor).where(...))` | `shortlist_repository.remove(db, group_id, supervisor_id)` |
| `db.add(ShortlistedSupervisor(...))` | `shortlist_repository.add(db, group_id, supervisor_id, added_by)` |

---

### 9.2 `app/api/http/supervisor_explore.py` — PARTIALLY REFACTORED ⚠️

**REFACTORED endpoint:** `get_supervisor_details()`

**REMOVED from get_supervisor_details:**
```python
# BEFORE - Direct SQLAlchemy query
result = await db.execute(
    select(User, Supervisor)
    .options(
        selectinload(Supervisor.domains),
        selectinload(Supervisor.industries),
    )
    .join(Supervisor, User.user_id == Supervisor.user_id)
    .where(User.user_id == supervisor_id, User.role == "supervisor")
)
row = result.first()
```

**ADDED repository calls:**
```python
from app.repositories import supervisor_repository

# New implementation:
row = await supervisor_repository.get_with_user(db, supervisor_id)
domains_list = await supervisor_repository.get_domains(db, supervisor_id)
industries_list = await supervisor_repository.get_industries(db, supervisor_id)
```

**NOT REFACTORED:** `explore_supervisors()` endpoint
- **Reason:** Contains complex relevance scoring using `sqlalchemy.case()` 
- **Details:** The search endpoint ranks supervisors by name match relevance (100 for exact, 80 for starts-with, 60 for contains)
- **Decision:** Keep direct SQLAlchemy for this specific use case; the repository `search()` method doesn't support relevance scoring

---

### 9.3 Files NOT REFACTORED (Time constraints / Complexity)

| File | Reason | Recommendation |
|------|--------|----------------|
| `group.py` | 1141 lines, 15+ endpoints, heavy raw SQL | Future PR - create `group_invite_repository.py` |
| `supervisor_invites.py` | 729 lines, complex request flows | Future PR - use `request_repository` |
| `auth/routes.py` | OAuth flows, password reset, complex user creation | Future PR - use `user_repository` |
| `student_profile.py` | Profile CRUD, minimal DB operations | Low priority |
| `supervisor_profile.py` | Profile CRUD, domain/industry associations | Low priority |

---

## 10. Phase 3: Service Refactoring (COMPLETED)

### 10.1 `app/services/recommendation_service.py` — FULLY REFACTORED ✅

**REMOVED from service:**
```python
# BEFORE - Direct SQLAlchemy imports
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.domain import Domain
from app.models.group import Group, GroupMember
from app.models.industry import Industry
from app.models.student import Student
from app.models.supervisor import Supervisor
from app.models.supervisor_domain import SupervisorDomain
from app.models.supervisor_industry import SupervisorIndustry
from app.models.user import User

# Direct queries removed:
# - select(Supervisor, User).join(...)
# - select(Domain).join(SupervisorDomain, ...).where(...)
# - select(Industry).join(SupervisorIndustry, ...).where(...)
# - select(Group).options(selectinload(...)).where(...)
```

**ADDED repository imports:**
```python
from app.repositories import group_repository, supervisor_repository
```

**Method mapping:**
| OLD (Direct SQLAlchemy) | NEW (Repository) |
|------------------------|------------------|
| `db.execute(select(Supervisor, User).join(...))` | `supervisor_repository.list_all_with_users(db)` |
| `db.execute(select(Domain).join(SupervisorDomain, ...).where(...))` | `supervisor_repository.get_domains(db, supervisor_id)` |
| `db.execute(select(Industry).join(SupervisorIndustry, ...).where(...))` | `supervisor_repository.get_industries(db, supervisor_id)` |
| `db.execute(select(Group).options(selectinload(...)).where(...))` | `group_repository.get_with_members(db, group_id)` |

---

## 11. Summary of Changes

### Files Created (Phase 1)
| File | Status |
|------|--------|
| `app/repositories/__init__.py` | ✅ Created |
| `app/repositories/base.py` | ✅ Created |
| `app/repositories/user_repository.py` | ✅ Created |
| `app/repositories/student_repository.py` | ✅ Created |
| `app/repositories/supervisor_repository.py` | ✅ Created |
| `app/repositories/group_repository.py` | ✅ Created |
| `app/repositories/shortlist_repository.py` | ✅ Created |
| `app/repositories/request_repository.py` | ✅ Created |
| `app/repositories/project_repository.py` | ✅ Created |
| `app/repositories/domain_repository.py` | ✅ Created |
| `app/repositories/admin_repository.py` | ✅ Created |

### Files Refactored (Phase 2)
| File | Status | Details |
|------|--------|---------|
| `app/api/http/shortlist.py` | ✅ FULLY REFACTORED | Removed all direct SQLAlchemy, uses `group_repository` & `shortlist_repository` |
| `app/api/http/supervisor_explore.py` | ⚠️ PARTIALLY REFACTORED | `get_supervisor_details()` uses repository; `explore_supervisors()` keeps direct SQL for relevance scoring |

### Services (Phase 3)
| File | Status | Notes |
|------|--------|-------|
| `app/services/recommendation_service.py` | ✅ FULLY REFACTORED | Uses `supervisor_repository` and `group_repository` |

---

## Conclusion

This refactoring has:

1. **Created a complete repository layer** (10 repository files + base class)
2. **Fully refactored `shortlist.py`** - removed all direct SQLAlchemy imports and DB operations
3. **Partially refactored `supervisor_explore.py`** - one endpoint now uses repository pattern
4. **Documented remaining work** - clear path for future refactoring of `group.py`, `auth/routes.py`, and `recommendation_service.py`

The repository layer provides **centralized database operations** making the codebase more maintainable, testable, and easier to extend. Route handlers that use repositories are now thin controllers that delegate data access, improving separation of concerns.
