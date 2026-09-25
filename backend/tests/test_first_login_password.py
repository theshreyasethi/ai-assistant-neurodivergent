"""HTTP-layer test of POST /api/auth/first-login-password and the
require_active_user gate it exists to satisfy (patent-readiness roadmap
task P1-05).

Mounts routers.auth_flow PLUS one trivial protected dummy route on a
throwaway app - not the full app.py, which pulls in unrelated LLM/RAG
setup this test doesn't need. Overrides ONLY auth.verify_user (the token
decode step - no real Firebase ID token exists in a test), so the REAL
require_active_user / verify_role logic actually runs against the fake
Firestore, proving the gate end to end rather than asserting it exists.
"""

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

import auth
from routers import auth_flow
from fakes import FakeAuth, FakeFirestore

CALLER_UID = "student-1"
CALLER_EMAIL = "s1@test.com"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_flow.router, prefix="/api")

    # A stand-in for "any standard endpoint" - exercises the exact same
    # require_active_user dependency every real route in app.py and the
    # other routers now uses.
    @app.get("/api/dummy/protected")
    async def dummy_protected(user: dict = Depends(auth.require_active_user)):
        return {"ok": True, "role": user.get("role")}

    return app


@pytest.fixture
def env(monkeypatch):
    fake_db = FakeFirestore()
    fake_auth = FakeAuth()
    monkeypatch.setattr(auth, "db", fake_db)
    monkeypatch.setattr(auth_flow, "firebase_auth", fake_auth)
    monkeypatch.setattr(auth_flow, "db", fake_db)
    auth._acct.clear()

    app = _build_app()
    app.dependency_overrides[auth.verify_user] = lambda: {"uid": CALLER_UID, "email": CALLER_EMAIL}

    with TestClient(app) as client:
        client.fake_db = fake_db  # type: ignore[attr-defined]
        client.fake_auth = fake_auth  # type: ignore[attr-defined]
        yield client
    auth._acct.clear()


def _seed_pending(client, uid=CALLER_UID, **extra):
    client.fake_db.seed("users", uid, {
        "role": "student", "status": "pending_first_login", "mustChangePassword": True, **extra,
    })


# ─────────────── the gate itself ───────────────


def test_standard_endpoint_blocked_while_must_change_password(env):
    _seed_pending(env)
    resp = env.get("/api/dummy/protected")
    assert resp.status_code == 403
    assert resp.json()["detail"] == {"code": "PASSWORD_CHANGE_REQUIRED"}


def test_standard_endpoint_works_for_an_active_account(env):
    env.fake_db.seed("users", CALLER_UID, {"role": "student", "status": "active", "mustChangePassword": False})
    resp = env.get("/api/dummy/protected")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "role": "student"}


def test_first_login_route_itself_is_reachable_while_pending(env):
    _seed_pending(env)
    resp = env.post("/api/auth/first-login-password", json={"newPassword": "a-genuinely-strong-pw"})
    assert resp.status_code == 200


# ─────────────── successful change ───────────────


def test_successful_change_clears_flag_updates_status_and_restores_access(env):
    _seed_pending(env)

    resp = env.post("/api/auth/first-login-password", json={"newPassword": "a-genuinely-strong-pw"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "next": "sign_in_again"}

    stored = env.fake_db.get_doc("users", CALLER_UID)
    assert stored["mustChangePassword"] is False
    assert stored["status"] == "active"
    assert "passwordChangedAt" in stored

    # The account gate must see the update on the very next request - not
    # after the 15s cache TTL - because invalidate_account_cache() was called.
    resp2 = env.get("/api/dummy/protected")
    assert resp2.status_code == 200
    assert resp2.json()["role"] == "student"


def test_successful_change_updates_the_password_via_admin_sdk(env):
    _seed_pending(env)
    env.post("/api/auth/first-login-password", json={"newPassword": "a-genuinely-strong-pw"})
    assert env.fake_auth.updated_passwords[CALLER_UID] == "a-genuinely-strong-pw"


def test_successful_change_revokes_existing_refresh_tokens(env):
    _seed_pending(env)
    env.post("/api/auth/first-login-password", json={"newPassword": "a-genuinely-strong-pw"})
    assert CALLER_UID in env.fake_auth.revoked


def test_revoke_failure_does_not_prevent_the_password_change(env, monkeypatch):
    """revoke_refresh_tokens is best-effort - a transient Admin SDK error
    there must not roll back or fail an already-completed password change."""
    _seed_pending(env)

    def _boom(_uid):
        raise RuntimeError("Admin SDK hiccup")

    monkeypatch.setattr(env.fake_auth, "revoke_refresh_tokens", _boom)
    resp = env.post("/api/auth/first-login-password", json={"newPassword": "a-genuinely-strong-pw"})
    assert resp.status_code == 200
    assert env.fake_db.get_doc("users", CALLER_UID)["mustChangePassword"] is False


# ─────────────── validation ───────────────


@pytest.mark.parametrize("bad_password", ["short1", "a" * 9, "123456789"])
def test_password_shorter_than_minimum_is_rejected(env, bad_password):
    _seed_pending(env)
    resp = env.post("/api/auth/first-login-password", json={"newPassword": bad_password})
    assert resp.status_code == 422
    # A rejected password must never reach Firebase Auth or Firestore.
    assert CALLER_UID not in env.fake_auth.updated_passwords
    assert env.fake_db.get_doc("users", CALLER_UID)["mustChangePassword"] is True


def test_password_longer_than_maximum_is_rejected(env):
    _seed_pending(env)
    resp = env.post("/api/auth/first-login-password", json={"newPassword": "a" * 129})
    assert resp.status_code == 422


@pytest.mark.parametrize("common_password", [
    "password123", "PASSWORD123", "1234567890", "qwertyuiop", "welcome123",
])
def test_common_or_obvious_passwords_are_rejected(env, common_password):
    _seed_pending(env)
    resp = env.post("/api/auth/first-login-password", json={"newPassword": common_password})
    assert resp.status_code == 422
    assert CALLER_UID not in env.fake_auth.updated_passwords


def test_low_variety_password_is_rejected(env):
    _seed_pending(env)
    resp = env.post("/api/auth/first-login-password", json={"newPassword": "aaaaaaaaaaaa"})
    assert resp.status_code == 422


def test_exactly_minimum_length_valid_password_is_accepted(env):
    _seed_pending(env)
    resp = env.post("/api/auth/first-login-password", json={"newPassword": "Xk7#mQ2!p9"})  # 10 chars
    assert len("Xk7#mQ2!p9") == 10
    assert resp.status_code == 200


def test_missing_body_field_returns_422(env):
    _seed_pending(env)
    resp = env.post("/api/auth/first-login-password", json={})
    assert resp.status_code == 422
