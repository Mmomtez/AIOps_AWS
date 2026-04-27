from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("INSTANCE_ID", "i-local")
os.environ.setdefault("S3_BUCKET_NAME", "local-bucket")
os.environ.setdefault("LOG_GROUP_NAME", "local-log-group")

from backend.api.auth import router as auth_router
from backend.db.base import Base
from backend.db.session import get_db
from backend.models.auth import RefreshToken, User, UserRole
from backend.services.auth_service import (
    confirm_email_verification,
    confirm_password_reset,
    request_email_verification,
    request_password_reset,
)


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(auth_router)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def test_register_login_refresh_logout_flow(client: TestClient, db_session: Session) -> None:
    register_response = client.post("/auth/register", json={"email": "user@example.com", "password": "StrongPass123"})
    assert register_response.status_code == 200

    login_response = client.post("/auth/login", json={"email": "user@example.com", "password": "StrongPass123"})
    assert login_response.status_code == 200
    tokens = login_response.json()["tokens"]
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "user@example.com"

    refresh_response = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh_response.status_code == 200
    new_tokens = refresh_response.json()["tokens"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    old_refresh = db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash.is_not(None)).order_by(RefreshToken.created_at.asc())
    ).scalars().first()
    assert old_refresh is not None
    assert old_refresh.revoked_at is not None

    logout_response = client.post("/auth/logout", json={"refresh_token": new_tokens["refresh_token"]})
    assert logout_response.status_code == 200


def test_lockout_after_repeated_failed_logins(client: TestClient) -> None:
    client.post("/auth/register", json={"email": "lock@example.com", "password": "StrongPass123"})
    for _ in range(5):
        client.post("/auth/login", json={"email": "lock@example.com", "password": "WrongPass123"})
    locked_response = client.post("/auth/login", json={"email": "lock@example.com", "password": "StrongPass123"})
    assert locked_response.status_code == 429


def test_email_verification_and_password_reset(db_session: Session) -> None:
    user = User(email="verify@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    verify_token = request_email_verification(db_session, user.email, "127.0.0.1", "pytest")
    assert verify_token
    confirm_email_verification(db_session, verify_token, "127.0.0.1", "pytest")
    db_session.commit()
    db_session.refresh(user)
    assert user.is_verified is True

    reset_token = request_password_reset(db_session, user.email, "127.0.0.1", "pytest")
    assert reset_token
    confirm_password_reset(db_session, reset_token, "NewStrongPass123", "127.0.0.1", "pytest")
    db_session.commit()
    db_session.refresh(user)
    assert user.password_hash != "x"


def test_rbac_admin_only(client: TestClient, db_session: Session) -> None:
    client.post("/auth/register", json={"email": "normal@example.com", "password": "StrongPass123"})
    login_response = client.post("/auth/login", json={"email": "normal@example.com", "password": "StrongPass123"})
    user_access_token = login_response.json()["tokens"]["access_token"]
    forbidden = client.get("/auth/admin-only", headers={"Authorization": f"Bearer {user_access_token}"})
    assert forbidden.status_code == 403

    admin = db_session.execute(select(User).where(User.email == "normal@example.com")).scalar_one()
    admin.role = UserRole.admin
    db_session.commit()
    admin_login = client.post("/auth/login", json={"email": "normal@example.com", "password": "StrongPass123"})
    admin_access_token = admin_login.json()["tokens"]["access_token"]
    granted = client.get("/auth/admin-only", headers={"Authorization": f"Bearer {admin_access_token}"})
    assert granted.status_code == 200


@pytest.mark.integration
def test_postgres_integration_smoke() -> None:
    db_url = os.getenv("AUTH_INTEGRATION_DB_URL")
    if not db_url:
        pytest.skip("Set AUTH_INTEGRATION_DB_URL to run Postgres integration tests.")

    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        result = connection.execute(text("select 1")).scalar_one()
        assert result == 1
