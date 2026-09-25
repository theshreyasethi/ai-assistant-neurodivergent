"""HTTP-layer test of GET /teacher/analytics/{student_id} in app.py —
patent-readiness audit finding A01 (Critical), roadmap task P1-06.

Before this fix, the route checked only role == "teacher" — ANY teacher
could read ANY student's analytics by guessing or enumerating uids. It
now depends on auth.require_teacher_of, which additionally requires the
caller be mapped to that specific student.

Imports the real, fully-wired app.py (not a throwaway app mounting one
router) specifically to prove the fix landed on the actual production
route object, not just on the shared auth.py helper in isolation
(test_student_access.py already covers the helper itself). app.py's
import cost is small (~1s, no network calls) and was already confirmed
safe in earlier verification for this same reason.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth  # noqa: E402
from fakes import FakeFirestore  # noqa: E402

OWNER_UID = "student-owner"
MAPPED_TEACHER_UID = "teacher-mapped"
UNMAPPED_TEACHER_UID = "teacher-unmapped"
ADMIN_UID = "admin-1"


@pytest.fixture
def fake_db(monkeypatch):
    import app as app_module  # imported inside the fixture so collection doesn't pay this cost for other files

    db = FakeFirestore()
    monkeypatch.setattr(auth, "db", db)
    monkeypatch.setattr(app_module, "db", db)
    auth._acct.clear()

    db.seed("users", OWNER_UID, {
        "role": "student", "status": "active", "mustChangePassword": False, "teacherId": MAPPED_TEACHER_UID,
    })
    db.seed("users", MAPPED_TEACHER_UID, {"role": "teacher", "status": "active", "mustChangePassword": False})
    db.seed("users", UNMAPPED_TEACHER_UID, {"role": "teacher", "status": "active", "mustChangePassword": False})
    db.seed("users", ADMIN_UID, {"role": "admin", "status": "active", "mustChangePassword": False})

    yield app_module, db
    auth._acct.clear()


def _client_as(app_module, uid: str) -> TestClient:
    app_module.app.dependency_overrides[auth.verify_user] = lambda: {"uid": uid, "email": "x@test.com"}
    return TestClient(app_module.app)


def test_unmapped_teacher_gets_404_not_the_students_analytics(fake_db):
    """The exact vulnerability A01 named: an unrelated teacher must not be
    able to read this student's analytics at all — not even a 403 that
    would confirm the uid exists, a 404."""
    app_module, _ = fake_db
    client = _client_as(app_module, UNMAPPED_TEACHER_UID)
    resp = client.get(f"/teacher/analytics/{OWNER_UID}")
    assert resp.status_code == 404


def test_mapped_teacher_can_read_the_students_analytics(fake_db):
    app_module, _ = fake_db
    client = _client_as(app_module, MAPPED_TEACHER_UID)
    resp = client.get(f"/teacher/analytics/{OWNER_UID}")
    assert resp.status_code == 200
    assert resp.json()["student_id"] == OWNER_UID


def test_admin_can_read_any_students_analytics(fake_db):
    app_module, _ = fake_db
    client = _client_as(app_module, ADMIN_UID)
    resp = client.get(f"/teacher/analytics/{OWNER_UID}")
    assert resp.status_code == 200


def test_the_student_themself_cannot_use_the_teacher_facing_route(fake_db):
    """require_teacher_of (unlike require_self_or_mapped_teacher) is
    teacher/admin-only by design — a student viewing their own analytics
    goes through a different, student-facing endpoint, not this one."""
    app_module, _ = fake_db
    client = _client_as(app_module, OWNER_UID)
    resp = client.get(f"/teacher/analytics/{OWNER_UID}")
    assert resp.status_code == 404
