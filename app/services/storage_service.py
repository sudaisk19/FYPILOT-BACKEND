# app/services/storage_service.py
"""Utility helpers for uploading user-provided files to Supabase Storage."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from supabase import Client

from app.core.config import settings

ANNOUNCEMENTS_BUCKET = "announcement_files"
SUBMISSION_FILES_BUCKET = "submission_files"
DOCUMENT_FILES_BUCKET = "group_document_files"


def get_public_file_url(bucket: str, storage_key: str) -> str:
    """Build a public Supabase Storage URL for a file.
    
    Args:
        bucket: The Supabase bucket name
        storage_key: The file path within the bucket
        
    Returns:
        Full public URL to access the file
    """
    supabase_url = settings.supabase_url.rstrip("/")
    return f"{supabase_url}/storage/v1/object/public/{bucket}/{storage_key}"


def _coerce_error(response: Optional[dict]) -> Optional[str]:
    """Extract an error message from Supabase responses if present."""
    if isinstance(response, dict):
        error = response.get("error")
        if isinstance(error, dict) and "message" in error:
            return error["message"]
        if isinstance(error, str):
            return error
    return None


async def upload_file_to_supabase(
    client: Client,
    *,
    bucket: str,
    storage_key: str,
    upload: UploadFile,
    upsert: bool = False,
) -> int:
    """Upload a FastAPI `UploadFile` object into Supabase Storage.

    Returns the number of bytes uploaded (file size).
    """
    data = await upload.read()
    content_type = upload.content_type or "application/octet-stream"

    def _upload() -> Optional[dict]:
        return client.storage.from_(bucket).upload(
            path=storage_key,
            file=data,
            file_options={"content-type": content_type, "upsert": upsert},
        )

    try:
        response = await asyncio.wait_for(
            run_in_threadpool(_upload),
            timeout=settings.storage_upload_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                "File upload timed out while contacting storage service. "
                "Please retry with a smaller file or try again shortly."
            ),
        ) from exc

    error_message = _coerce_error(response)
    if error_message:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload file: {error_message}",
        )

    return len(data)


async def delete_file_from_supabase(
    client: Client,
    *,
    bucket: str,
    storage_key: str,
) -> None:
    """Delete a file from Supabase Storage; ignore if already missing."""

    def _delete() -> Optional[dict]:
        return client.storage.from_(bucket).remove([storage_key])

    response = await run_in_threadpool(_delete)
    print(f"DEBUG: Supabase Response for {storage_key}: {response}")
    error_message = _coerce_error(response)
    if error_message:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete file: {error_message}",
        )


async def download_file_from_supabase(
    client: Client,
    *,
    bucket: str,
    storage_key: str,
) -> bytes:
    """Download a file from Supabase Storage and return its raw bytes."""

    def _download() -> bytes:
        # Supabase Python client's download returns bytes directly
        return client.storage.from_(bucket).download(storage_key)

    try:
        data = await run_in_threadpool(_download)
        return data
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download file: {str(e)}",
        )
