# app/repositories/jury_matching_repository.py
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.faculty import Faculty
from app.models.group import Group, GroupMember
from app.models.jury_assignment import JuryAssignment, JuryAssignmentBatch
from app.models.jury_pair import JuryPair
from app.models.student import Student
from app.models.user import User


class JuryMatchingRepository:
    """Repository handling all database operations for jury matching."""

    async def reset_all_jury_data(self, db: AsyncSession) -> Dict[str, int]:
        del_assignments = await db.execute(delete(JuryAssignment))
        del_pairs = await db.execute(delete(JuryPair))
        del_batches = await db.execute(delete(JuryAssignmentBatch))

        return {
            "deleted_assignments": del_assignments.rowcount,
            "deleted_pairs": del_pairs.rowcount,
            "deleted_batches": del_batches.rowcount,
        }

    async def get_batch_with_assignments(
        self, db: AsyncSession, batch_id: UUID
    ) -> Optional[JuryAssignmentBatch]:
        query = (
            select(JuryAssignmentBatch)
            .where(JuryAssignmentBatch.batch_id == batch_id)
            .options(
                selectinload(JuryAssignmentBatch.assignments).selectinload(
                    JuryAssignment.project
                ),
                selectinload(JuryAssignmentBatch.assignments).selectinload(
                    JuryAssignment.jury_pair
                ),
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_latest_batch(self, db: AsyncSession) -> Optional[JuryAssignmentBatch]:
        latest_q = (
            select(JuryAssignmentBatch)
            .order_by(JuryAssignmentBatch.created_at.desc())
            .limit(1)
        )
        latest_r = await db.execute(latest_q)
        return latest_r.scalar_one_or_none()

    async def get_all_batches(self, db: AsyncSession) -> List[JuryAssignmentBatch]:
        query = select(JuryAssignmentBatch).order_by(
            JuryAssignmentBatch.created_at.desc()
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_all_jury_pairs_with_names(self, db: AsyncSession) -> List[Any]:
        F1 = User.__table__.alias("f1")
        F2 = User.__table__.alias("f2")

        query = (
            select(
                JuryPair.jury_id,
                JuryPair.jury_number,
                JuryPair.faculty_1_id,
                F1.c.full_name.label("faculty_1_name"),
                JuryPair.faculty_2_id,
                F2.c.full_name.label("faculty_2_name"),
            )
            .outerjoin(F1, JuryPair.faculty_1_id == F1.c.user_id)
            .outerjoin(F2, JuryPair.faculty_2_id == F2.c.user_id)
            .order_by(JuryPair.jury_number)
        )
        result = await db.execute(query)
        return result.all()

    async def get_groups_with_members(
        self, db: AsyncSession, group_ids: List[UUID]
    ) -> List[Group]:
        grp_query = (
            select(Group)
            .where(Group.group_id.in_(group_ids))
            .options(
                selectinload(Group.members)
                .selectinload(GroupMember.student)
                .selectinload(Student.user)
            )
        )
        grp_result = await db.execute(grp_query)
        return list(grp_result.scalars().all())

    async def get_faculty_info_batch(
        self, db: AsyncSession, faculty_ids: List[UUID]
    ) -> List[Any]:
        fac_t = Faculty.__table__
        usr_t = User.__table__
        fac_query = (
            select(fac_t.c.user_id, usr_t.c.full_name, fac_t.c.department)
            .join(usr_t, fac_t.c.user_id == usr_t.c.user_id)
            .where(fac_t.c.user_id.in_(faculty_ids))
        )
        fac_result = await db.execute(fac_query)
        return fac_result.all()

    async def get_jury_pair_by_id(
        self, db: AsyncSession, pair_id: UUID
    ) -> Optional[JuryPair]:
        pair_query = select(JuryPair).where(JuryPair.jury_id == pair_id)
        pair_result = await db.execute(pair_query)
        return pair_result.scalar_one_or_none()

    async def get_assignment_by_id(
        self, db: AsyncSession, assignment_id: UUID
    ) -> Optional[JuryAssignment]:
        query = select(JuryAssignment).where(JuryAssignment.id == assignment_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_batch_by_id(
        self, db: AsyncSession, batch_id: UUID
    ) -> Optional[JuryAssignmentBatch]:
        query = select(JuryAssignmentBatch).where(
            JuryAssignmentBatch.batch_id == batch_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()


# Singleton instance
jury_matching_repository = JuryMatchingRepository()
