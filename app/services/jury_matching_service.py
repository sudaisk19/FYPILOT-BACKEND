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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.middleware.ai_service import ai_service_circuit
from app.models.group import Group
from app.models.jury_assignment import (
    JuryAssignment,
    JuryAssignmentBatch,
    JuryBatchStatusEnum,
)
from app.models.jury_pair import JuryPair
from app.models.project import Project
from app.repositories.jury_matching_repository import jury_matching_repository
from app.services.jury_matching_client import (
    JuryMatchingServiceError,
    jury_matching_client,
)

logger = logging.getLogger(__name__)

# Domain invariant: a jury is one pair of faculty evaluators (always two members).
JURY_PAIR_MEMBER_COUNT = 2
# Minimum distinct jury pairs each project must receive (not part of public assign body).
DEFAULT_MIN_JURY_PAIRS_PER_PROJECT = 1


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
        self,
        fyp_cycles: Optional[List[str]] = None,
        min_groups_per_pair: Optional[int] = None,
        max_groups_per_pair: Optional[int] = None,
        min_jury_per_project: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get jury recommendations for ALL projects in a single batch call.

        Returns:
            List of project jury matches.
        """
        self._circuit.check_and_raise()

        try:
            results = await self._client.batch_match(
                fyp_cycles=fyp_cycles,
                min_groups_per_pair=min_groups_per_pair,
                max_groups_per_pair=max_groups_per_pair,
                min_jury_per_project=min_jury_per_project,
            )
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

    def _safe_uuid(self, raw: Any) -> Optional[UUID]:
        """Best-effort UUID parser for variable AI payload shapes."""
        if raw is None:
            return None
        try:
            return uuid.UUID(str(raw))
        except (ValueError, TypeError, AttributeError):
            return None

    def _extract_project_uuid(self, assignment: Dict[str, Any]) -> Optional[UUID]:
        """Extract project UUID from common key variants / nested project object."""
        direct = (
            assignment.get("project_id")
            or assignment.get("projectId")
            or assignment.get("project_uuid")
            or assignment.get("id")
        )
        parsed = self._safe_uuid(direct)
        if parsed:
            return parsed

        project_obj = assignment.get("project")
        if isinstance(project_obj, dict):
            nested = (
                project_obj.get("project_id")
                or project_obj.get("projectId")
                or project_obj.get("project_uuid")
                or project_obj.get("id")
            )
            return self._safe_uuid(nested)
        return None

    def _extract_pair_uuid(
        self,
        assignment: Dict[str, Any],
        pair_lookup: Dict[str, UUID],
    ) -> Optional[UUID]:
        """Extract pair UUID from known keys; fallback to faculty pair mapping."""
        direct = (
            assignment.get("pair_id")
            or assignment.get("pairId")
            or assignment.get("jury_id")
            or assignment.get("juryId")
        )
        parsed = self._safe_uuid(direct)
        if parsed and str(parsed) in pair_lookup:
            return pair_lookup[str(parsed)]

        pair_obj = assignment.get("pair")
        if isinstance(pair_obj, dict):
            nested = (
                pair_obj.get("pair_id")
                or pair_obj.get("pairId")
                or pair_obj.get("jury_id")
                or pair_obj.get("juryId")
                or pair_obj.get("id")
            )
            parsed = self._safe_uuid(nested)
            if parsed:
                return parsed

        f1 = assignment.get("faculty_1_id")
        f2 = assignment.get("faculty_2_id")
        if f1 and f2:
            by_faculty = pair_lookup.get(f"{f1}:{f2}") or pair_lookup.get(f"{f2}:{f1}")
            if by_faculty:
                return by_faculty
        return None

    def _extract_member_faculty_ids(self, members: Any) -> List[UUID]:
        """Extract up to 2 faculty UUIDs from AI `members` array."""
        if not isinstance(members, list):
            return []
        ids: List[UUID] = []
        for m in members:
            if not isinstance(m, dict):
                continue
            raw = m.get("faculty_id") or m.get("user_id") or m.get("id")
            parsed = self._safe_uuid(raw)
            if parsed:
                ids.append(parsed)
        return ids

    def _extract_project_id_from_item(self, project_item: Any) -> Optional[UUID]:
        """Extract project UUID from assigned project item."""
        if isinstance(project_item, str):
            return self._safe_uuid(project_item)
        if not isinstance(project_item, dict):
            return None

        direct = (
            project_item.get("project_id")
            or project_item.get("projectId")
            or project_item.get("project_uuid")
            or project_item.get("id")
        )
        parsed = self._safe_uuid(direct)
        if parsed:
            return parsed

        nested = project_item.get("project")
        if isinstance(nested, dict):
            nested_id = (
                nested.get("project_id")
                or nested.get("projectId")
                or nested.get("project_uuid")
                or nested.get("id")
            )
            return self._safe_uuid(nested_id)
        return None

    async def _build_project_lookup(
        self, db: AsyncSession
    ) -> tuple[Dict[str, UUID], Dict[str, UUID]]:
        """
        Build lookup maps for resolving AI project refs to DB project UUIDs.
        Returns (by_fyp_id, by_name) with lowercase keys.
        """
        by_fyp_id: Dict[str, UUID] = {}
        by_name: Dict[str, UUID] = {}

        rows = (
            await db.execute(select(Project.project_id, Project.fyp_id, Project.name))
        ).all()
        for row in rows:
            pid = row.project_id
            if row.fyp_id:
                by_fyp_id[str(row.fyp_id).strip().lower()] = pid
            if row.name:
                by_name[str(row.name).strip().lower()] = pid
        return by_fyp_id, by_name

    async def _get_target_project_ids_for_cycles(
        self, db: AsyncSession, fyp_cycles: List[str]
    ) -> List[UUID]:
        """Fetch project IDs belonging to the requested FYP cycles."""
        if not fyp_cycles:
            return []
        rows = await db.execute(
            select(Project.project_id)
            .join(Group, Project.group_id == Group.group_id)
            .where(Group.fyp_cycle.in_(fyp_cycles))
            .order_by(Project.created_at.asc())
        )
        return list(rows.scalars().all())

    def _resolve_project_uuid_from_lookup(
        self,
        assignment: Dict[str, Any],
        by_fyp_id: Dict[str, UUID],
        by_name: Dict[str, UUID],
    ) -> Optional[UUID]:
        """
        Resolve project UUID using non-UUID refs (fyp_id/name) from AI payload.
        """
        candidates: List[str] = []
        for key in ("fyp_id", "fypId", "project_name", "projectName", "name", "title"):
            raw = assignment.get(key)
            if isinstance(raw, str) and raw.strip():
                candidates.append(raw.strip())

        project_obj = assignment.get("project")
        if isinstance(project_obj, dict):
            for key in (
                "fyp_id",
                "fypId",
                "project_name",
                "projectName",
                "name",
                "title",
            ):
                raw = project_obj.get(key)
                if isinstance(raw, str) and raw.strip():
                    candidates.append(raw.strip())

        ref = assignment.get("project_ref")
        if isinstance(ref, str) and ref.strip():
            candidates.append(ref.strip())

        for cand in candidates:
            parsed = self._safe_uuid(cand)
            if parsed:
                return parsed
            key = cand.lower()
            if key in by_fyp_id:
                return by_fyp_id[key]
            if key in by_name:
                return by_name[key]
        return None

    def _normalize_ai_payload(
        self, ai_results: Any
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Normalize different AI response shapes into:
        - pairs_data: [{jury_id, faculty_1_id, faculty_2_id}, ...]
        - assignments_data: [{project_id, jury_id/pair_id, score?, reason?}, ...]
        """
        pairs_data: List[Dict[str, Any]] = []
        assignments_data: List[Dict[str, Any]] = []

        raw_pairs: Any = []
        raw_assignments: Any = []
        if isinstance(ai_results, dict):
            raw_pairs = ai_results.get("pairs", [])
            raw_assignments = ai_results.get("assignments", [])
        elif isinstance(ai_results, list):
            raw_assignments = ai_results

        if isinstance(raw_pairs, list):
            pairs_data = [p for p in raw_pairs if isinstance(p, dict)]
        if not isinstance(raw_assignments, list):
            return pairs_data, assignments_data

        # Detect grouped response: each item has assigned_projects for a jury pair.
        grouped = any(
            isinstance(item, dict) and "assigned_projects" in item
            for item in raw_assignments
        )
        if not grouped:
            assignments_data = [a for a in raw_assignments if isinstance(a, dict)]
            return pairs_data, assignments_data

        # Build pairs_data from grouped items if AI didn't return explicit `pairs`.
        if not pairs_data:
            for item in raw_assignments:
                if not isinstance(item, dict):
                    continue
                member_ids = self._extract_member_faculty_ids(item.get("members"))
                if len(member_ids) < 2:
                    continue
                jury_id = self._safe_uuid(item.get("jury_id") or item.get("pair_id"))
                pairs_data.append(
                    {
                        "jury_id": str(jury_id) if jury_id else str(uuid.uuid4()),
                        "faculty_1_id": str(member_ids[0]),
                        "faculty_2_id": str(member_ids[1]),
                    }
                )

        # Flatten grouped assignments into row-wise assignments.
        for item in raw_assignments:
            if not isinstance(item, dict):
                continue
            pair_ref = item.get("pair_id") or item.get("jury_id") or item.get("id")
            projects = item.get("assigned_projects")
            if not isinstance(projects, list):
                continue

            for proj in projects:
                project_id = self._extract_project_id_from_item(proj)
                if not project_id:
                    project_ref = None
                    if isinstance(proj, dict):
                        project_ref = (
                            proj.get("fyp_id")
                            or proj.get("fypId")
                            or proj.get("project_name")
                            or proj.get("projectName")
                            or proj.get("name")
                            or proj.get("title")
                        )
                    if not project_ref and isinstance(proj, str):
                        project_ref = proj
                    if project_ref:
                        assignments_data.append(
                            {
                                "project_ref": str(project_ref),
                                "jury_id": pair_ref,
                            }
                        )
                    continue
                row: Dict[str, Any] = {
                    "project_id": str(project_id),
                    "jury_id": pair_ref,
                }
                if isinstance(proj, dict):
                    if "score" in proj:
                        row["score"] = proj.get("score")
                    if "reason" in proj:
                        row["reason"] = proj.get("reason")
                assignments_data.append(row)

        return pairs_data, assignments_data

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
        counts = await jury_matching_repository.reset_all_jury_data(db)
        await db.commit()

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
        min_groups_per_pair: int = 1,
        max_groups_per_pair: int = 10,
    ) -> None:
        """
        Background task: execute the full jury assignment flow.

        Creates its own DB session (runs outside request lifecycle).

        Each jury pair always represents exactly ``JURY_PAIR_MEMBER_COUNT`` faculty
        members. Per-pair workload is controlled by ``min_groups_per_pair`` /
        ``max_groups_per_pair`` from the assign request. Minimum jury pairs per
        project uses ``DEFAULT_MIN_JURY_PAIRS_PER_PROJECT`` (not client-supplied).

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
                ai_results = await self.get_batch_matches(
                    fyp_cycles=fyp_cycles,
                    min_groups_per_pair=min_groups_per_pair,
                    max_groups_per_pair=max_groups_per_pair,
                    min_jury_per_project=DEFAULT_MIN_JURY_PAIRS_PER_PROJECT,
                )

                if not ai_results:
                    await self._fail_batch(
                        db, batch_id, "AI service returned no results"
                    )
                    return

                # ── Step 3: Normalize AI payload into pairs + flat assignments ──
                pairs_data, assignments_data = self._normalize_ai_payload(ai_results)

                # Build existing pair maps to make inserts idempotent.
                existing_pairs = (await db.execute(select(JuryPair))).scalars().all()
                pair_lookup: Dict[str, UUID] = {}
                existing_by_faculty: Dict[str, UUID] = {}
                for p in existing_pairs:
                    pair_lookup[str(p.jury_id)] = p.jury_id
                    k1 = f"{p.faculty_1_id}:{p.faculty_2_id}"
                    k2 = f"{p.faculty_2_id}:{p.faculty_1_id}"
                    pair_lookup[k1] = p.jury_id
                    pair_lookup[k2] = p.jury_id
                    existing_by_faculty[k1] = p.jury_id
                    existing_by_faculty[k2] = p.jury_id

                pair_objects: List[JuryPair] = []
                pending_ids: set[UUID] = set()
                pending_faculty: set[str] = set()
                for idx, pair in enumerate(pairs_data, start=1):
                    f1 = self._safe_uuid(pair.get("faculty_1_id"))
                    f2 = self._safe_uuid(pair.get("faculty_2_id"))
                    if not f1 or not f2 or f1 == f2:
                        continue

                    k1 = f"{f1}:{f2}"
                    k2 = f"{f2}:{f1}"

                    # Reuse already-known pair for this faculty combo.
                    existing_faculty_id = existing_by_faculty.get(
                        k1
                    ) or existing_by_faculty.get(k2)
                    if existing_faculty_id:
                        pair_lookup[k1] = existing_faculty_id
                        pair_lookup[k2] = existing_faculty_id
                        raw_jid = self._safe_uuid(pair.get("jury_id"))
                        if raw_jid:
                            pair_lookup[str(raw_jid)] = existing_faculty_id
                        continue

                    raw_jid = self._safe_uuid(pair.get("jury_id")) or uuid.uuid4()
                    # Avoid duplicate PK insert and duplicate combos in same payload.
                    if raw_jid in pair_lookup or raw_jid in pending_ids:
                        raw_jid = uuid.uuid4()
                    if k1 in pending_faculty or k2 in pending_faculty:
                        continue

                    pair_obj = JuryPair(
                        jury_id=raw_jid,
                        faculty_1_id=f1,
                        faculty_2_id=f2,
                        jury_number=idx,
                    )
                    pair_objects.append(pair_obj)
                    pending_ids.add(raw_jid)
                    pending_faculty.add(k1)
                    pending_faculty.add(k2)
                    pair_lookup[str(raw_jid)] = raw_jid
                    pair_lookup[k1] = raw_jid
                    pair_lookup[k2] = raw_jid

                if pair_objects:
                    db.add_all(pair_objects)
                    await db.flush()  # Ensure new jury_ids are usable for assignments.

                # ── Step 4: Validate AI assignments quickly and persist ──
                by_fyp_id, by_name = await self._build_project_lookup(db)
                skipped_assignments = 0
                assignment_objects: List[JuryAssignment] = []
                pair_load: Dict[UUID, int] = {}
                project_load: Dict[UUID, int] = {}
                project_pair_seen: set[tuple[UUID, UUID]] = set()
                available_pair_ids = {v for k, v in pair_lookup.items() if ":" not in k}

                for a_data in assignments_data:
                    if not isinstance(a_data, dict):
                        skipped_assignments += 1
                        continue

                    project_uuid = self._extract_project_uuid(a_data)
                    if not project_uuid:
                        project_uuid = self._resolve_project_uuid_from_lookup(
                            a_data, by_fyp_id, by_name
                        )
                    if not project_uuid:
                        skipped_assignments += 1
                        continue

                    pair_uuid = self._extract_pair_uuid(a_data, pair_lookup)
                    if not pair_uuid or pair_uuid not in available_pair_ids:
                        skipped_assignments += 1
                        continue

                    key = (project_uuid, pair_uuid)
                    if key in project_pair_seen:
                        # Ignore duplicate recommendation rows for same project+pair.
                        continue
                    project_pair_seen.add(key)

                    score_raw = a_data.get("score")
                    try:
                        score_val = float(score_raw) if score_raw is not None else None
                    except (TypeError, ValueError):
                        score_val = None

                    assignment_objects.append(
                        JuryAssignment(
                            id=uuid.uuid4(),
                            batch_id=batch_id,
                            project_id=project_uuid,
                            pair_id=pair_uuid,
                            score=score_val,
                            reason=a_data.get("reason"),
                        )
                    )
                    pair_load[pair_uuid] = pair_load.get(pair_uuid, 0) + 1
                    project_load[project_uuid] = project_load.get(project_uuid, 0) + 1

                if not assignment_objects:
                    sample_keys = []
                    if assignments_data and isinstance(assignments_data[0], dict):
                        sample_keys = list(assignments_data[0].keys())
                    await self._fail_batch(
                        db,
                        batch_id,
                        "AI assignments payload missing resolvable project/pair identifiers"
                        f" (count={len(assignments_data)}, sample_keys={sample_keys})",
                    )
                    return

                min_groups = max(1, int(min_groups_per_pair))
                max_groups = max(1, int(max_groups_per_pair))
                min_jury = max(1, int(DEFAULT_MIN_JURY_PAIRS_PER_PROJECT))

                if min_groups > max_groups:
                    await self._fail_batch(
                        db,
                        batch_id,
                        "Invalid constraints: min_groups_per_pair cannot exceed "
                        "max_groups_per_pair "
                        f"(min={min_groups}, max={max_groups})",
                    )
                    return

                overloaded_pairs = {
                    str(pid): count
                    for pid, count in pair_load.items()
                    if count > max_groups
                }
                if overloaded_pairs:
                    await self._fail_batch(
                        db,
                        batch_id,
                        "AI assignments violate max_groups_per_pair. "
                        f"max={max_groups}, overloaded={overloaded_pairs}",
                    )
                    return

                underloaded_pairs = {
                    str(pid): count
                    for pid, count in pair_load.items()
                    if count < min_groups
                }
                if underloaded_pairs:
                    await self._fail_batch(
                        db,
                        batch_id,
                        "AI assignments violate min_groups_per_pair. "
                        f"min={min_groups}, underloaded={underloaded_pairs}",
                    )
                    return

                target_project_ids = await self._get_target_project_ids_for_cycles(
                    db, fyp_cycles
                )
                if not target_project_ids:
                    await self._fail_batch(
                        db,
                        batch_id,
                        f"No projects found for requested cycles: {fyp_cycles}",
                    )
                    return

                missing_projects = [
                    str(pid)
                    for pid in target_project_ids
                    if project_load.get(pid, 0) < min_jury
                ]
                if missing_projects:
                    await self._fail_batch(
                        db,
                        batch_id,
                        "AI assignments violate minimum jury pairs per project "
                        f"(internal min={min_jury}). "
                        f"missing_or_underfilled_projects={missing_projects[:20]}",
                    )
                    return

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
                    f" (skipped={skipped_assignments})"
                    f" validated(min_groups={min_groups}, max_groups={max_groups}, "
                    f"min_jury_pairs_per_project={min_jury}, "
                    f"jury_pair_members={JURY_PAIR_MEMBER_COUNT})"
                )

            except Exception as e:
                logger.error(
                    f"Batch {batch_id}: FAILED — {str(e)}\n" f"{traceback.format_exc()}"
                )
                try:
                    await db.rollback()
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

        return await jury_matching_repository.get_batch_with_assignments(db, batch_id)

    async def get_all_batches(self, db: AsyncSession) -> List[JuryAssignmentBatch]:
        """Get all batches, most recent first."""
        return await jury_matching_repository.get_all_batches(db)

    async def get_all_jury_pairs(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Get all jury pairs with faculty names for dropdown.

        Returns list of dicts with jury_id, jury_number,
        faculty_1_id, faculty_1_name, faculty_2_id, faculty_2_name.
        """
        rows = await jury_matching_repository.get_all_jury_pairs_with_names(db)

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
            latest_batch = await jury_matching_repository.get_latest_batch(db)
            if not latest_batch:
                return None
            batch_id = latest_batch.batch_id

        # ── Load batch with assignments (project + pair) ──
        batch = await jury_matching_repository.get_batch_with_assignments(db, batch_id)

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
            if a.pair:
                faculty_ids.add(a.pair.faculty_1_id)
                faculty_ids.add(a.pair.faculty_2_id)

        # ── Batch-fetch groups → members → student → user ──
        groups_map: Dict[str, Any] = {}
        if group_ids:
            groups = await jury_matching_repository.get_groups_with_members(
                db, list(group_ids)
            )
            for g in groups:
                groups_map[str(g.group_id)] = g

        # ── Batch-fetch faculty info (name + department) ──
        faculty_map: Dict[str, Dict[str, Any]] = {}
        if faculty_ids:
            rows = await jury_matching_repository.get_faculty_info_batch(
                db, list(faculty_ids)
            )
            for row in rows:
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
                pair_assignments[pk] = {"pair": a.pair, "items": []}
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
        pair = await jury_matching_repository.get_jury_pair_by_id(db, new_pair_id)
        if not pair:
            return None

        # Find the assignment
        assignment = await jury_matching_repository.get_assignment_by_id(
            db, assignment_id
        )

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
        return await jury_matching_repository.get_batch_by_id(db, batch_id)

    async def _fail_batch(self, db: AsyncSession, batch_id: UUID, error: str) -> None:
        """Mark a batch as failed with an error log."""
        batch = await self._get_batch(db, batch_id)
        if batch:
            batch.status = JuryBatchStatusEnum.failed
            batch.error_log = error
            await db.commit()


# Global instance
jury_matching_service = JuryMatchingService()
