# app/schemas/error_schema.py
"""
Standardized Error Response Schemas

This module provides consistent error response structures across all endpoints.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Individual error detail for validation errors."""

    field: Optional[str] = Field(None, description="Field name that caused the error")
    message: str = Field(..., description="Human-readable error message")
    code: Optional[str] = Field(None, description="Machine-readable error code")


class ErrorResponse(BaseModel):
    """Standardized error response structure for all endpoints."""

    success: bool = Field(False, description="Always false for errors")
    error: str = Field(..., description="Main error message")
    error_code: str = Field(..., description="Machine-readable error code")
    details: Optional[List[ErrorDetail]] = Field(
        None, description="Additional error details (for validation errors)"
    )
    timestamp: Optional[str] = Field(None, description="Error timestamp (ISO format)")

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "Invalid email or password",
                "error_code": "AUTH_INVALID_CREDENTIALS",
                "details": None,
                "timestamp": "2025-12-10T10:30:00Z",
            }
        }


# Error codes for login endpoint
class LoginErrorCodes:
    """Standard error codes for login endpoint."""

    # Authentication errors (401)
    INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"

    # Validation errors (400/422)
    MISSING_EMAIL = "VALIDATION_MISSING_EMAIL"
    MISSING_PASSWORD = "VALIDATION_MISSING_PASSWORD"
    INVALID_EMAIL = "VALIDATION_INVALID_EMAIL"
    VALIDATION_ERROR = "VALIDATION_ERROR"  # Multiple validation errors

    # Server errors (500)
    DATABASE_ERROR = "SERVER_DATABASE_ERROR"
    INTERNAL_ERROR = "SERVER_INTERNAL_ERROR"

    # Service errors (503)
    UNAVAILABLE = "SERVER_UNAVAILABLE"
