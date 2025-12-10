# app/core/error_handlers.py
"""
Custom Exception Handlers

This module provides standardized error handling and response formatting.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.error_schema import ErrorDetail, ErrorResponse, LoginErrorCodes

logger = logging.getLogger(__name__)


def format_error_response(
    error_message: str,
    error_code: str,
    details: Optional[List[ErrorDetail]] = None,
    status_code: int = 500,
) -> JSONResponse:
    """
    Format a standardized error response.

    Args:
        error_message: Human-readable error message
        error_code: Machine-readable error code
        details: Optional list of error details
        status_code: HTTP status code

    Returns:
        JSONResponse with standardized error structure
    """
    error_response = ErrorResponse(
        success=False,
        error=error_message,
        error_code=error_code,
        details=details,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    return JSONResponse(
        status_code=status_code, content=error_response.model_dump(exclude_none=True)
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors (422).

    Converts FastAPI validation errors to standardized format.
    """
    details = []
    error_messages = []

    for error in exc.errors():
        field = error["loc"][-1] if error["loc"] else None
        message = error["msg"]
        error_messages.append(f"{field}: {message}" if field else message)

        details.append(
            ErrorDetail(
                field=str(field) if field else None,
                message=message,
                code=error["type"],
            )
        )

    # Determine main error message
    if len(details) == 1:
        main_error = details[0].message
        if details[0].field == "email":
            error_code = LoginErrorCodes.INVALID_EMAIL_FORMAT
        elif details[0].field == "password":
            error_code = LoginErrorCodes.MISSING_PASSWORD
        else:
            error_code = LoginErrorCodes.VALIDATION_ERROR
    else:
        main_error = "Multiple validation errors"
        error_code = LoginErrorCodes.VALIDATION_ERROR

    logger.warning(f"Validation error on {request.url.path}: {error_messages}")

    return format_error_response(
        error_message=main_error,
        error_code=error_code,
        details=details,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handle HTTPException with standardized format.

    Converts FastAPI HTTPException to standardized error response.
    """
    # Map status codes to error codes
    error_code_map = {
        401: LoginErrorCodes.INVALID_CREDENTIALS,
        500: LoginErrorCodes.INTERNAL_ERROR,
        503: LoginErrorCodes.UNAVAILABLE,
    }

    error_code = error_code_map.get(exc.status_code, "UNKNOWN_ERROR")

    logger.warning(
        f"HTTP {exc.status_code} on {request.url.path}: {exc.detail}",
        extra={"status_code": exc.status_code, "detail": exc.detail},
    )

    return format_error_response(
        error_message=str(exc.detail),
        error_code=error_code,
        details=None,
        status_code=exc.status_code,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions with standardized format.

    Catches all unhandled exceptions and returns consistent error response.
    """
    logger.error(
        f"Unhandled exception on {request.url.path}: {str(exc)}",
        exc_info=True,
        extra={"path": request.url.path, "method": request.method},
    )

    return format_error_response(
        error_message="An unexpected error occurred. Please try again later.",
        error_code=LoginErrorCodes.INTERNAL_ERROR,
        details=None,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
