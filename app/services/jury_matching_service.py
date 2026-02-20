# app/services/jury_matching_service.py
"""
Jury Matching Service — Bridge between backend API and the AI microservice.

This service:
1. Calls the external AI service for batch jury matching
2. Calls the AI service for re-indexing
3. Uses circuit breaker for fault tolerance
4. Implements automated jury assignment (Background Waiter pattern)
"""

import logging
import traceback
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal
from app.middleware.ai_service import ai_service_circuit
from app.models.group import Group
from app.models.jury_assignment import (
    JuryAssignment,
    JuryAssignmentBatch,
    JuryBatchStatusEnum,
)
from app.models.project import Project
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

    async def get_batch_matches(self) -> List[Dict[str, Any]]:
        """
        Get jury recommendations for ALL projects in a single batch call.

        Returns:
            List of project jury matches.
        """
        self._circuit.check_and_raise()

        try:
            results = await self._client.batch_match()
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
    # Jury Assignment — Background Waiter Pattern
    # ─────────────────────────────────────────────────────────────

    async def create_assignment_batch(self, db: AsyncSession) -> JuryAssignmentBatch:
        """
        Create a new batch record (the "ticket").

        Returns immediately so the admin gets a batch_id to poll.
        """
        batch = JuryAssignmentBatch(
            batch_id=uuid.uuid4(),
            status=JuryBatchStatusEnum.processing,
        )
        db.add(batch)
        await db.commit()
        await db.refresh(batch)

        logger.info(f"Created jury assignment batch {batch.batch_id}")
        return batch

    async def run_assignment_job(
        self,
        batch_id: UUID,
        max_groups_per_jury: int,
        min_jury_per_project: int,
        fyp_cycle: str,
    ) -> None:
        """
        Background task: execute the full jury assignment flow.

        Creates its own DB session (runs outside request lifecycle).

        Flow:
        1. Call AI service for batch jury matches
        2. Run assignment algorithm (capacity + conflict resolution)
        3. Bulk insert jury assignments
        4. Update batch status → completed / failed
        """
        async with AsyncSessionLocal() as db:
            try:
                # ── Step 1: Get AI recommendations ──
                logger.info(f"Batch {batch_id}: calling AI service for matches")
                ai_results = await self.get_batch_matches()

                if not ai_results:
                    await self._fail_batch(
                        db, batch_id, "AI service returned no results"
                    )
                    return

                # ── Step 2: Load project→supervisor mapping (for conflict exclusion) ──
                project_supervisor_map = await self._load_project_supervisors(db)

                # ── Step 3: Run assignment algorithm ──
                assignments = self._run_assignment_algorithm(
                    ai_results=ai_results,
                    max_groups_per_jury=max_groups_per_jury,
                    min_jury_per_project=min_jury_per_project,
                    project_supervisor_map=project_supervisor_map,
                )

                # ── Step 4: Bulk insert assignments ──
                assignment_objects = [
                    JuryAssignment(
                        id=uuid.uuid4(),
                        batch_id=batch_id,
                        project_id=a["project_id"],
                        jury_id=a["jury_id"],
                        score=a.get("score"),
                        reason=a.get("reason"),
                    )
                    for a in assignments
                ]
                db.add_all(assignment_objects)

                # ── Step 5: Mark batch completed ──
                batch = await self._get_batch(db, batch_id)
                if batch:
                    batch.status = JuryBatchStatusEnum.completed
                    await db.commit()

                logger.info(
                    f"Batch {batch_id}: COMPLETED — "
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

    def _run_assignment_algorithm(
        self,
        ai_results: List[Dict[str, Any]],
        max_groups_per_jury: int,
        min_jury_per_project: int,
        project_supervisor_map: Dict[str, Optional[str]],
    ) -> List[Dict[str, Any]]:
        """
        Core assignment algorithm.

        Rules:
        1. A project's own supervisor CANNOT be their jury
        2. Each jury member evaluates at most `max_groups_per_jury` projects
        3. Each project gets at least `min_jury_per_project` jury members
        4. Prefer higher AI match scores (already ranked by AI)
        """
        jury_load: Dict[str, int] = defaultdict(int)
        assignments: List[Dict[str, Any]] = []

        for project_data in ai_results:
            project_id = project_data.get("project_id")
            matches = project_data.get("matches", [])

            if not project_id or not matches:
                continue

            project_supervisor_id = project_supervisor_map.get(project_id)
            assigned_count = 0

            for match in matches:
                if assigned_count >= min_jury_per_project:
                    break

                jury_id = match.get("jury_id")
                if not jury_id:
                    continue

                # Rule 1: Skip own supervisor
                if jury_id == project_supervisor_id:
                    continue

                # Rule 2: Skip if jury at capacity
                if jury_load[jury_id] >= max_groups_per_jury:
                    continue

                assignments.append(
                    {
                        "project_id": project_id,
                        "jury_id": jury_id,
                        "score": match.get("score"),
                        "reason": match.get("reason"),
                    }
                )
                jury_load[jury_id] += 1
                assigned_count += 1

            if assigned_count < min_jury_per_project:
                logger.warning(
                    f"Project {project_id} got only {assigned_count}/"
                    f"{min_jury_per_project} jury members"
                )

        logger.info(
            f"Assignment algorithm: {len(assignments)} assignments "
            f"for {len(ai_results)} projects"
        )
        return assignments

    async def get_batch_status(
        self, db: AsyncSession, batch_id: UUID
    ) -> Optional[JuryAssignmentBatch]:
        """Get a batch with its assignments (for polling)."""
        query = (
            select(JuryAssignmentBatch)
            .where(JuryAssignmentBatch.batch_id == batch_id)
            .options(selectinload(JuryAssignmentBatch.assignments))
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

    async def _load_project_supervisors(
        self, db: AsyncSession
    ) -> Dict[str, Optional[str]]:
        """Load project_id → supervisor_user_id mapping."""
        query = select(Project.project_id, Group.supervisor_id).join(
            Group, Project.group_id == Group.group_id
        )
        result = await db.execute(query)
        rows = result.all()

        mapping = {}
        for project_id, supervisor_id in rows:
            mapping[str(project_id)] = str(supervisor_id) if supervisor_id else None

        logger.info(f"Loaded supervisor mapping for {len(mapping)} projects")
        return mapping


# Global instance
jury_matching_service = JuryMatchingService()
