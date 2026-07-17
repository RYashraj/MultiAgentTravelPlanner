"""Best-effort Redis cache for authenticated user session identity.

JWT validation remains the source of truth. Redis makes repeated session lookups
available to later agent features without making the Week 3 MVP depend on Redis.
"""
import json
import logging
from functools import lru_cache

import redis

from app.core.config import get_settings
from app.core.security import CurrentUser

logger = logging.getLogger(__name__)


class RedisSessionCache:
    def __init__(self) -> None:
        settings = get_settings()
        self.ttl_seconds = settings.redis_session_ttl_seconds
        self.client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )

    def cache_user(self, user: CurrentUser) -> None:
        """Cache non-sensitive identity data; failures never block an API request."""
        payload = json.dumps({"id": str(user.id), "email": user.email, "full_name": user.full_name})
        try:
            self.client.setex(f"voyagerai:session:{user.id}", self.ttl_seconds, payload)
        except redis.RedisError:
            logger.debug("Redis unavailable; continuing without session cache")


@lru_cache
def get_session_cache() -> RedisSessionCache:
    return RedisSessionCache()
