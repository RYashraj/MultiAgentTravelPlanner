from sqlalchemy.orm import Session
from app.db.models import User
import uuid

class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def create(self, user_id: uuid.UUID, email: str, full_name: str | None = None) -> User:
        user = User(id=user_id, email=email, full_name=full_name)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
