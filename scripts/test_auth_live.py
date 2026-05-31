#!/usr/bin/env python3
"""Live end-to-end auth workflow against a running backend (default localhost:8000)."""
from __future__ import annotations

import json
import sys
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
EMAIL = f"live-{uuid.uuid4().hex[:8]}@example.com"
PASSWORD = "StrongPass123"
NEW_PASSWORD = "NewStrongPass456"

steps: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    steps.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        health = client.get("/health")
        record("Health check", health.status_code == 200, health.text[:80])

        reg = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
        record("Register", reg.status_code == 200, reg.text[:120] if reg.status_code != 200 else f"user={reg.json().get('id')}")

        dup = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
        record("Duplicate register blocked", dup.status_code == 409)

        login = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        record("Login", login.status_code == 200)
        if login.status_code != 200:
            return _summary()

        body = login.json()
        access = body["tokens"]["access_token"]
        refresh = body["tokens"]["refresh_token"]
        headers = {"Authorization": f"Bearer {access}"}

        me = client.get("/auth/me", headers=headers)
        record("GET /auth/me", me.status_code == 200 and me.json()["email"] == EMAIL)

        patch = client.patch("/auth/me", json={"display_name": "Live Test User"}, headers=headers)
        record("PATCH /auth/me", patch.status_code == 200 and patch.json()["display_name"] == "Live Test User")

        verify = client.post("/auth/verify-email/request", json={"email": EMAIL})
        record("Verify email request", verify.status_code == 200)

        reset = client.post("/auth/password-reset/request", json={"email": EMAIL})
        record("Password reset request", reset.status_code == 200)

        login2 = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        refresh2 = login2.json()["tokens"]["refresh_token"] if login2.status_code == 200 else ""
        record("Second login (extra session)", login2.status_code == 200)

        sessions = client.get("/auth/me/sessions", params={"refresh_token": refresh}, headers=headers)
        record(
            "List sessions",
            sessions.status_code == 200 and sessions.json()["total"] >= 2,
            f"total={sessions.json().get('total')}" if sessions.status_code == 200 else sessions.text[:80],
        )

        activity = client.get("/auth/me/activity", headers=headers)
        record("Activity feed", activity.status_code == 200 and activity.json()["total"] >= 1)

        refreshed = client.post("/auth/refresh", json={"refresh_token": refresh})
        record("Refresh tokens", refreshed.status_code == 200)
        if refreshed.status_code == 200:
            access = refreshed.json()["tokens"]["access_token"]
            refresh = refreshed.json()["tokens"]["refresh_token"]
            headers = {"Authorization": f"Bearer {access}"}

        admin_only = client.get("/auth/admin-only", headers=headers)
        record("Admin-only blocked for user", admin_only.status_code == 403)

        users_forbidden = client.get("/users", headers=headers)
        record("Admin /users blocked for user", users_forbidden.status_code == 403)

        change = client.post(
            "/auth/me/change-password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=headers,
        )
        record("Change password", change.status_code == 200)

        stale = client.post("/auth/refresh", json={"refresh_token": refresh2})
        record("Old refresh token invalid after password change", stale.status_code == 401)

        relogin = client.post("/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD})
        record("Login with new password", relogin.status_code == 200)
        if relogin.status_code == 200:
            final_refresh = relogin.json()["tokens"]["refresh_token"]
            logout = client.post("/auth/logout", json={"refresh_token": final_refresh})
            record("Logout", logout.status_code == 200)
            after = client.post("/auth/refresh", json={"refresh_token": final_refresh})
            record("Refresh blocked after logout", after.status_code == 401)

        no_auth = client.get("/auth/me")
        record("Unauthenticated /auth/me blocked", no_auth.status_code == 401)

    return _summary()


def _summary() -> int:
    passed = sum(1 for _, ok, _ in steps if ok)
    total = len(steps)
    print(f"\n{'=' * 50}")
    print(f"Live auth workflow: {passed}/{total} steps passed")
    print(f"Test user email: {EMAIL}")
    if passed < total:
        print("\nFailed steps:")
        for name, ok, detail in steps:
            if not ok:
                print(f"  - {name}: {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
