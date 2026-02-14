from typing import Any, Dict, List
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.db import supabase
from app.services.storage_service import (
    ANNOUNCEMENTS_BUCKET,
    delete_file_from_supabase,
    upload_file_to_supabase,
)


class FileService:
    @staticmethod
    async def upload_multiple_files(
        files: List[UploadFile], folder: str
    ) -> List[Dict[str, Any]]:
        """
        Upload multiple files to Supabase storage.
        Returns a list of dictionaries containing file metadata.
        """
        results = []
        for file in files:
            # Generate unique storage key
            # Sanitize filename or just use UUID?
            # Using UUID to avoid collisions and weird characters.
            # Keep extension if present
            ext = ""
            if file.filename and "." in file.filename:
                ext = f".{file.filename.split('.')[-1]}"

            unique_name = f"{uuid4()}{ext}"
            storage_key = f"{folder}/{unique_name}"

            # Upload
            size_bytes = await upload_file_to_supabase(
                client=supabase,
                bucket=ANNOUNCEMENTS_BUCKET,
                storage_key=storage_key,
                upload=file,
            )

            results.append(
                {
                    "file_name": file.filename,
                    "storage_key": storage_key,
                    "mime_type": file.content_type,
                    "size_bytes": size_bytes,
                }
            )
        return results

    @staticmethod
    async def delete_file(storage_key: str):
        """
        Delete a file from Supabase storage.
        """
        await delete_file_from_supabase(
            client=supabase, bucket=ANNOUNCEMENTS_BUCKET, storage_key=storage_key
        )

    @staticmethod
    async def download_file(storage_key: str) -> bytes:
        """
        Download a file from Supabase storage.
        """
        try:
            # Supabase storage download returns bytes
            response = supabase.storage.from_(ANNOUNCEMENTS_BUCKET).download(
                storage_key
            )
            return response
        except Exception as e:
            # Check if it is a 404-like error from Supabase
            # Generally supabase raises an error if not found.
            raise HTTPException(
                status_code=404,
                detail=f"File not found or could not be downloaded: {str(e)}",
            )
