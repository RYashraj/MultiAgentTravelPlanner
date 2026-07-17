"""
Dependencies for VoyagerAI API endpoints.
Includes database session and Supabase authentication JWT verification.
"""
import logging
import uuid
import json
import redis
# pyrefly: ignore [missing-import]
import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.db.models import User
from app.repositories.user import UserRepository

logger = logging.getLogger(__name__)
settings = get_settings()
security = HTTPBearer(auto_error=False)

# Initialize Redis client with fallback
redis_client = None
if settings.redis_url:
    try:
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    except Exception as e:
        logger.warning(f"Failed to initialize Redis client: {e}")

def get_cached_user(user_id: uuid.UUID, db: Session) -> User | None:
    """
    Retrieves user details from Redis cache if available.
    Falls back to querying the database and caches the retrieved user details.
    """
    user_repo = UserRepository(db)
    cache_key = f"user_session:{str(user_id)}"
    
    if redis_client:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                data = json.loads(cached_data)
                logger.info(f"Redis cache hit for user {data.get('email')}")
                return User(
                    id=uuid.UUID(data["id"]),
                    email=data["email"],
                    full_name=data.get("full_name")
                )
        except Exception as e:
            logger.warning(f"Error reading from Redis cache: {e}")
            
    # Fallback to DB
    user = user_repo.get_by_id(user_id)
    if user and redis_client:
        try:
            user_data = {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name
            }
            redis_client.setex(cache_key, 3600, json.dumps(user_data))
            logger.info(f"Cached user {user.email} in Redis")
        except Exception as e:
            logger.warning(f"Error writing to Redis cache: {e}")
            
    return user

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Decodes the Supabase JWT access token to authenticate the user.
    If SUPABASE_JWT_SECRET is empty/not configured, runs in Mock Auth Mode
    using Bearer tokens starting with 'mock-user-'.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Header",
        )
    
    token = credentials.credentials
    user_repo = UserRepository(db)
    
    # Dev/Mock Auth Fallback
    if not settings.supabase_jwt_secret:
        if token.startswith("mock-user-"):
            email = token.replace("mock-user-", "")
            if not email.endswith(".com") and "@" not in email:
                email = f"{email}@example.com"
            elif "@" not in email:
                email = f"{email}@example.com"
                
            # Create a deterministic UUID based on email
            mock_id = uuid.uuid5(uuid.NAMESPACE_DNS, email)
            user = get_cached_user(mock_id, db)
            if not user:
                user = user_repo.create(user_id=mock_id, email=email, full_name=email.split("@")[0].capitalize())
                logger.info(f"Mock Auth Mode: Created mock user {email} ({mock_id})")
                if redis_client:
                    try:
                        redis_client.setex(f"user_session:{str(mock_id)}", 3600, json.dumps({
                            "id": str(user.id),
                            "email": user.email,
                            "full_name": user.full_name
                        }))
                    except Exception as e:
                        pass
            return user
            
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_JWT_SECRET is not configured on the backend. Use 'mock-user-<email>' as Bearer token for dev bypass.",
        )

    try:
        # Decode Supabase JWT signed with HS256 using the JWT Secret
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": True},
            audience="authenticated"
        )
        
        user_id_str = payload.get("sub")
        email = payload.get("email")
        
        if not user_id_str or not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: missing sub or email",
            )
            
        user_id = uuid.UUID(user_id_str)
        
        user = get_cached_user(user_id, db)
        if not user:
            # Sync user metadata from JWT if available
            user_metadata = payload.get("user_metadata", {})
            full_name = user_metadata.get("full_name") or user_metadata.get("name")
            user = user_repo.create(user_id=user_id, email=email, full_name=full_name)
            logger.info(f"Supabase Auth Mode: Synced authenticated user {email} ({user_id})")
            if redis_client:
                try:
                    redis_client.setex(f"user_session:{str(user_id)}", 3600, json.dumps({
                        "id": str(user.id),
                        "email": user.email,
                        "full_name": user.full_name
                    }))
                except Exception as e:
                    pass
            
        return user
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )
