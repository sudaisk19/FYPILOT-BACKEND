"""
Document Service
Business logic for live-draft autosave, version snapshots, and workspace management.
All DB access goes through the repository layer.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group_document import (
    DocumentFile,
    DocumentVersion,
    GroupDocument,
    SaveTriggerEnum,
)
from app.repositories.group_document_repository import group_document_repo


class DocumentService:

    # ── Workspace Queries ───────────────────────────────────────────────────

    async def get_workspace_documents(
        self, db: AsyncSession, chat_session_id: str
    ) -> List[GroupDocument]:
        """Return all document tabs linked to a workspace session."""
        return await group_document_repo.get_documents_for_session(db, chat_session_id)

    async def get_document(
        self, db: AsyncSession, doc_id: UUID
    ) -> Optional[GroupDocument]:
        return await group_document_repo.get_by_id(db, doc_id)

    # ── Document Creation ───────────────────────────────────────────────────

    async def create_document(
        self,
        db: AsyncSession,
        group_id: UUID,
        doc_type: str,
        title: str,
        created_by: UUID,
        chat_session_id: Optional[str] = None,
        content: Optional[dict] = None,
    ) -> GroupDocument:
        doc = await group_document_repo.create_document(
            db,
            group_id=group_id,
            doc_type=doc_type,
            title=title,
            created_by=created_by,
            chat_session_id=chat_session_id,
            content=content,
        )
        await db.commit()
        await db.refresh(doc)
        return doc

    # ── Autosave (Optimistic Locking) ───────────────────────────────────────

    async def autosave_document(
        self,
        db: AsyncSession,
        doc_id: UUID,
        content: dict,
        expected_lock_version: int,
        updated_by: UUID,
    ) -> GroupDocument:
        """
        Persist the live draft. Raises HTTP 409 on version conflict.
        Does NOT create a version snapshot row.
        """
        doc = await group_document_repo.autosave(
            db,
            doc_id=doc_id,
            content=content,
            expected_lock_version=expected_lock_version,
            updated_by=updated_by,
        )
        await db.commit()
        return doc

    async def rename_document(
        self,
        db: AsyncSession,
        doc_id: UUID,
        title: str,
        updated_by: UUID,
    ) -> GroupDocument:
        doc = await group_document_repo.rename_document(
            db, doc_id=doc_id, title=title, updated_by=updated_by
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        await db.commit()
        return doc

    # ── Snapshot Versioning ─────────────────────────────────────────────────

    async def create_version_snapshot(
        self,
        db: AsyncSession,
        doc_id: UUID,
        save_trigger: SaveTriggerEnum,
        created_by: UUID,
    ) -> DocumentVersion:
        """
        Creates an immutable snapshot from the current live content.
        Called on: manual save, accepted AI edit, or PDF export.
        """
        snapshot = await group_document_repo.create_snapshot(
            db,
            doc_id=doc_id,
            save_trigger=save_trigger,
            created_by=created_by,
        )
        await db.commit()
        await db.refresh(snapshot)
        return snapshot

    async def list_versions(
        self, db: AsyncSession, doc_id: UUID
    ) -> List[DocumentVersion]:
        return await group_document_repo.get_versions(db, doc_id)

    # ── File Tracking ───────────────────────────────────────────────────────

    async def register_file(
        self,
        db: AsyncSession,
        document_id: UUID,
        uploaded_by: UUID,
        file_name: str,
        storage_key: str,
        file_purpose: str,
        mime_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
        version_number: Optional[int] = None,
    ) -> DocumentFile:
        f = await group_document_repo.create_file(
            db,
            document_id=document_id,
            uploaded_by=uploaded_by,
            file_name=file_name,
            storage_key=storage_key,
            file_purpose=file_purpose,
            mime_type=mime_type,
            size_bytes=size_bytes,
            version_number=version_number,
        )
        await db.commit()
        await db.refresh(f)
        return f


document_service = DocumentService()
