"""File upload/download service using Supabase Storage."""

import mimetypes
from typing import Tuple
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.db import supabase


class FileService:
    """Service for handling file uploads and downloads with Supabase Storage."""

    BUCKET_NAME = "announcement_files"  # Supabase storage bucket name
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max file size

    @staticmethod
    async def upload_file(
        file: UploadFile, folder: str = "announcements"
    ) -> Tuple[str, str, int, str]:
        """
        Upload a file to Supabase Storage.

        Args:
            file: The uploaded file from FastAPI
            folder: Subfolder within the bucket (e.g., "announcements", "submissions")

        Returns:
            Tuple of (storage_key, file_name, size_bytes, mime_type)

        Raises:
            HTTPException: If upload fails or file is too large
        """
        # Read file content
        content = await file.read()
        file_size = len(content)

        # Check file size
        if file_size > FileService.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds maximum allowed size of {FileService.MAX_FILE_SIZE / (1024*1024)}MB",
            )

        # Generate unique file name
        file_extension = ""
        if file.filename:
            parts = file.filename.rsplit(".", 1)
            if len(parts) > 1:
                file_extension = f".{parts[1]}"

        unique_name = f"{uuid4()}{file_extension}"
        storage_path = f"{folder}/{unique_name}"

        # Determine MIME type
        mime_type = file.content_type
        if not mime_type and file.filename:
            mime_type, _ = mimetypes.guess_type(file.filename)
        mime_type = mime_type or "application/octet-stream"

        try:
            # Upload to Supabase Storage
            result = supabase.storage.from_(FileService.BUCKET_NAME).upload(
                path=storage_path,
                file=content,
                file_options={"content-type": mime_type},
            )

            # Get public URL
            supabase.storage.from_(FileService.BUCKET_NAME).get_public_url(storage_path)

            return (storage_path, file.filename or unique_name, file_size, mime_type)

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to upload file: {str(e)}"
            )

    @staticmethod
    async def upload_multiple_files(
        files: list[UploadFile], folder: str = "announcements"
    ) -> list[dict]:
        """
        Upload multiple files to Supabase Storage.

        Args:
            files: List of uploaded files
            folder: Subfolder within the bucket

        Returns:
            List of dicts with file metadata
        """
        uploaded_files = []

        for file in files:
            storage_key, file_name, size_bytes, mime_type = (
                await FileService.upload_file(file, folder)
            )

            uploaded_files.append(
                {
                    "storage_key": storage_key,
                    "file_name": file_name,
                    "size_bytes": size_bytes,
                    "mime_type": mime_type,
                }
            )

        return uploaded_files

    @staticmethod
    def get_file_url(storage_key: str) -> str:
        """
        Get public URL for a file.

        Args:
            storage_key: The storage path/key

        Returns:
            Public URL to access the file
        """
        return supabase.storage.from_(FileService.BUCKET_NAME).get_public_url(
            storage_key
        )

    @staticmethod
    async def download_file(storage_key: str) -> bytes:
        """
        Download a file from Supabase Storage.

        Args:
            storage_key: The storage path/key

        Returns:
            File content as bytes

        Raises:
            HTTPException: If download fails
        """
        try:
            result = supabase.storage.from_(FileService.BUCKET_NAME).download(
                storage_key
            )
            return result
        except Exception as e:
            raise HTTPException(
                status_code=404,
                detail=f"File not found or failed to download: {str(e)}",
            )

    @staticmethod
    async def delete_file(storage_key: str) -> bool:
        """
        Delete a file from Supabase Storage.

        Args:
            storage_key: The storage path/key

        Returns:
            True if deleted successfully

        Raises:
            HTTPException: If deletion fails
        """
        try:
            supabase.storage.from_(FileService.BUCKET_NAME).remove([storage_key])
            return True
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to delete file: {str(e)}"
            )
