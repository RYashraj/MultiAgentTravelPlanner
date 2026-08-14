"""
Structured logging, Request ID context propagation, and Sentry integration.

Features:
  - Generates or propagates X-Request-ID header across API logs.
  - Formats structured, readable logs without leaking credentials, Bearer tokens, or passwords.
  - Safe, optional Sentry SDK initialization (disabled gracefully if SENTRY_DSN is missing).
"""
import contextvars
import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import get_settings

# ContextVar to store current request ID for logging formatters across async tasks
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="req_sys")


class RequestIdLogFilter(logging.Filter):
    """Injects current request_id into standard log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that attaches a unique X-Request-ID header to every request,
    propagates it through application loggers, and logs safe HTTP metrics.
    Never logs sensitive headers (Authorization, Cookie, API Keys) or request body passwords.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()

        # Extract or generate Request ID
        req_id = request.headers.get("X-Request-ID")
        if not req_id or not req_id.strip():
            req_id = f"req_{uuid.uuid4().hex[:8]}"

        request.state.request_id = req_id
        token = request_id_var.set(req_id)

        _logger = logging.getLogger("app.request")

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Attach Request ID to response headers (covers 401, 422, 429, 2xx, etc.)
            response.headers["X-Request-ID"] = req_id

            _logger.info(
                "%s %s -> %s (%.2fms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            return response
        except Exception as exc:
            # Starlette BaseHTTPMiddleware re-raises exceptions from inner middleware
            # rather than converting them to responses.  We catch here so we can
            # construct a 500 response that carries X-Request-ID before re-raising
            # to the global exception handler registered via setup_exception_handlers().
            duration_ms = (time.perf_counter() - start_time) * 1000
            _logger.exception(
                "%s %s -> 500 UNHANDLED (%.2fms): %s",
                request.method,
                request.url.path,
                duration_ms,
                exc,
            )
            # Import here to avoid circular imports at module load time
            from app.core.config import get_settings as _get_settings
            settings = _get_settings()
            if settings.environment == "development":
                detail = f"Internal Server Error: {exc}"
            else:
                detail = "An internal server error occurred. Please try again later."
            from fastapi.responses import JSONResponse as _JSONResponse
            err_response = _JSONResponse(
                status_code=500,
                content={"detail": detail},
                headers={"X-Request-ID": req_id},
            )
            return err_response
        finally:
            request_id_var.reset(token)



def setup_structured_logging() -> None:
    """Configures application-wide logging with Request ID filters and formatted output."""
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Attach Request ID filter to root handlers
    handler_filter = RequestIdLogFilter()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(request_id)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.addFilter(handler_filter)
        root_logger.addHandler(console_handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)
            handler.addFilter(handler_filter)


def setup_sentry() -> bool:
    """
    Initializes Sentry error monitoring if SENTRY_DSN is configured.
    Safely degrades if SENTRY_DSN is empty or sentry-sdk package is absent.
    Returns True if active, False if disabled/unverified.
    """
    settings = get_settings()
    logger = logging.getLogger(__name__)

    if not settings.sentry_dsn or not settings.sentry_dsn.strip():
        logger.info("Sentry DSN not configured — error monitoring safely disabled.")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=1.0,
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
        )
        logger.info("Sentry integration initialized successfully for environment: %s", settings.environment)
        return True
    except ImportError:
        logger.warning("Sentry DSN configured, but 'sentry-sdk' package is not installed. Sentry monitoring skipped.")
        return False
    except Exception as exc:
        logger.error("Failed to initialize Sentry: %s", exc)
        return False
