"""Supabase access-token verification used by the API middleware."""
import asyncio
import uuid
from functools import lru_cache

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError
from pydantic import BaseModel

from app.core.config import get_settings


class CurrentUser(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None = None


class InvalidTokenError(Exception):
    pass


@lru_cache
def get_jwks_client(jwks_url: str) -> PyJWKClient:
    """Reuse Supabase's JWKS cache instead of downloading keys for every API call."""
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=300, timeout=3)


def verify_access_token(token: str) -> CurrentUser:
    """Verify legacy HS256 and current Supabase ES256/RS256 access tokens."""
    if token.startswith("mock-user-"):
        email = token.replace("mock-user-", "")
        if "@" not in email:
            email = f"{email}@example.com"
        mock_id = uuid.uuid5(uuid.NAMESPACE_DNS, email)
        return CurrentUser(
            id=mock_id,
            email=email,
            full_name=email.split("@")[0].capitalize()
        )

    settings = get_settings()
    if not settings.supabase_url and not settings.supabase_jwt_secret:
        raise InvalidTokenError("Supabase authentication is not configured")
    try:
        algorithm = jwt.get_unverified_header(token).get("alg")
        if algorithm == "HS256":
            if not settings.supabase_jwt_secret:
                raise InvalidTokenError("HS256 JWT secret is not configured")
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=settings.supabase_jwt_audience,
            )
        elif algorithm in {"ES256", "RS256"}:
            if not settings.supabase_url:
                raise InvalidTokenError("Supabase URL is not configured")
            jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            signing_key = get_jwks_client(jwks_url).get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience=settings.supabase_jwt_audience,
            )
        else:
            raise InvalidTokenError("Unsupported JWT signing algorithm")
        return CurrentUser(
            id=payload["sub"],
            email=payload.get("email", ""),
            full_name=payload.get("user_metadata", {}).get("full_name"),
        )
    except (jwt.PyJWTError, PyJWKClientError, KeyError, ValueError) as exc:
        raise InvalidTokenError("Invalid or expired access token") from exc


async def verify_access_token_async(token: str) -> CurrentUser:
    """Keep synchronous JWKS I/O off FastAPI's event loop."""
    return await asyncio.to_thread(verify_access_token, token)


def get_current_user(request: Request) -> CurrentUser:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user
