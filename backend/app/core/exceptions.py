"""
Global exception handling and error sanitization module.

Ensures client responses NEVER expose stack traces, internal file paths,
database connections, credentials, or raw third-party provider errors.
Full diagnostic details are logged internally.
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def setup_exception_handlers(app: FastAPI) -> None:
    """Registers global exception handlers on the FastAPI application."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Sanitizes Pydantic request validation errors into a clean, safe JSON format."""
        formatted_errors = []
        for error in exc.errors():
            loc = " -> ".join([str(x) for x in error.get("loc", []) if x != "body"])
            msg = error.get("msg", "Invalid value")
            formatted_errors.append({"field": loc or "request_body", "message": msg})

        logger.warning(
            "Validation error on %s %s: %s",
            request.method,
            request.url.path,
            formatted_errors,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Input validation failed",
                "errors": formatted_errors,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Handles explicit HTTP exceptions cleanly without stack trace leakage."""
        logger.info("HTTP %s on %s %s: %s", exc.status_code, request.method, request.url.path, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Catch-all handler for unhandled exceptions.
        Logs full diagnostic traceback internally, but returns a safe, sanitized
        message to the client in production mode.
        """
        logger.exception("Unhandled Exception on %s %s: %s", request.method, request.url.path, exc)

        settings = get_settings()
        if settings.environment == "development":
            # In local dev mode, return helpful error info
            error_message = f"Internal Server Error: {str(exc)}"
        else:
            # Production mode: strict error masking
            error_message = "An internal server error occurred. Please try again later."

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": error_message},
        )
