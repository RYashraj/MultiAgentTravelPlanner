"""
Dependencies for VoyagerAI API endpoints.
Includes database session and Supabase authentication JWT verification.
"""
import logging
import uuid
# pyrefly: ignore [missing-import]
import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.db.models import User

logger = logging.getLogger(__name__)
settings = get_settings()
security = HTTPBearer(auto_error=False)

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
            user = db.query(User).filter(User.id == mock_id).first()
            if not user:
                user = User(id=mock_id, email=email, full_name=email.split("@")[0].capitalize())
                db.add(user)
                db.commit()
                db.refresh(user)
                logger.info(f"Mock Auth Mode: Created mock user {email} ({mock_id})")
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
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            # Sync user metadata from JWT if available
            user_metadata = payload.get("user_metadata", {})
            full_name = user_metadata.get("full_name") or user_metadata.get("name")
            user = User(id=user_id, email=email, full_name=full_name)
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"Supabase Auth Mode: Synced authenticated user {email} ({user_id})")
            
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
