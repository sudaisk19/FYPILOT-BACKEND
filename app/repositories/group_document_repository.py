"""
Group Document Repository
Handles all Postgres CRUD for group_documents, document_versions, document_files.
"""

import json
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group_document import (
    DocumentFile,
    DocumentVersion,
    GroupDocument,
    SaveTriggerEnum,
)
from app.repositories.base import BaseRepository


class GroupDocumentRepository(BaseRepository[GroupDocument]):
    def __init__(self):
        super().__init__(GroupDocument)

    # ── Document Queries ────────────────────────────────────────────────────

    async def get_by_id(
        self, db: AsyncSession, doc_id: UUID
    ) -> Optional[GroupDocument]:
        """Fetch a single document by its PK."""
        result = await db.execute(
            select(GroupDocument).where(GroupDocument.id == doc_id)
        )
        return result.scalars().first()

    async def get_documents_for_session(
        self, db: AsyncSession, chat_session_id: str
    ) -> List[GroupDocument]:
        """Return all active documents that belong to a workspace (chat session)."""
        result = await db.execute(
            select(GroupDocument)
            .where(
                GroupDocument.chat_session_id == chat_session_id,
                GroupDocument.is_active.is_(True),
            )
            .order_by(GroupDocument.created_at)
        )
        return list(result.scalars().all())

    async def get_documents_for_group(
        self, db: AsyncSession, group_id: UUID, active_only: bool = True
    ) -> List[GroupDocument]:
        """Return all documents for a group, optionally filtering by is_active."""
        q = select(GroupDocument).where(GroupDocument.group_id == group_id)
        if active_only:
            q = q.where(GroupDocument.is_active.is_(True))
        q = q.order_by(GroupDocument.created_at)
        result = await db.execute(q)
        return list(result.scalars().all())

    # ── Document Mutations ──────────────────────────────────────────────────

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
        """Create a new live draft document."""
        doc = GroupDocument(
            group_id=group_id,
            chat_session_id=chat_session_id,
            doc_type=doc_type,
            title=title,
            content=content or {},
            lock_version=1,
            is_active=True,
            created_by=created_by,
            updated_by=created_by,
        )
        db.add(doc)
        await db.flush()
        await db.refresh(doc)
        return doc

    async def autosave(
        self,
        db: AsyncSession,
        doc_id: UUID,
        content: dict,
        expected_lock_version: int,
        updated_by: UUID,
    ) -> GroupDocument:
        """
        Optimistic-lock autosave:
        UPDATE group_documents
        SET content=:c, lock_version=lock_version+1, updated_by=:u
        WHERE id=:id AND lock_version=:expected
        RETURNING *

        Raises HTTP 409 if another writer incremented the version first.
        """
        stmt = (
            update(GroupDocument)
            .where(
                GroupDocument.id == doc_id,
                GroupDocument.lock_version == expected_lock_version,
            )
            .values(
                content=content,
                lock_version=GroupDocument.lock_version + 1,
                updated_by=updated_by,
            )
            .returning(GroupDocument)
        )
        result = await db.execute(stmt)
        row = result.scalars().first()

        if row is None:
            # Either doc doesn't exist or version mismatch
            existing = await self.get_by_id(db, doc_id)
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Document not found."
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Autosave conflict: expected lock_version={expected_lock_version}, "
                    f"current={existing.lock_version}. "
                    "Your teammate made changes. Please refresh to sync."
                ),
            )
        await db.flush()
        return row

    async def rename_document(
        self,
        db: AsyncSession,
        doc_id: UUID,
        title: str,
        updated_by: UUID,
    ) -> Optional[GroupDocument]:
        """Rename a document regardless of lock_version."""
        stmt = (
            update(GroupDocument)
            .where(GroupDocument.id == doc_id)
            .values(
                title=title,
                updated_by=updated_by,
                # Optionally, bump lock_version so other clients know it changed?
                # lock_version=GroupDocument.lock_version + 1,
            )
            .returning(GroupDocument)
        )
        result = await db.execute(stmt)
        row = result.scalars().first()
        if row:
            await db.flush()
        return row

    # ── Version Snapshots ───────────────────────────────────────────────────

    async def get_next_version_number(self, db: AsyncSession, doc_id: UUID) -> int:
        """Compute the next sequential version number for a document."""
        result = await db.execute(
            select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
                DocumentVersion.document_id == doc_id
            )
        )
        return (result.scalar_one() or 0) + 1

    async def create_snapshot(
        self,
        db: AsyncSession,
        doc_id: UUID,
        save_trigger: SaveTriggerEnum,
        created_by: UUID,
    ) -> DocumentVersion:
        """
        Reads the live content of a document and inserts an immutable
        snapshot row in document_versions.
        """
        doc = await self.get_by_id(db, doc_id)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found."
            )

        version_number = await self.get_next_version_number(db, doc_id)

        snapshot = DocumentVersion(
            document_id=doc_id,
            version_number=version_number,
            content=json.dumps(doc.content or {}),
            save_trigger=save_trigger,
            created_by=created_by,
        )
        db.add(snapshot)
        await db.flush()
        await db.refresh(snapshot)
        return snapshot

    async def get_versions(
        self, db: AsyncSession, doc_id: UUID
    ) -> List[DocumentVersion]:
        """List all version snapshots for a document, newest first."""
        result = await db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == doc_id)
            .order_by(DocumentVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_version(
        self, db: AsyncSession, doc_id: UUID, version_number: int
    ) -> Optional[DocumentVersion]:
        result = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == doc_id,
                DocumentVersion.version_number == version_number,
            )
        )
        return result.scalars().first()

    # ── Document Files ──────────────────────────────────────────────────────

    async def create_file(
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
        df = DocumentFile(
            document_id=document_id,
            uploaded_by=uploaded_by,
            file_name=file_name,
            storage_key=storage_key,
            file_purpose=file_purpose,
            mime_type=mime_type,
            size_bytes=size_bytes,
            version_number=version_number,
        )
        db.add(df)
        await db.flush()
        await db.refresh(df)
        return df

    async def get_files(
        self, db: AsyncSession, doc_id: UUID, purpose: Optional[str] = None
    ) -> List[DocumentFile]:
        q = select(DocumentFile).where(DocumentFile.document_id == doc_id)
        if purpose:
            q = q.where(DocumentFile.file_purpose == purpose)
        result = await db.execute(q.order_by(DocumentFile.created_at.desc()))
        return list(result.scalars().all())


group_document_repo = GroupDocumentRepository()
