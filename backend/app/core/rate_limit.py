import logging
import time

import redis
from fastapi import Request

from app.core.cache import get_session_cache
from app.core.exceptions import RateLimitExceeded

logger = logging.getLogger(__name__)

def rate_limit(requests: int = 60, window_seconds: int = 60):
    """
    FastAPI dependency for fixed-window rate limiting using Redis.
    Limits by IP address by default.
    Fails open if Redis is unreachable to avoid blocking legitimate traffic during outages.
    """
    def _rate_limit(request: Request):
        try:
            client = get_session_cache().client
            ip = request.client.host if request.client else "127.0.0.1"
            # Use current time divided by window to create fixed time buckets
            window_bucket = int(time.time() // window_seconds)
            key = f"voyagerai:rate_limit:{ip}:{window_bucket}"
            
            # Use a pipeline for atomic increment and expire
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds + 5) # slight buffer
            result = pipe.execute()
            
            count = result[0]
            if count > requests:
                logger.warning(f"Rate limit exceeded for IP {ip} ({count}/{requests} requests)")
                raise RateLimitExceeded(f"Rate limit exceeded. Maximum {requests} requests per {window_seconds} seconds.")
                
        except redis.RedisError as e:
            logger.warning(f"Redis error during rate limiting: {e}. Failing open.")
            # Fail open - we don't want to block users just because cache is down
        except RateLimitExceeded:
            raise # re-raise the intended exception
        except Exception as e:
            logger.error(f"Unexpected error in rate limiting: {e}")
            
    return _rate_limit
