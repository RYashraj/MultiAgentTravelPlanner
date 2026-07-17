from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.db.models import User
from pydantic import BaseModel
import uuid

router = APIRouter(prefix="/auth", tags=["auth"])

class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None

    class Config:
        from_attributes = True

@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Returns the authenticated user details based on the verified JWT token.
    """
    return current_user
