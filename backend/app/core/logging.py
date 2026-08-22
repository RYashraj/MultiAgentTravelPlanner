import logging
from contextvars import ContextVar

from pythonjsonlogger import json as jsonlogger

# Context variable to hold the request ID
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class RequestIdFilter(logging.Filter):
    """Injects the current request ID into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def setup_logging():
    """Configure structured JSON logging."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Clear existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    handler = logging.StreamHandler()
    
    # We want these fields in our JSON logs
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s",
        rename_fields={
            "levelname": "level",
            "asctime": "timestamp",
            "name": "logger_name"
        }
    )
    
    handler.setFormatter(formatter)
    
    # Add the filter to inject request_id
    handler.addFilter(RequestIdFilter())
    logger.addHandler(handler)
    
    # Also apply to uvicorn/fastapi loggers if they exist
    for logger_name in ("uvicorn", "uvicorn.access", "fastapi"):
        l = logging.getLogger(logger_name)
        l.handlers = []
        l.addHandler(handler)
        l.addFilter(RequestIdFilter())

