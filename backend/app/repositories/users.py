import uuid

from sqlalchemy.orm import Session

from app.db.models import User


class UserRepository:
    def __init__(self, db: Session): self.db = db

    def upsert(self, user_id: uuid.UUID, email: str, full_name: str | None = None) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            user = User(id=user_id, email=email, full_name=full_name)
            self.db.add(user)
        else:
            user.email = email
            user.full_name = full_name or user.full_name
        self.db.commit(); self.db.refresh(user)
        return user
