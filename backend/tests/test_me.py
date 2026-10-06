"""HTTP-layer test of GET/PATCH /api/me (patent-readiness roadmap task
P1-08 — self-service account updates).

Mounts routers.me on a throwaway app with only auth.verify_user
overridden, same pattern as the other router test files, so the real
require_active_user gate and the real update logic both run end to end.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from routers import me as me_router
from fakes import FakeAuth, FakeFirestore

UID = "user-1"
SCHOOL_DOMAIN = "students.eduease.local"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(me_router.router, prefix="/api")
    return app


@pytest.fixture
def env(monkeypatch):
    fake_db = FakeFirestore()
    fake_auth = FakeAuth()
    monkeypatch.setattr(auth, "db", fake_db)
    monkeypatch.setattr(me_router, "db", fake_db)
    monkeypatch.setattr(me_router, "firebase_auth", fake_auth)
    auth._acct.clear()

    app = _build_app()
    app.dependency_overrides[auth.verify_user] = lambda: {"uid": UID, "email": f"kid1@{SCHOOL_DOMAIN}"}

    with TestClient(app) as client:
        client.fake_db = fake_db  # type: ignore[attr-defined]
        client.fake_auth = fake_auth  # type: ignore[attr-defined]
        yield client
    auth._acct.clear()


def _seed(env, **extra):
    env.fake_db.seed("users", UID, {
        "role": "student", "status": "active", "mustChangePassword": False,
        "email": f"kid1@{SCHOOL_DOMAIN}", "username": "kid1", "displayName": "Kid One",
        **extra,
    })


# ─────────────── GET /api/me ───────────────


def test_get_me_returns_own_profile(env):
    _seed(env, gradeLevel="4", teacherId="t1")
    resp = env.get("/api/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["uid"] == UID
    assert body["username"] == "kid1"
    assert body["displayName"] == "Kid One"
    assert body["role"] == "student"
    assert body["gradeLevel"] == "4"


def test_get_me_blocked_while_must_change_password(env):
    _seed(env, mustChangePassword=True, status="pending_first_login")
    resp = env.get("/api/me")
    assert resp.status_code == 403
    assert resp.json()["detail"] == {"code": "PASSWORD_CHANGE_REQUIRED"}


# ─────────────── PATCH /api/me ───────────────


def test_update_display_name_only(env):
    _seed(env)
    resp = env.patch("/api/me", json={"displayName": "New Name"})
    assert resp.status_code == 200
    assert env.fake_db.get_doc("users", UID)["displayName"] == "New Name"
    assert env.fake_auth.updated_passwords == {}  # password untouched


def test_empty_patch_body_is_rejected(env):
    _seed(env)
    resp = env.patch("/api/me", json={})
    assert resp.status_code == 422


def test_blank_display_name_is_rejected(env):
    _seed(env)
    resp = env.patch("/api/me", json={"displayName": ""})
    assert resp.status_code == 422


def test_invalid_username_shape_is_rejected(env):
    _seed(env)
    resp = env.patch("/api/me", json={"username": "no spaces!"})
    assert resp.status_code == 422


def test_username_change_rolls_forward_the_synthetic_login_email(env):
    _seed(env)
    resp = env.patch("/api/me", json={"username": "kiddo2"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "kiddo2"
    assert body["email"] == f"kiddo2@{SCHOOL_DOMAIN}"
    stored = env.fake_db.get_doc("users", UID)
    assert stored["username"] == "kiddo2"
    assert stored["email"] == f"kiddo2@{SCHOOL_DOMAIN}"


def test_username_change_does_not_touch_a_real_external_email(env):
    """A teacher/admin created with a real email keeps it — only the
    synthetic username@SCHOOL_LOGIN_DOMAIN form is ever rolled forward."""
    _seed(env, role="teacher", email="ms.lee@school.org", username="mslee")
    resp = env.patch("/api/me", json={"username": "new-handle"})
    assert resp.status_code == 200
    body = resp.json()
    assert "email" not in body  # untouched, so not reported as updated
    assert env.fake_db.get_doc("users", UID)["email"] == "ms.lee@school.org"


def test_username_collision_returns_409(env, monkeypatch):
    _seed(env)

    def _boom(_uid, **kwargs):
        if "email" in kwargs:
            raise env.fake_auth.EmailAlreadyExistsError(kwargs["email"])

    monkeypatch.setattr(env.fake_auth, "update_user", _boom)
    resp = env.patch("/api/me", json={"username": "taken"})
    assert resp.status_code == 409


def test_can_update_both_fields_at_once(env):
    _seed(env)
    resp = env.patch("/api/me", json={"displayName": "Kid Prime", "username": "kidprime"})
    assert resp.status_code == 200
    stored = env.fake_db.get_doc("users", UID)
    assert stored["displayName"] == "Kid Prime"
    assert stored["username"] == "kidprime"


def test_update_cache_is_invalidated_so_next_request_sees_fresh_data(env):
    _seed(env)
    env.get("/api/me")  # warms the _acct cache
    env.patch("/api/me", json={"displayName": "Changed"})
    resp = env.get("/api/me")
    assert resp.json()["displayName"] == "Changed"
