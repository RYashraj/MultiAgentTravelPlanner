"""
Rate Limiting Middleware for VoyagerAI backend.

Protects sensitive and high-cost routes:
  1. Auth Endpoints (/api/v1/auth/*) -> Configured via RATE_LIMIT_AUTH_RPM (default: 10/min)
  2. Message & Agent Planning Endpoints (/api/v1/trips/{id}/messages) -> Configured via RATE_LIMIT_MESSAGE_RPM (default: 20/min)
  3. General API Endpoints -> Configured via RATE_LIMIT_GENERAL_RPM (default: 120/min)

Returns clean HTTP 429 (Too Many Requests) JSON responses without leaking internal details.
"""
import collections
import logging
import time
from typing import Dict, List

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter using a timestamp deque per client key."""

    def __init__(self) -> None:
        # Maps (client_key, route_category) -> deque of request timestamps
        self._records: Dict[tuple[str, str], collections.deque] = collections.defaultdict(collections.deque)

    def is_rate_limited(self, client_key: str, category: str, limit_rpm: int, window_seconds: int = 60) -> tuple[bool, int, int]:
        """
        Checks if the request exceeds limit_rpm within window_seconds.
        Returns tuple: (is_limited, remaining_quota, retry_after_seconds)
        """
        now = time.time()
        window_start = now - window_seconds
        key = (client_key, category)
        timestamps = self._records[key]

        # Evict timestamps older than sliding window
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        if len(timestamps) >= limit_rpm:
            oldest = timestamps[0]
            retry_after = max(1, int(oldest + window_seconds - now))
            return True, 0, retry_after

        timestamps.append(now)
        remaining = max(0, limit_rpm - len(timestamps))
        return False, remaining, 0

    def reset() -> None:
        """Clear all rate limit state (useful for tests)."""
        self._records.clear()


# Global rate limiter instance
_limiter = InMemoryRateLimiter()


def get_rate_limiter() -> InMemoryRateLimiter:
    return _limiter


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces configurable sliding-window rate limits across API routes.
    Disabled safely when settings.rate_limiting_enabled is False.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()

        if not settings.rate_limiting_enabled:
            return await call_next(request)

        # Ignore static assets, docs, and root health check
        path = request.url.path
        if path.startswith("/static") or path in ("/docs", "/redoc", "/openapi.json", "/health", "/"):
            return await call_next(request)

        # Identify client (Client IP address or auth token snippet)
        client_ip = request.client.host if request.client else "127.0.0.1"
        client_key = client_ip

        # Determine route category & limit
        if path.startswith(f"{settings.api_v1_prefix}/auth"):
            category = "auth"
            limit_rpm = settings.rate_limit_auth_rpm
        elif "/messages" in path:
            category = "messages"
            limit_rpm = settings.rate_limit_message_rpm
        else:
            category = "general"
            limit_rpm = settings.rate_limit_general_rpm

        is_limited, remaining, retry_after = _limiter.is_rate_limited(client_key, category, limit_rpm)

        if is_limited:
            logger.warning(
                "Rate limit exceeded for %s on %s %s [%s: %d/min] — retry in %ds",
                client_key,
                request.method,
                path,
                category,
                limit_rpm,
                retry_after,
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded. Please wait before retrying.",
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit_rpm),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit_rpm)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
