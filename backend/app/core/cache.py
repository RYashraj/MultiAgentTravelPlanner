"""Best-effort Redis cache for authenticated user session identity.

JWT validation remains the source of truth. Redis makes repeated session lookups
fast for agent features without making the MVP depend on Redis being available.
"""
import hashlib
import json
import logging
from functools import lru_cache, wraps

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


def with_redis_cache(ttl_seconds: int = 3600, key_prefix: str = "cache"):
    """
    Decorator that caches function output in Redis using the shared singleton client.
    Fails open (calls original function) if Redis is unreachable.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = ""
            client = None
            try:
                key_args = f"{args}-{kwargs}".encode("utf-8")
                key_hash = hashlib.md5(key_args).hexdigest()
                cache_key = f"voyagerai:{key_prefix}:{func.__name__}:{key_hash}"
                client = get_session_cache().client
                cached = client.get(cache_key)
                if cached:
                    return json.loads(str(cached))
            except redis.RedisError as exc:
                logger.warning("Redis unavailable for cache read (%s): %s", func.__name__, exc)
            except Exception as exc:
                logger.warning("Error reading from cache (%s): %s", func.__name__, exc)

            result = func(*args, **kwargs)

            if client is not None and cache_key:
                try:
                    client.setex(cache_key, ttl_seconds, json.dumps(result))
                except redis.RedisError as exc:
                    logger.warning("Redis unavailable for cache write (%s): %s", func.__name__, exc)
                except Exception as exc:
                    logger.warning("Error writing to cache (%s): %s", func.__name__, exc)

            return result
        return wrapper
    return decorator
