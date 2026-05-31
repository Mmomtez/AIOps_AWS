from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("INSTANCE_ID", "i-local")
os.environ.setdefault("S3_BUCKET_NAME", "local-bucket")
os.environ.setdefault("LOG_GROUP_NAME", "local-log-group")

from backend.api.auth import router as auth_router
from backend.api.user_profile import router as user_profile_router
from backend.api.users import router as users_router
from backend.db.base import Base
from backend.db.session import get_db
from backend.models.auth import RefreshToken, User, UserRole


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
    app.include_router(user_profile_router)
    app.include_router(users_router)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def _register_and_login(client: TestClient, email: str, password: str = "StrongPass123") -> dict:
    client.post("/auth/register", json={"email": email, "password": password})
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["tokens"]


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_update_profile(client: TestClient) -> None:
    tokens = _register_and_login(client, "profile@example.com")
    response = client.patch(
        "/auth/me",
        json={"display_name": "Profile User"},
        headers=_auth_headers(tokens["access_token"]),
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Profile User"


def test_change_password_revokes_sessions(client: TestClient, db_session: Session) -> None:
    tokens = _register_and_login(client, "pass@example.com")
    second_login = client.post("/auth/login", json={"email": "pass@example.com", "password": "StrongPass123"})
    assert second_login.status_code == 200

    change_response = client.post(
        "/auth/me/change-password",
        json={"current_password": "StrongPass123", "new_password": "NewStrongPass456"},
        headers=_auth_headers(tokens["access_token"]),
    )
    assert change_response.status_code == 200

    user = db_session.execute(select(User).where(User.email == "pass@example.com")).scalar_one()
    assert user.password_changed_at is not None

    active_tokens = db_session.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
    ).scalars().all()
    assert active_tokens == []

    old_login = client.post("/auth/login", json={"email": "pass@example.com", "password": "StrongPass123"})
    assert old_login.status_code == 401
    new_login = client.post("/auth/login", json={"email": "pass@example.com", "password": "NewStrongPass456"})
    assert new_login.status_code == 200


def test_deactivate_account(client: TestClient, db_session: Session) -> None:
    tokens = _register_and_login(client, "deact@example.com")
    response = client.post("/auth/me/deactivate", headers=_auth_headers(tokens["access_token"]))
    assert response.status_code == 200

    user = db_session.execute(select(User).where(User.email == "deact@example.com")).scalar_one()
    assert user.is_active is False
    assert user.deactivated_at is not None

    login_response = client.post("/auth/login", json={"email": "deact@example.com", "password": "StrongPass123"})
    assert login_response.status_code == 403


def test_session_management(client: TestClient) -> None:
    tokens = _register_and_login(client, "sess@example.com")
    client.post("/auth/login", json={"email": "sess@example.com", "password": "StrongPass123"})

    sessions_response = client.get(
        "/auth/me/sessions",
        params={"refresh_token": tokens["refresh_token"]},
        headers=_auth_headers(tokens["access_token"]),
    )
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()["items"]
    assert len(sessions) == 2
    assert sum(1 for session in sessions if session["is_current"]) == 1

    revoke_one = client.delete(
        f"/auth/me/sessions/{sessions[0]['id']}",
        headers=_auth_headers(tokens["access_token"]),
    )
    assert revoke_one.status_code == 200

    revoke_all = client.post(
        "/auth/me/sessions/revoke-all",
        json={"keep_refresh_token": tokens["refresh_token"]},
        headers=_auth_headers(tokens["access_token"]),
    )
    assert revoke_all.status_code == 200


def test_activity_feed(client: TestClient) -> None:
    tokens = _register_and_login(client, "activity@example.com")
    client.patch(
        "/auth/me",
        json={"display_name": "Active User"},
        headers=_auth_headers(tokens["access_token"]),
    )
    response = client.get("/auth/me/activity", headers=_auth_headers(tokens["access_token"]))
    assert response.status_code == 200
    assert response.json()["total"] >= 1


def test_admin_user_management(client: TestClient, db_session: Session) -> None:
    user_tokens = _register_and_login(client, "member@example.com")
    _register_and_login(client, "admin@example.com")

    forbidden = client.get("/users", headers=_auth_headers(user_tokens["access_token"]))
    assert forbidden.status_code == 403

    admin = db_session.execute(select(User).where(User.email == "admin@example.com")).scalar_one()
    admin.role = UserRole.admin
    db_session.commit()
    admin_login = client.post("/auth/login", json={"email": "admin@example.com", "password": "StrongPass123"})
    admin_access = admin_login.json()["tokens"]["access_token"]

    list_response = client.get("/users", headers=_auth_headers(admin_access))
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 2

    member = db_session.execute(select(User).where(User.email == "member@example.com")).scalar_one()
    patch_response = client.patch(
        f"/users/{member.id}",
        json={"display_name": "Managed User", "is_verified": True},
        headers=_auth_headers(admin_access),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["display_name"] == "Managed User"
    assert patch_response.json()["is_verified"] is True

    unlock_response = client.post(f"/users/{member.id}/unlock", headers=_auth_headers(admin_access))
    assert unlock_response.status_code == 200

    revoke_response = client.post(f"/users/{member.id}/revoke-sessions", headers=_auth_headers(admin_access))
    assert revoke_response.status_code == 200


def test_admin_cannot_deactivate_last_admin(client: TestClient, db_session: Session) -> None:
    _register_and_login(client, "solo-admin@example.com")
    admin = db_session.execute(select(User).where(User.email == "solo-admin@example.com")).scalar_one()
    admin.role = UserRole.admin
    db_session.commit()

    admin_login = client.post("/auth/login", json={"email": "solo-admin@example.com", "password": "StrongPass123"})
    admin_access = admin_login.json()["tokens"]["access_token"]

    self_deactivate = client.delete(f"/users/{admin.id}", headers=_auth_headers(admin_access))
    assert self_deactivate.status_code == 400

    demote = client.patch(
        f"/users/{admin.id}",
        json={"role": "user"},
        headers=_auth_headers(admin_access),
    )
    assert demote.status_code == 400
