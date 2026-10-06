"""Account lifecycle: disable/enable, admin password reset, student
reassignment (patent-readiness roadmap task P1-09).

Two layers, same pattern as the rest of this suite: unit tests of
services.accounts' functions directly, then HTTP-layer tests of
routers/admin.py's routes via a throwaway app with only auth.verify_user
overridden, so the real require_admin / require_active_user chain runs.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from routers import admin as admin_router
from services import accounts
from fakes import FakeAuth, FakeFirestore

ADMIN_UID = "admin-1"
TEACHER_A = "teacher-a"
TEACHER_B = "teacher-b"
STUDENT_UID = "student-1"


# ─────────────── services.accounts unit tests ───────────────


@pytest.fixture
def fake_backend(monkeypatch):
    fake_db = FakeFirestore()
    fake_auth = FakeAuth()
    monkeypatch.setattr(accounts, "db", fake_db)
    monkeypatch.setattr(accounts, "firebase_auth", fake_auth)
    return fake_db, fake_auth


def _seed_student(fake_db, uid=STUDENT_UID, teacher=TEACHER_A, **extra):
    fake_db.seed("users", uid, {
        "role": "student", "status": "active", "email": f"{uid}@school.org",
        "teacherId": teacher, "teacher_id": teacher, **extra,
    })


def _seed_teacher(fake_db, uid, **extra):
    fake_db.seed("users", uid, {"role": "teacher", "status": "active", **extra})


def test_set_account_status_disables_and_revokes_sessions(fake_backend):
    fake_db, fake_auth = fake_backend
    _seed_student(fake_db)
    result = accounts.set_account_status(STUDENT_UID, "disabled", actor=ADMIN_UID)
    assert result["status"] == "disabled"
    assert fake_db.get_doc("users", STUDENT_UID)["status"] == "disabled"
    assert STUDENT_UID in fake_auth.revoked


def test_set_account_status_re_enables(fake_backend):
    fake_db, _ = fake_backend
    _seed_student(fake_db, status="disabled")
    accounts.set_account_status(STUDENT_UID, "active", actor=ADMIN_UID)
    assert fake_db.get_doc("users", STUDENT_UID)["status"] == "active"


def test_set_account_status_writes_audit_log(fake_backend):
    fake_db, _ = fake_backend
    _seed_student(fake_db)
    accounts.set_account_status(STUDENT_UID, "disabled", actor=ADMIN_UID)
    entries = list(fake_db.all_docs("audit_log").values())
    assert len(entries) == 1
    assert entries[0]["action"] == "account.disabled"
    assert entries[0]["actor"] == ADMIN_UID


def test_set_account_status_unknown_account_raises_not_found(fake_backend):
    with pytest.raises(accounts.AccountNotFound):
        accounts.set_account_status("ghost", "disabled", actor=ADMIN_UID)


def test_admin_reset_password_issues_a_fresh_temp_password(fake_backend):
    fake_db, fake_auth = fake_backend
    _seed_student(fake_db, mustChangePassword=False, status="active")
    result = accounts.admin_reset_password(STUDENT_UID, actor=ADMIN_UID)
    assert len(result["temporaryPassword"]) == 14
    assert fake_auth.updated_passwords[STUDENT_UID] == result["temporaryPassword"]
    stored = fake_db.get_doc("users", STUDENT_UID)
    assert stored["mustChangePassword"] is True
    assert stored["status"] == "pending_first_login"
    assert STUDENT_UID in fake_auth.revoked


def test_admin_reset_password_on_unknown_account_raises_not_found(fake_backend):
    with pytest.raises(accounts.AccountNotFound):
        accounts.admin_reset_password("ghost", actor=ADMIN_UID)


def test_reassign_teacher_updates_student_and_enrollments(fake_backend):
    fake_db, _ = fake_backend
    _seed_student(fake_db, teacher=TEACHER_A)
    _seed_teacher(fake_db, TEACHER_A)
    _seed_teacher(fake_db, TEACHER_B)
    fake_db.seed("enrollments", f"{TEACHER_A}_{STUDENT_UID}", {
        "teacherId": TEACHER_A, "studentId": STUDENT_UID, "active": True,
    })

    result = accounts.reassign_teacher(STUDENT_UID, TEACHER_B, actor=ADMIN_UID)
    assert result["teacherId"] == TEACHER_B
    assert result["previousTeacherId"] == TEACHER_A

    stored = fake_db.get_doc("users", STUDENT_UID)
    assert stored["teacherId"] == TEACHER_B and stored["teacher_id"] == TEACHER_B

    old_enrollment = fake_db.get_doc("enrollments", f"{TEACHER_A}_{STUDENT_UID}")
    assert old_enrollment["active"] is False

    new_enrollment = fake_db.get_doc("enrollments", f"{TEACHER_B}_{STUDENT_UID}")
    assert new_enrollment["active"] is True


def test_reassign_teacher_rejects_an_invalid_new_teacher(fake_backend):
    fake_db, _ = fake_backend
    _seed_student(fake_db)
    with pytest.raises(accounts.TeacherInvalid):
        accounts.reassign_teacher(STUDENT_UID, "not-a-teacher", actor=ADMIN_UID)


def test_reassign_teacher_rejects_a_disabled_new_teacher(fake_backend):
    fake_db, _ = fake_backend
    _seed_student(fake_db)
    _seed_teacher(fake_db, TEACHER_B, status="disabled")
    with pytest.raises(accounts.TeacherInvalid):
        accounts.reassign_teacher(STUDENT_UID, TEACHER_B, actor=ADMIN_UID)


def test_reassign_teacher_rejects_a_non_student_target(fake_backend):
    fake_db, _ = fake_backend
    _seed_teacher(fake_db, STUDENT_UID)  # same uid, role=teacher
    _seed_teacher(fake_db, TEACHER_B)
    with pytest.raises(accounts.AccountError):
        accounts.reassign_teacher(STUDENT_UID, TEACHER_B, actor=ADMIN_UID)


# ─────────────── HTTP layer ───────────────


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(admin_router.router, prefix="/api")
    return app


@pytest.fixture
def client(monkeypatch):
    fake_db = FakeFirestore()
    fake_auth = FakeAuth()
    monkeypatch.setattr(accounts, "db", fake_db)
    monkeypatch.setattr(accounts, "firebase_auth", fake_auth)

    app = _build_app()
    app.dependency_overrides[admin_router.require_admin] = lambda: {"uid": ADMIN_UID, "role": "admin"}

    with TestClient(app) as test_client:
        test_client.fake_db = fake_db  # type: ignore[attr-defined]
        test_client.fake_auth = fake_auth  # type: ignore[attr-defined]
        yield test_client


def test_disable_route(client):
    _seed_student(client.fake_db)
    resp = client.post(f"/api/admin/users/{STUDENT_UID}/disable")
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"


def test_disable_unknown_user_returns_404(client):
    resp = client.post("/api/admin/users/ghost/disable")
    assert resp.status_code == 404


def test_enable_route(client):
    _seed_student(client.fake_db, status="disabled")
    resp = client.post(f"/api/admin/users/{STUDENT_UID}/enable")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_reset_password_route_returns_temp_password_once(client):
    _seed_student(client.fake_db, mustChangePassword=False, status="active")
    resp = client.post(f"/api/admin/users/{STUDENT_UID}/reset-password")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["temporaryPassword"]) == 14
    assert client.fake_db.get_doc("users", STUDENT_UID)["mustChangePassword"] is True


def test_reassign_teacher_route(client):
    _seed_student(client.fake_db, teacher=TEACHER_A)
    _seed_teacher(client.fake_db, TEACHER_A)
    _seed_teacher(client.fake_db, TEACHER_B)
    resp = client.patch(f"/api/admin/students/{STUDENT_UID}/teacher", json={"teacherId": TEACHER_B})
    assert resp.status_code == 200
    assert resp.json()["teacherId"] == TEACHER_B


def test_reassign_teacher_route_rejects_invalid_teacher_with_422(client):
    _seed_student(client.fake_db, teacher=TEACHER_A)
    _seed_teacher(client.fake_db, TEACHER_A)
    resp = client.patch(f"/api/admin/students/{STUDENT_UID}/teacher", json={"teacherId": "ghost"})
    assert resp.status_code == 422


def test_lifecycle_routes_require_admin():
    """Without the require_admin override, the real dependency chain
    (verify_user -> require_active_user -> verify_role) rejects an
    unauthenticated call with 401 before ever reaching account logic."""
    app = _build_app()
    with TestClient(app) as unauthed:
        resp = unauthed.post(f"/api/admin/users/{STUDENT_UID}/disable")
    assert resp.status_code == 401
