# app/core/exceptions.py

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import (
    RequestValidationError,
)
from fastapi.responses import JSONResponse

# Use Uvicorn's logger so uncaught errors still show up in your logs
logger = logging.getLogger("uvicorn.error")


def register_exception_handlers(app: FastAPI):
    """
    Call this once in your main setup:
        register_exception_handlers(app)

    It installs three global handlers:
      1) RequestValidationError → 422 with details of each field error
      2) HTTPException (400,404, etc.) → status code + single message
      3) Catch-all Exception → 500 with generic message
    """

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """
        Handles Pydantic validation failures (e.g. missing/invalid fields).
        This now safely stringifies all loc parts.
        """
        formatted = [
            {
                # err["loc"] might be ("body", 12) for JSON parse errors,
                # so convert each piece to str before joining.
                "field": ".".join(str(item) for item in err["loc"][1:]),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "status": "error",
                "error": {
                    "code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "type": "ValidationError",
                    "details": formatted,
                },
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """
        Catches any HTTPException raised in your endpoints, e.g.:
            raise HTTPException(404, "Not Found")
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": {
                    "code": exc.status_code,
                    "type": exc.__class__.__name__,
                    "message": exc.detail,
                },
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """
        Last‐resort catch‐all. Logs the exception and returns a generic 500.
        """
        logger.error(f"Unhandled error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "error": {
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "type": "InternalServerError",
                    "message": "An unexpected error occurred.",
                },
            },
        )
