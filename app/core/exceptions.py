# app/core/exceptions.py

import logging

from fastapi import FastAPI
from fastapi.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError

from app.core.error_handlers import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

# Use Uvicorn's logger so uncaught errors still show up in your logs
logger = logging.getLogger("uvicorn.error")


def register_exception_handlers(app: FastAPI):
    """
    Register standardized exception handlers for the application.

    This installs global handlers for:
      1) RequestValidationError → 422 with standardized error format
      2) HTTPException → Appropriate status code with standardized format
      3) Catch-all Exception → 500 with standardized format
    """

    # Register the standardized handlers
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("Registered standardized exception handlers")
