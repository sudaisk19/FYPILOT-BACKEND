# app/repositories/group_repository.py
"""
Group Repository Module

Handles all database operations for the Group and GroupMember models.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.group import Group, GroupMember
from app.models.student import Student
from app.models.user import User

from .base import BaseRepository


class GroupRepository(BaseRepository[Group]):
    """Repository for Group model operations."""

    def __init__(self):
        super().__init__(Group)

    async def get_by_id(self, db: AsyncSession, group_id: UUID) -> Optional[Group]:
        """
        Get group by ID.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            Group instance or None
        """
        return await super().get_by_id(db, group_id, "group_id")

    async def get_with_members(
        self, db: AsyncSession, group_id: UUID
    ) -> Optional[Group]:
        """
        Get group with members loaded.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            Group instance with members loaded, or None
        """
        query = (
            select(Group)
            .options(
                selectinload(Group.members)
                .selectinload(GroupMember.student)
                .selectinload(Student.user)
            )
            .where(Group.group_id == group_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def get_with_project(
        self, db: AsyncSession, group_id: UUID
    ) -> Optional[Group]:
        """
        Get group with project loaded.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            Group instance with project loaded, or None
        """
        query = (
            select(Group)
            .options(selectinload(Group.project))
            .where(Group.group_id == group_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        name: str,
        fyp_stage: Optional[str] = None,
        fyp_cycle: Optional[str] = None,
        cohort_year: Optional[int] = None,
    ) -> Group:
        """
        Create a new group.

        Args:
            db: Database session
            name: Group name
            fyp_stage: FYP stage enum value
            fyp_cycle: FYP cycle enum value
            cohort_year: Cohort year

        Returns:
            Created Group instance
        """
        from app.models.group import FYPCycleEnum, FYPStageEnum

        group_data = {
            "name": name,
            "created_at": datetime.utcnow(),
        }

        if fyp_stage:
            group_data["fyp_stage"] = FYPStageEnum(fyp_stage)
        else:
            group_data["fyp_stage"] = FYPStageEnum.ideation

        if fyp_cycle:
            group_data["fyp_cycle"] = FYPCycleEnum(fyp_cycle)
        else:
            group_data["fyp_cycle"] = FYPCycleEnum.fyp1

        if cohort_year:
            group_data["cohort_year"] = cohort_year

        return await super().create(db, group_data)

    async def update(
        self,
        db: AsyncSession,
        group_id: UUID,
        updates: Dict[str, Any],
    ) -> Optional[Group]:
        """
        Update group fields.

        Args:
            db: Database session
            group_id: Group's UUID
            updates: Dictionary of fields to update

        Returns:
            Updated Group instance or None if not found
        """
        group = await self.get_by_id(db, group_id)
        if not group:
            return None
        return await super().update(db, group, updates)

    async def delete(self, db: AsyncSession, group_id: UUID) -> bool:
        """
        Delete a group.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            True if deleted, False if not found
        """
        return await super().delete(db, group_id, "group_id")

    # --- Membership operations ---

    async def get_members(self, db: AsyncSession, group_id: UUID) -> List[GroupMember]:
        """
        Get all members of a group.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            List of GroupMember instances
        """
        query = select(GroupMember).where(GroupMember.group_id == group_id)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_members_with_users(
        self, db: AsyncSession, group_id: UUID
    ) -> List[Tuple[User, Student, GroupMember]]:
        """
        Get all members of a group with user and student data.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            List of (User, Student, GroupMember) tuples
        """
        query = (
            select(User, Student, GroupMember)
            .join(Student, User.user_id == Student.user_id)
            .join(GroupMember, Student.user_id == GroupMember.student_id)
            .where(GroupMember.group_id == group_id)
        )
        result = await db.execute(query)
        return list(result.all())

    async def add_member(
        self,
        db: AsyncSession,
        group_id: UUID,
        student_id: UUID,
    ) -> GroupMember:
        """
        Add a student to a group.

        Args:
            db: Database session
            group_id: Group's UUID
            student_id: Student's user ID

        Returns:
            Created GroupMember instance
        """
        member = GroupMember(
            group_id=group_id,
            student_id=student_id,
            joined_at=datetime.utcnow(),
        )
        db.add(member)
        await db.flush()
        return member

    async def remove_member(
        self,
        db: AsyncSession,
        group_id: UUID,
        student_id: UUID,
    ) -> bool:
        """
        Remove a student from a group.

        Args:
            db: Database session
            group_id: Group's UUID
            student_id: Student's user ID

        Returns:
            True if removed, False if not found
        """
        from sqlalchemy import delete

        result = await db.execute(
            delete(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.student_id == student_id,
            )
        )
        await db.flush()
        return result.rowcount > 0

    async def check_membership(
        self,
        db: AsyncSession,
        group_id: UUID,
        student_id: UUID,
    ) -> bool:
        """
        Check if a student is a member of a group.

        Args:
            db: Database session
            group_id: Group's UUID
            student_id: Student's user ID

        Returns:
            True if member, False otherwise
        """
        query = select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.student_id == student_id,
        )
        result = await db.execute(query)
        return result.scalars().first() is not None

    async def count_members(self, db: AsyncSession, group_id: UUID) -> int:
        """
        Count members in a group.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            Number of members
        """
        query = (
            select(func.count())
            .select_from(GroupMember)
            .where(GroupMember.group_id == group_id)
        )
        result = await db.execute(query)
        return result.scalar_one()

    async def get_student_group(
        self, db: AsyncSession, student_id: UUID
    ) -> Optional[Group]:
        """
        Get the group a student belongs to.

        Args:
            db: Database session
            student_id: Student's user ID

        Returns:
            Group instance or None if student is not in any group
        """
        query = (
            select(Group)
            .join(GroupMember, Group.group_id == GroupMember.group_id)
            .where(GroupMember.student_id == student_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def get_student_membership(
        self, db: AsyncSession, student_id: UUID
    ) -> Optional[GroupMember]:
        """
        Get the membership record for a student.

        Args:
            db: Database session
            student_id: Student's user ID

        Returns:
            GroupMember instance or None
        """
        query = select(GroupMember).where(GroupMember.student_id == student_id)
        result = await db.execute(query)
        return result.scalars().first()

    async def is_student_in_any_group(self, db: AsyncSession, student_id: UUID) -> bool:
        """
        Check if a student is in any group.

        Args:
            db: Database session
            student_id: Student's user ID

        Returns:
            True if in a group, False otherwise
        """
        membership = await self.get_student_membership(db, student_id)
        return membership is not None

    async def get_supervised_groups(
        self,
        db: AsyncSession,
        supervisor_id: UUID,
    ) -> List[Group]:
        """
        Get all groups supervised by a supervisor (as main or co-supervisor).

        Args:
            db: Database session
            supervisor_id: Supervisor's user ID

        Returns:
            List of Group instances
        """
        query = select(Group).where(
            or_(
                Group.supervisor_id == supervisor_id,
                Group.cosupervisor_ids.contains([supervisor_id]),
            )
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def set_supervisor(
        self,
        db: AsyncSession,
        group_id: UUID,
        supervisor_id: UUID,
    ) -> Optional[Group]:
        """
        Set the main supervisor for a group.

        Args:
            db: Database session
            group_id: Group's UUID
            supervisor_id: Supervisor's user ID

        Returns:
            Updated Group instance or None
        """
        return await self.update(db, group_id, {"supervisor_id": supervisor_id})

    async def set_cosupervisor(
        self,
        db: AsyncSession,
        group_id: UUID,
        cosupervisor_id: UUID,
    ) -> Optional[Group]:
        """
        Set the co-supervisor for a group.

        Args:
            db: Database session
            group_id: Group's UUID
            cosupervisor_id: Co-supervisor's user ID

        Returns:
            Updated Group instance or None
        """
        group = await self.get_by_id(db, group_id)
        if not group:
            return None

        # If the array doesn't exist, start a new one
        current_ids = list(group.cosupervisor_ids) if group.cosupervisor_ids else []
        if cosupervisor_id not in current_ids:
            current_ids.append(cosupervisor_id)

        return await self.update(db, group_id, {"cosupervisor_ids": current_ids})

    async def get_managed_group(
        self, db: AsyncSession, supervisor_id: UUID, group_id: UUID
    ) -> Optional[Group]:
        """Get a group managed by a specific supervisor or cosupervisor."""
        query = select(Group).where(
            Group.group_id == group_id,
            or_(
                Group.supervisor_id == supervisor_id,
                Group.cosupervisor_ids.contains([supervisor_id]),
            ),
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_jury_assigned_group(
        self, db: AsyncSession, jury_id: UUID, group_id: UUID
    ) -> Optional[Group]:
        """Get a group assigned to a specific jury member."""
        from app.models.jury_assignment import JuryAssignment
        from app.models.jury_pair import JuryPair
        from app.models.project import Project

        query = (
            select(Group)
            .join(Project, Project.group_id == Group.group_id)
            .join(JuryAssignment, JuryAssignment.project_id == Project.project_id)
            .join(JuryPair, JuryPair.jury_id == JuryAssignment.pair_id)
            .where(
                Group.group_id == group_id,
                or_(
                    JuryPair.faculty_1_id == jury_id,
                    JuryPair.faculty_2_id == jury_id,
                ),
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_jury_assigned_groups(
        self, db: AsyncSession, jury_id: UUID, fyp_cycle
    ) -> List[Tuple[Group, Any]]:
        """List all groups and their projects assigned to a jury for a specific FYP cycle."""
        from app.models.jury_assignment import JuryAssignment
        from app.models.jury_pair import JuryPair
        from app.models.project import Project

        query = (
            select(Group, Project)
            .join(Project, Project.group_id == Group.group_id)
            .join(JuryAssignment, JuryAssignment.project_id == Project.project_id)
            .join(JuryPair, JuryPair.jury_id == JuryAssignment.pair_id)
            .where(
                Group.fyp_cycle == fyp_cycle,
                or_(
                    JuryPair.faculty_1_id == jury_id,
                    JuryPair.faculty_2_id == jury_id,
                ),
            )
            .order_by(Project.name.asc())
        )
        result = await db.execute(query)
        return result.all()

    async def get_group_members_basic_info(
        self, db: AsyncSession, group_ids: List[UUID]
    ) -> List[Any]:
        """Fetch basic member info (full_name, roll_number) for multiple group IDs."""
        query = (
            select(
                GroupMember.group_id,
                User.full_name,
                Student.roll_number,
            )
            .join(Student, Student.user_id == GroupMember.student_id)
            .join(User, User.user_id == Student.user_id)
            .where(GroupMember.group_id.in_(group_ids))
            .order_by(Student.roll_number.asc())
        )
        result = await db.execute(query)
        return result.all()

    async def get_supervisor_assigned_groups_directory(
        self, db: AsyncSession, supervisor_id: UUID, search: Optional[str] = None
    ) -> List[Group]:
        """Fetch all groups assigned to a supervisor, with optional search filtering."""
        from sqlalchemy.types import Text as SQLText

        from app.models.project import Project

        query = (
            select(Group)
            .options(
                selectinload(Group.members)
                .joinedload(GroupMember.student)
                .joinedload(Student.user),
                selectinload(Group.project),
            )
            .outerjoin(Project, Project.group_id == Group.group_id)
            .where(Group.supervisor_id == supervisor_id)
        )

        if search:
            s = f"%{search.strip()}%"
            member_name_exists = (
                select(GroupMember.group_id)
                .join(Student, Student.user_id == GroupMember.student_id)
                .join(User, User.user_id == Student.user_id)
                .where(
                    GroupMember.group_id == Group.group_id,
                    User.full_name.ilike(s),
                )
                .correlate(Group)
                .exists()
            )

            query = query.where(
                or_(
                    Project.name.ilike(s),
                    Project.tech_stack.cast(SQLText).ilike(s),
                    member_name_exists,
                )
            )

        query = query.order_by(Group.updated_at.desc())
        result = await db.execute(query)
        return list(result.scalars().unique().all())

    async def get_supervisor_assigned_groups_dropdown(
        self, db: AsyncSession, supervisor_id: UUID
    ) -> List[Any]:
        """Fetch a lightweight list of (group_id, project_name) for a supervisor."""
        from app.models.project import Project

        query = (
            select(Group.group_id, Project.name.label("name"))
            .outerjoin(Project, Project.group_id == Group.group_id)
            .where(
                or_(
                    Group.supervisor_id == supervisor_id,
                    Group.cosupervisor_ids.contains([supervisor_id]),
                )
            )
            .order_by(Project.name.asc())
        )
        result = await db.execute(query)
        return result.all()

    async def get_group_profile_full(
        self, db: AsyncSession, group_id: UUID
    ) -> Optional[Group]:
        """Fetch a group with complete profile details eager-loaded."""
        from app.models.faculty import Faculty
        from app.models.project import Project

        query = (
            select(Group)
            .options(
                selectinload(Group.members)
                .joinedload(GroupMember.student)
                .joinedload(Student.user),
                selectinload(Group.project).selectinload(Project.domains),
                selectinload(Group.project).selectinload(Project.industry),
                selectinload(Group.supervisor).joinedload(Faculty.user),
                selectinload(Group.co_supervisors).joinedload(Faculty.user),
            )
            .where(Group.group_id == group_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def list_admin_groups(
        self,
        db: AsyncSession,
        batch: Optional[int] = None,
        cohort: Optional[str] = None,
        cycle: Optional[str] = None,
        supervisor: str = "all",
        members: Optional[int] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 10,
    ) -> Tuple[List[Any], int]:
        """Admin complex list groups with filters and pagination."""
        from sqlalchemy.orm import aliased

        from app.models.project import Project

        sup_user = aliased(User)

        member_counts_sq = (
            select(
                GroupMember.group_id.label("group_id"),
                func.count(GroupMember.student_id).label("members_count"),
            )
            .group_by(GroupMember.group_id)
            .subquery()
        )

        query = (
            select(
                Group.group_id,
                Group.fyp_cycle,
                Group.fyp_stage,
                Group.cohort,
                func.coalesce(member_counts_sq.c.members_count, 0).label(
                    "members_count"
                ),
                Project.name.label("project_name"),
                sup_user.full_name.label("supervisor_name"),
                literal(None).label("cosupervisor_name"),
            )
            .select_from(Group)
            .outerjoin(member_counts_sq, member_counts_sq.c.group_id == Group.group_id)
            .outerjoin(Project, Project.group_id == Group.group_id)
            .outerjoin(sup_user, sup_user.user_id == Group.supervisor_id)
            .group_by(
                Group.group_id,
                Project.name,
                Group.cohort,
                sup_user.full_name,
                member_counts_sq.c.members_count,
            )
        )

        filters = []
        if batch is not None:
            filters.append(Group.cohort_year == batch)
        if cycle is not None:
            filters.append(Group.fyp_cycle == cycle)

        if supervisor == "assigned":
            filters.append(Group.supervisor_id.isnot(None))
        elif supervisor == "unassigned":
            filters.append(Group.supervisor_id.is_(None))

        if members is not None:
            filters.append(
                func.coalesce(member_counts_sq.c.members_count, 0) == members
            )

        if cohort:
            filters.append(func.upper(Group.cohort) == cohort.upper())

        if search:
            s = f"%{search}%"
            filters.append(
                or_(
                    Project.name.ilike(s),
                    sup_user.full_name.ilike(s),
                    Group.name.ilike(s),
                )
            )

        if filters:
            query = query.where(and_(*filters))

        count_query = (
            select(func.count(func.distinct(Group.group_id)))
            .select_from(Group)
            .outerjoin(member_counts_sq, member_counts_sq.c.group_id == Group.group_id)
            .outerjoin(Project, Project.group_id == Group.group_id)
            .outerjoin(sup_user, sup_user.user_id == Group.supervisor_id)
        )
        if filters:
            count_query = count_query.where(and_(*filters))

        total = (await db.execute(count_query)).scalar() or 0

        offset = (page - 1) * per_page
        query = query.order_by(Group.updated_at.desc()).offset(offset).limit(per_page)

        result = await db.execute(query)
        rows = result.all()
        return rows, total

    async def update_cohort_cycle(
        self, db: AsyncSession, cohort: str, target_cycle: str
    ) -> int:
        """Update fyp cycle for all groups of a cohort."""
        from datetime import datetime

        normalized = cohort.upper()

        match_query = select(func.count(Group.group_id)).where(
            func.upper(Group.cohort) == normalized
        )
        total = (await db.execute(match_query)).scalar() or 0

        if total > 0:
            await db.execute(
                update(Group)
                .where(func.upper(Group.cohort) == normalized)
                .values(fyp_cycle=target_cycle, updated_at=datetime.utcnow())
            )

        return total

    async def get_admin_group_profile(
        self, db: AsyncSession, group_id: UUID
    ) -> Optional[Group]:
        """Fetch group profile with detailed student academic info for admin."""
        from app.models.faculty import Faculty
        from app.models.project import Project

        query = (
            select(Group)
            .options(
                selectinload(Group.project).selectinload(Project.domains),
                selectinload(Group.project).selectinload(Project.industry),
                selectinload(Group.members)
                .joinedload(GroupMember.student)
                .joinedload(Student.user),
                selectinload(Group.supervisor).joinedload(Faculty.user),
                selectinload(Group.co_supervisors).joinedload(Faculty.user),
            )
            .where(Group.group_id == group_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def get_group_with_project(
        self, db: AsyncSession, group_id: UUID
    ) -> Optional[Group]:
        """Fetch group with its project eagerly loaded."""
        query = (
            select(Group)
            .options(selectinload(Group.project))
            .where(Group.group_id == group_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def get_groups_with_project_by_ids(
        self, db: AsyncSession, group_ids: List[UUID]
    ) -> List[Group]:
        """Fetch multiple groups with their project details loaded."""
        if not group_ids:
            return []
        query = (
            select(Group)
            .options(selectinload(Group.project))
            .where(
                Group.group_id.in_(group_ids),
                Group.project.has(),
            )
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_groups_by_supervisor(
        self, db: AsyncSession, supervisor_id: UUID
    ) -> List[Group]:
        """Fetch all groups supervised or co-supervised by the given user."""
        query = (
            select(Group)
            .options(selectinload(Group.project))
            .where(
                or_(
                    Group.supervisor_id == supervisor_id,
                    Group.cosupervisor_ids.contains([supervisor_id]),
                )
            )
        )
        result = await db.execute(query)
        return list(result.scalars().all())


# Singleton instance for convenience
group_repository = GroupRepository()
