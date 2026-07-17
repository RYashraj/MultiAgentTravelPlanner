import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    settings = get_settings()
    original_secret = settings.supabase_jwt_secret
    settings.supabase_jwt_secret = "week-3-test-secret"
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    settings.supabase_jwt_secret = original_secret
    Base.metadata.drop_all(engine)


@pytest.fixture()
def auth_headers():
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "traveler@example.com", "aud": "authenticated"},
        "week-3-test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
