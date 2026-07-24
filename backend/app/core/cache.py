"""Best-effort Redis cache for authenticated user session identity.

JWT validation remains the source of truth. Redis makes repeated session lookups
available to later agent features without making the Week 3 MVP depend on Redis.
"""
import json
import logging
from functools import lru_cache, wraps
import hashlib

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
    Decorator that caches function output in Redis.
    Fails open (calls original function) if Redis is unreachable.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            client = None
            cache_key = ""
            try:
                # Build a deterministic cache key based on args
                key_args = f"{args}-{kwargs}".encode("utf-8")
                key_hash = hashlib.md5(key_args).hexdigest()
                cache_key = f"voyagerai:{key_prefix}:{func.__name__}:{key_hash}"
                
                settings = get_settings()
                client = redis.Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=0.2,
                    socket_timeout=0.2,
                )
                
                cached = client.get(cache_key)
                if cached:
                    return json.loads(str(cached))
            except redis.RedisError as e:
                logger.warning(f"Redis unavailable for cache read ({func.__name__}): {e}")
            except Exception as e:
                logger.warning(f"Error reading from cache ({func.__name__}): {e}")
                
            # Execute actual function
            result = func(*args, **kwargs)
            
            if client is not None and cache_key:
                try:
                    client.setex(cache_key, ttl_seconds, json.dumps(result))
                except redis.RedisError as e:
                    logger.warning(f"Redis unavailable for cache write ({func.__name__}): {e}")
                except Exception as e:
                    logger.warning(f"Error writing to cache ({func.__name__}): {e}")
                
            return result
        return wrapper
    return decorator
