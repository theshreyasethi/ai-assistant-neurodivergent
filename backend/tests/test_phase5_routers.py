"""HTTP-layer tests for Phase 5's new endpoints — teacher audit log,
current-override lookup, and the admin dossier endpoint (roadmap P5-06,
P5-08).
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from routers import admin, overrides
from fakes import FakeFirestore

STUDENT_UID = "student-1"
TEACHER_UID = "teacher-1"
OTHER_TEACHER_UID = "teacher-2"
ADMIN_UID = "admin-1"


def _client_as(app: FastAPI, uid: str) -> TestClient:
    app.dependency_overrides[auth.verify_user] = lambda: {"uid": uid, "email": "x@test.com"}
    return TestClient(app)


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setattr(auth, "db", db)
    monkeypatch.setattr(overrides, "db", db)
    auth._acct.clear()
    db.seed("users", STUDENT_UID, {
        "role": "student", "status": "active", "mustChangePassword": False, "teacherId": TEACHER_UID,
    })
    db.seed("users", TEACHER_UID, {"role": "teacher", "status": "active", "mustChangePassword": False})
    db.seed("users", OTHER_TEACHER_UID, {"role": "teacher", "status": "active", "mustChangePassword": False})
    db.seed("users", ADMIN_UID, {"role": "admin", "status": "active", "mustChangePassword": False})
    yield db
    auth._acct.clear()


def _overrides_app() -> FastAPI:
    app = FastAPI()
    app.include_router(overrides.router, prefix="/api")
    return app


def test_get_weight_override_reports_inactive_when_none_set(fake_db):
    client = _client_as(_overrides_app(), TEACHER_UID)
    resp = client.get(f"/api/teachers/students/{STUDENT_UID}/dase-weights")
    assert resp.status_code == 200
    assert resp.json()["active"] is False


def test_get_weight_override_reports_active_after_set(fake_db):
    client = _client_as(_overrides_app(), TEACHER_UID)
    client.put(f"/api/teachers/students/{STUDENT_UID}/dase-weights", json={
        "weights": {"ACC": 1.0}, "reason": "Testing GET after PUT",
    })
    resp = client.get(f"/api/teachers/students/{STUDENT_UID}/dase-weights")
    body = resp.json()
    assert body["active"] is True
    assert body["weights"] == {"ACC": 1.0}
    assert body["reason"] == "Testing GET after PUT"


def test_audit_log_scoped_to_the_calling_teachers_own_entries(fake_db):
    teacher_client = _client_as(_overrides_app(), TEACHER_UID)
    teacher_client.put(f"/api/teachers/students/{STUDENT_UID}/dase-weights", json={
        "weights": {"ACC": 1.0}, "reason": "Teacher 1's override",
    })

    # Seed an unrelated audit_log entry from a different actor directly —
    # the endpoint must not leak it to teacher-1.
    fake_db.seed("audit_log", "other-entry", {
        "actor": OTHER_TEACHER_UID, "action": "dase_weights.override", "target": "someone-else", "at": 1,
    })

    resp = teacher_client.get("/api/teachers/audit-log")
    body = resp.json()
    assert body["count"] == 1
    assert body["entries"][0]["actor"] == TEACHER_UID
    assert body["entries"][0]["details"]["reason"] == "Teacher 1's override"


def test_audit_log_requires_teacher_role(fake_db):
    client = _client_as(_overrides_app(), STUDENT_UID)
    resp = client.get("/api/teachers/audit-log")
    assert resp.status_code == 403


def test_audit_log_only_includes_dase_weight_actions(fake_db):
    fake_db.seed("audit_log", "unrelated", {
        "actor": TEACHER_UID, "action": "student.create", "target": "x", "at": 1,
    })
    client = _client_as(_overrides_app(), TEACHER_UID)
    resp = client.get("/api/teachers/audit-log")
    assert resp.json()["count"] == 0


# ─────────────────────── admin dossier endpoint ───────────────────────


def _admin_app() -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/api")
    return app


def test_dossier_requires_admin_role(fake_db):
    client = _client_as(_admin_app(), TEACHER_UID)
    resp = client.get("/api/admin/dossier")
    assert resp.status_code == 403


def test_dossier_returns_404_when_not_built(fake_db, monkeypatch, tmp_path):
    monkeypatch.setattr(admin, "_DOSSIER_PATH", tmp_path / "does_not_exist.json")
    client = _client_as(_admin_app(), ADMIN_UID)
    resp = client.get("/api/admin/dossier")
    assert resp.status_code == 404


def test_dossier_serves_the_built_file(fake_db, monkeypatch, tmp_path):
    dossier_path = tmp_path / "patent_dossier.json"
    dossier_path.write_text(json.dumps({"allResolved": True, "claims": []}), encoding="utf-8")
    monkeypatch.setattr(admin, "_DOSSIER_PATH", dossier_path)

    client = _client_as(_admin_app(), ADMIN_UID)
    resp = client.get("/api/admin/dossier")
    assert resp.status_code == 200
    assert resp.json()["allResolved"] is True
