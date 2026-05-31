from __future__ import annotations

import os
import uuid
from uuid import UUID

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
from backend.models.auth import User, UserRole


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


def _auth(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_full_auth_workflow(client: TestClient, db_session: Session) -> None:
    email = f"workflow-{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPass123"
    new_password = "NewStrongPass456"

    # 1. Register
    register = client.post("/auth/register", json={"email": email, "password": password})
    assert register.status_code == 200, register.text
    user_id = register.json()["id"]
    assert register.json()["is_active"] is True
    assert register.json()["is_verified"] is False

    # 2. Duplicate register fails
    dup = client.post("/auth/register", json={"email": email, "password": password})
    assert dup.status_code == 409

    # 3. Login
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    tokens = login.json()["tokens"]
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]
    assert login.json()["user"]["last_login_at"] is not None

    # 4. Get profile
    me = client.get("/auth/me", headers=_auth(access))
    assert me.status_code == 200
    assert me.json()["email"] == email

    # 5. Update profile
    patch = client.patch("/auth/me", json={"display_name": "Workflow User"}, headers=_auth(access))
    assert patch.status_code == 200
    assert patch.json()["display_name"] == "Workflow User"

    # 6. Email verify request (always 200 — no enumeration)
    verify_req = client.post("/auth/verify-email/request", json={"email": email})
    assert verify_req.status_code == 200

    # 7. Password reset request (always 200 — no enumeration)
    reset_req = client.post("/auth/password-reset/request", json={"email": email})
    assert reset_req.status_code == 200

    # 8. Second login → two active sessions
    login2 = client.post("/auth/login", json={"email": email, "password": password})
    assert login2.status_code == 200
    refresh2 = login2.json()["tokens"]["refresh_token"]

    sessions = client.get("/auth/me/sessions", params={"refresh_token": refresh}, headers=_auth(access))
    assert sessions.status_code == 200
    assert sessions.json()["total"] == 2

    # 9. Activity feed has events
    activity = client.get("/auth/me/activity", headers=_auth(access))
    assert activity.status_code == 200
    assert activity.json()["total"] >= 1

    # 10. Refresh token rotation
    refreshed = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()["tokens"]
    assert new_tokens["refresh_token"] != refresh
    access = new_tokens["access_token"]

    # 11. RBAC — user cannot access admin-only
    forbidden = client.get("/auth/admin-only", headers=_auth(access))
    assert forbidden.status_code == 403

    # 12. Promote to admin and verify access
    user = db_session.execute(select(User).where(User.id == UUID(user_id))).scalar_one()
    user.role = UserRole.admin
    db_session.commit()
    admin_login = client.post("/auth/login", json={"email": email, "password": password})
    admin_access = admin_login.json()["tokens"]["access_token"]
    admin_ok = client.get("/auth/admin-only", headers=_auth(admin_access))
    assert admin_ok.status_code == 200

    # 13. Admin lists users
    users_list = client.get("/users", headers=_auth(admin_access))
    assert users_list.status_code == 200
    assert users_list.json()["total"] >= 1

    # 14. Change password (revokes all sessions)
    change_pw = client.post(
        "/auth/me/change-password",
        json={"current_password": password, "new_password": new_password},
        headers=_auth(admin_access),
    )
    assert change_pw.status_code == 200

    # Old refresh token no longer works
    stale_refresh = client.post("/auth/refresh", json={"refresh_token": refresh2})
    assert stale_refresh.status_code == 401

    # Login with new password
    relogin = client.post("/auth/login", json={"email": email, "password": new_password})
    assert relogin.status_code == 200
    final_tokens = relogin.json()["tokens"]

    # 15. Logout
    logout = client.post("/auth/logout", json={"refresh_token": final_tokens["refresh_token"]})
    assert logout.status_code == 200

    # Refresh after logout fails
    after_logout = client.post("/auth/refresh", json={"refresh_token": final_tokens["refresh_token"]})
    assert after_logout.status_code == 401

    # 16. Unauthenticated access blocked
    no_auth = client.get("/auth/me")
    assert no_auth.status_code == 401
