import asyncio

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.cache import get_session_cache
from app.core.security import InvalidTokenError, verify_access_token_async


class SupabaseJWTMiddleware(BaseHTTPMiddleware):
    """Protect the Week 3 user-scoped API before route handlers are reached."""

    protected_prefixes = ("/api/v1/trips", "/api/v1/auth/me")

    async def dispatch(self, request: Request, call_next):
        # CORS preflight requests are intentionally unauthenticated.
        if request.method == "OPTIONS":
            return await call_next(request)

        if not request.url.path.startswith(self.protected_prefixes):
            return await call_next(request)

        authorization = request.headers.get("Authorization", "")

        if not authorization.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Bearer token required"},
            )

        try:
            user = await verify_access_token_async(authorization.removeprefix("Bearer ").strip())
            request.state.user = user
            await asyncio.to_thread(get_session_cache().cache_user, user)
        except InvalidTokenError as exc:
            return JSONResponse(
                status_code=401,
                content={"detail": str(exc)},
            )

        return await call_next(request)
    
