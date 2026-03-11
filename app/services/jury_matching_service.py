# app/services/jury_matching_service.py
"""
Jury Matching Service — Bridge between backend API and the AI microservice.

This service:
1. Calls the external AI service for batch jury matching
2. Calls the AI service for re-indexing
3. Uses circuit breaker for fault tolerance
4. Implements pair-based jury assignment (Background Waiter pattern)
5. Provides reset / delete / patch operations for admin
"""

import logging
import traceback
import uuid
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal
from app.middleware.ai_service import ai_service_circuit
from app.models.faculty import Faculty
from app.models.group import Group, GroupMember
from app.models.jury_assignment import (
    JuryAssignment,
    JuryAssignmentBatch,
    JuryBatchStatusEnum,
)
from app.models.jury_pair import JuryPair
from app.models.student import Student
from app.models.user import User
from app.services.jury_matching_client import (
    JuryMatchingServiceError,
    jury_matching_client,
)

logger = logging.getLogger(__name__)


class JuryMatchingService:
    """Service for jury matching via the external AI microservice."""

    def __init__(self):
        """Initialize the jury matching service."""
        self._client = jury_matching_client
        self._circuit = ai_service_circuit

    async def health_check(self) -> bool:
        """Check if the Jury Matching AI service is available."""
        return await self._client.health_check()

    async def get_batch_matches(
        self, fyp_cycles: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get jury recommendations for ALL projects in a single batch call.

        Returns:
            List of project jury matches.
        """
        self._circuit.check_and_raise()

        try:
            results = await self._client.batch_match(fyp_cycles=fyp_cycles)
            self._circuit.record_success()
            logger.info(f"Received jury matches for {len(results)} projects")
            return results

        except JuryMatchingServiceError as e:
            self._circuit.record_failure()
            logger.error(f"Jury Matching service error: {e.message}")
            raise

    async def trigger_reindex(self) -> Dict[str, Any]:
        """Trigger a full re-index of the jury + project FAISS indexes."""
        self._circuit.check_and_raise()

        try:
            result = await self._client.reindex()
            self._circuit.record_success()
            return result

        except JuryMatchingServiceError as e:
            self._circuit.record_failure()
            logger.error(f"Jury re-index error: {e.message}")
            raise

    # ─────────────────────────────────────────────────────────────
    # Reset — Clear all 3 tables before a new assignment run
    # ─────────────────────────────────────────────────────────────

    async def reset_all_jury_data(self, db: AsyncSession) -> Dict[str, int]:
        """
        Delete ALL records from jury_assignments, jury_pairs,
        and jury_assignment_batches. Used before a new AI assignment
        run and also as a manual admin action.

        Returns counts of deleted rows.
        """
        # Order matters: assignments → pairs → batches (FK dependencies)
        del_assignments = await db.execute(delete(JuryAssignment))
        del_pairs = await db.execute(delete(JuryPair))
        del_batches = await db.execute(delete(JuryAssignmentBatch))
        await db.commit()

        counts = {
            "deleted_assignments": del_assignments.rowcount,
            "deleted_pairs": del_pairs.rowcount,
            "deleted_batches": del_batches.rowcount,
        }
        logger.info(f"Reset all jury data: {counts}")
        return counts

    # ─────────────────────────────────────────────────────────────
    # Jury Assignment — Background Waiter Pattern
    # ─────────────────────────────────────────────────────────────

    async def create_assignment_batch(
        self,
        db: AsyncSession,
        fyp_cycles: List[str],
        created_by: Optional[UUID] = None,
    ) -> JuryAssignmentBatch:
        """
        Create a new batch record (the "ticket").

        Returns immediately so the admin gets a batch_id to poll.
        """
        batch = JuryAssignmentBatch(
            batch_id=uuid.uuid4(),
            status=JuryBatchStatusEnum.processing,
            fyp_cycles=fyp_cycles,
            created_by=created_by,
        )
        db.add(batch)
        await db.commit()
        await db.refresh(batch)

        logger.info(f"Created jury assignment batch {batch.batch_id}")
        return batch

    async def run_assignment_job(
        self,
        batch_id: UUID,
        fyp_cycles: List[str],
    ) -> None:
        """
        Background task: execute the full jury assignment flow.

        Creates its own DB session (runs outside request lifecycle).

        Flow:
        1. Reset all existing jury data (clean slate)
        2. Call AI service → get pairs + assignments
        3. Save jury pairs to DB
        4. Save jury assignments to DB
        5. Update batch status → completed / failed
        """
        async with AsyncSessionLocal() as db:
            try:
                # ── Step 1: Reset all existing data ──
                logger.info(f"Batch {batch_id}: resetting all jury data")
                await self.reset_all_jury_data(db)

                # Re-fetch the batch (it was just re-created, need to
                # make sure it still exists after reset)
                batch = await self._get_batch(db, batch_id)
                if not batch:
                    # The reset deleted our batch too — recreate it
                    batch = JuryAssignmentBatch(
                        batch_id=batch_id,
                        status=JuryBatchStatusEnum.processing,
                        fyp_cycles=fyp_cycles,
                    )
                    db.add(batch)
                    await db.commit()

                # ── Step 2: Call AI service for jury pairs + assignments ──
                logger.info(f"Batch {batch_id}: calling AI service")
                ai_results = await self.get_batch_matches(fyp_cycles=fyp_cycles)

                if not ai_results:
                    await self._fail_batch(
                        db, batch_id, "AI service returned no results"
                    )
                    return

                # ── Step 3: Save jury pairs from AI response ──
                # AI returns pairs as a list in the response
                pairs_data = []
                if isinstance(ai_results, dict):
                    pairs_data = ai_results.get("pairs", [])
                    assignments_data = ai_results.get("assignments", [])
                elif isinstance(ai_results, list):
                    # Fallback: old format where results is a flat list
                    assignments_data = ai_results
                    pairs_data = []

                pair_objects = []
                for idx, pair in enumerate(pairs_data, start=1):
                    pair_obj = JuryPair(
                        jury_id=(
                            uuid.UUID(pair["jury_id"])
                            if "jury_id" in pair
                            else uuid.uuid4()
                        ),
                        faculty_1_id=uuid.UUID(pair["faculty_1_id"]),
                        faculty_2_id=uuid.UUID(pair["faculty_2_id"]),
                        jury_number=idx,
                    )
                    pair_objects.append(pair_obj)

                if pair_objects:
                    db.add_all(pair_objects)
                    await db.flush()  # Get IDs before assignments reference them

                # Build a lookup: faculty pair key → jury_id
                pair_lookup = {}
                for p in pair_objects:
                    pair_lookup[str(p.jury_id)] = p.jury_id

                # ── Step 4: Save assignments ──
                assignment_objects = []
                for a_data in assignments_data:
                    pair_id_str = a_data.get("pair_id") or a_data.get("jury_id")
                    assignment_objects.append(
                        JuryAssignment(
                            id=uuid.uuid4(),
                            batch_id=batch_id,
                            project_id=uuid.UUID(a_data["project_id"]),
                            pair_id=uuid.UUID(pair_id_str) if pair_id_str else None,
                            score=a_data.get("score"),
                            reason=a_data.get("reason"),
                        )
                    )

                if assignment_objects:
                    db.add_all(assignment_objects)

                # ── Step 5: Mark batch completed ──
                batch = await self._get_batch(db, batch_id)
                if batch:
                    batch.status = JuryBatchStatusEnum.completed
                    await db.commit()

                logger.info(
                    f"Batch {batch_id}: COMPLETED — "
                    f"{len(pair_objects)} pairs, "
                    f"{len(assignment_objects)} assignments"
                )

            except Exception as e:
                logger.error(
                    f"Batch {batch_id}: FAILED — {str(e)}\n" f"{traceback.format_exc()}"
                )
                try:
                    await self._fail_batch(db, batch_id, str(e)[:500])
                except Exception as inner_e:
                    logger.error(f"Failed to mark batch as failed: {inner_e}")

    # ─────────────────────────────────────────────────────────────
    # Read operations
    # ─────────────────────────────────────────────────────────────

    async def get_batch_status(
        self, db: AsyncSession, batch_id: UUID
    ) -> Optional[JuryAssignmentBatch]:
        """Get a batch with its assignments (for polling)."""
        from app.models.jury_pair import JuryPair  # noqa: F811

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

    async def get_all_batches(self, db: AsyncSession) -> List[JuryAssignmentBatch]:
        """Get all batches, most recent first."""
        query = select(JuryAssignmentBatch).order_by(
            JuryAssignmentBatch.created_at.desc()
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_all_jury_pairs(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Get all jury pairs with faculty names for dropdown.

        Returns list of dicts with jury_id, jury_number,
        faculty_1_id, faculty_1_name, faculty_2_id, faculty_2_name.
        """
        # Alias User for the two faculty members
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
        rows = result.all()

        return [
            {
                "jury_id": str(r.jury_id),
                "jury_number": r.jury_number,
                "faculty_1_id": str(r.faculty_1_id),
                "faculty_1_name": r.faculty_1_name or "Unknown",
                "faculty_2_id": str(r.faculty_2_id),
                "faculty_2_name": r.faculty_2_name or "Unknown",
            }
            for r in rows
        ]

    # ─────────────────────────────────────────────────────────────
    # Grouped Assignments — Frontend-facing response builder
    # ─────────────────────────────────────────────────────────────

    async def get_jury_matches(
        self,
        db: AsyncSession,
        batch_id: Optional[UUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get jury assignments grouped by pair with full details.

        If *batch_id* is ``None``, the latest batch is used.
        Returns ``{"batch": <JuryAssignmentBatch>, "jury_matches": [...]}``
        where each match follows the frontend ``MOCK_JURY_MATCHES`` shape.
        """
        # ── Resolve batch_id ──
        if batch_id is None:
            latest_q = (
                select(JuryAssignmentBatch)
                .order_by(JuryAssignmentBatch.created_at.desc())
                .limit(1)
            )
            latest_r = await db.execute(latest_q)
            latest_batch = latest_r.scalar_one_or_none()
            if not latest_batch:
                return None
            batch_id = latest_batch.batch_id

        # ── Load batch with assignments (project + jury_pair) ──
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
        batch = result.scalar_one_or_none()

        if not batch:
            return None

        # Not completed yet or empty → return batch meta only
        if batch.status != JuryBatchStatusEnum.completed or not batch.assignments:
            return {"batch": batch, "jury_matches": []}

        # ── Collect IDs for batch queries ──
        group_ids: set = set()
        faculty_ids: set = set()
        for a in batch.assignments:
            if a.project and a.project.group_id:
                group_ids.add(a.project.group_id)
            if a.jury_pair:
                faculty_ids.add(a.jury_pair.faculty_1_id)
                faculty_ids.add(a.jury_pair.faculty_2_id)

        # ── Batch-fetch groups → members → student → user ──
        groups_map: Dict[str, Any] = {}
        if group_ids:
            grp_query = (
                select(Group)
                .where(Group.group_id.in_(list(group_ids)))
                .options(
                    selectinload(Group.members)
                    .selectinload(GroupMember.student)
                    .selectinload(Student.user)
                )
            )
            grp_result = await db.execute(grp_query)
            for g in grp_result.scalars().all():
                groups_map[str(g.group_id)] = g

        # ── Batch-fetch faculty info (name + department) ──
        faculty_map: Dict[str, Dict[str, Any]] = {}
        if faculty_ids:
            fac_t = Faculty.__table__
            usr_t = User.__table__
            fac_query = (
                select(fac_t.c.user_id, usr_t.c.full_name, fac_t.c.department)
                .join(usr_t, fac_t.c.user_id == usr_t.c.user_id)
                .where(fac_t.c.user_id.in_(list(faculty_ids)))
            )
            fac_result = await db.execute(fac_query)
            for row in fac_result.all():
                faculty_map[str(row.user_id)] = {
                    "name": row.full_name or "Unknown",
                    "department": row.department,
                }

        # ── Group assignments by pair_id ──
        pair_assignments: Dict[str, Dict[str, Any]] = {}
        for a in batch.assignments:
            pk = str(a.pair_id) if a.pair_id else None
            if pk is None:
                continue
            if pk not in pair_assignments:
                pair_assignments[pk] = {"pair": a.jury_pair, "items": []}
            pair_assignments[pk]["items"].append(a)

        # ── Build jury_matches list ──
        jury_matches: List[Dict[str, Any]] = []
        for data in pair_assignments.values():
            pair = data["pair"]
            if not pair:
                continue

            supervisors = []
            for fid in [str(pair.faculty_1_id), str(pair.faculty_2_id)]:
                info = faculty_map.get(fid, {"name": "Unknown", "department": None})
                supervisors.append(info)

            groups: List[Dict[str, Any]] = []
            for a in data["items"]:
                project = a.project
                gid = str(project.group_id) if project and project.group_id else None
                group = groups_map.get(gid) if gid else None

                members = []
                if group:
                    for m in group.members:
                        student = m.student
                        user = student.user if student else None
                        members.append(
                            {
                                "name": (user.full_name if user else "Unknown"),
                                "rollNumber": (
                                    student.roll_number if student else "N/A"
                                ),
                            }
                        )

                fyp_cycle_val = None
                if group and group.fyp_cycle:
                    fyp_cycle_val = (
                        group.fyp_cycle.value
                        if hasattr(group.fyp_cycle, "value")
                        else str(group.fyp_cycle)
                    )

                groups.append(
                    {
                        "id": str(a.id),
                        "projectName": (project.name if project else "Unknown"),
                        "fypId": (project.fyp_id if project else None),
                        "fypCycle": fyp_cycle_val,
                        "members": members,
                    }
                )

            jury_matches.append(
                {
                    "id": str(pair.jury_id),
                    "jury_number": pair.jury_number,
                    "supervisors": supervisors,
                    "groups": groups,
                }
            )

        jury_matches.sort(key=lambda x: x.get("jury_number") or 999)
        return {"batch": batch, "jury_matches": jury_matches}

    # ─────────────────────────────────────────────────────────────
    # Patch — Change jury pair for a specific assignment
    # ─────────────────────────────────────────────────────────────

    async def update_assignment_jury(
        self,
        db: AsyncSession,
        assignment_id: UUID,
        new_pair_id: UUID,
    ) -> Optional[JuryAssignment]:
        """
        Change the jury pair for a specific assignment.

        Returns the updated assignment or None if not found.
        """
        # Verify the new pair exists
        pair_query = select(JuryPair).where(JuryPair.jury_id == new_pair_id)
        pair_result = await db.execute(pair_query)
        pair = pair_result.scalar_one_or_none()
        if not pair:
            return None

        # Find the assignment
        query = select(JuryAssignment).where(JuryAssignment.id == assignment_id)
        result = await db.execute(query)
        assignment = result.scalar_one_or_none()

        if not assignment:
            return None

        assignment.pair_id = new_pair_id
        await db.commit()
        await db.refresh(assignment)

        logger.info(
            f"Updated assignment {assignment_id}: " f"pair changed to {new_pair_id}"
        )
        return assignment

    # ── Private helpers ──────────────────────────────────────────

    async def _get_batch(
        self, db: AsyncSession, batch_id: UUID
    ) -> Optional[JuryAssignmentBatch]:
        """Load a batch by ID."""
        query = select(JuryAssignmentBatch).where(
            JuryAssignmentBatch.batch_id == batch_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _fail_batch(self, db: AsyncSession, batch_id: UUID, error: str) -> None:
        """Mark a batch as failed with an error log."""
        batch = await self._get_batch(db, batch_id)
        if batch:
            batch.status = JuryBatchStatusEnum.failed
            batch.error_log = error
            await db.commit()


# Global instance
jury_matching_service = JuryMatchingService()
