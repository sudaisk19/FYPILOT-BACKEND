# app/services/storage_service.py
"""Utility helpers for uploading user-provided files to Supabase Storage."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from supabase import Client

ANNOUNCEMENTS_BUCKET = "announcement_files"


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
        return (
            client.storage.from_(bucket)
            .upload(
                path=storage_key,
                file=data,
                file_options={"content-type": content_type, "upsert": upsert},
            )
        )

    response = await run_in_threadpool(_upload)
    error_message = _coerce_error(response)
    if error_message:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload announcement file: {error_message}",
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
    error_message = _coerce_error(response)
    if error_message:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete announcement file: {error_message}",
        )
