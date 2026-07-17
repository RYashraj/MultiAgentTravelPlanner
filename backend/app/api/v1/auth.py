from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.repositories import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def current_account(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Confirm the Supabase token and synchronize its account into our database."""
    local_user = UserRepository(db).upsert(user.id, user.email, user.full_name)
    return {"id": str(local_user.id), "email": local_user.email, "full_name": local_user.full_name}
