"""HTTP-layer test of routers/evaluation.py's ownership enforcement
(patent-readiness audit finding A02, roadmap task P1-07).

Same pattern as test_telemetry_ownership.py: mounts routers.evaluation on
a throwaway app, overrides only auth.verify_user, so the real
require_active_user / assert_session_access / require_self_or_mapped_teacher
logic runs end to end.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from routers import evaluation
from fakes import FakeFirestore

OWNER_UID = "student-owner"
OTHER_STUDENT_UID = "student-other"
TEACHER_UID = "teacher-1"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(evaluation.router, prefix="/api")
    return app


def _client_as(fake_db, uid: str) -> TestClient:
    app = _build_app()
    app.dependency_overrides[auth.verify_user] = lambda: {"uid": uid, "email": "x@test.com"}
    client = TestClient(app)
    client.fake_db = fake_db  # type: ignore[attr-defined]
    return client


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setattr(auth, "db", db)
    monkeypatch.setattr(evaluation, "db", db)
    auth._acct.clear()

    db.seed("users", OWNER_UID, {"role": "student", "status": "active", "mustChangePassword": False})
    db.seed("users", OTHER_STUDENT_UID, {"role": "student", "status": "active", "mustChangePassword": False})
    db.seed("users", TEACHER_UID, {"role": "teacher", "status": "active", "mustChangePassword": False})
    yield db
    auth._acct.clear()


def _seed_session_with_events(fake_db, session_id="sess1", owner=OWNER_UID):
    fake_db.seed("sessions", session_id, {"studentId": owner})
    fake_db.seed(f"sessions/{session_id}/events", "e1", {
        "type": "question", "correct": True, "timeMs": 4000, "difficulty": 3,
        "questionId": "q1", "serverTs": 1,
    })


# ─────────────── POST /api/evaluate ───────────────


def test_owner_can_evaluate_their_own_session(fake_db):
    _seed_session_with_events(fake_db)
    client = _client_as(fake_db, OWNER_UID)
    resp = client.post("/api/evaluate", json={
        "sessionId": "sess1", "studentId": OWNER_UID, "profile": "default", "persist": False,
    })
    assert resp.status_code == 200
    assert resp.json()["studentId"] == OWNER_UID


def test_other_student_cannot_evaluate_someone_elses_session(fake_db):
    """The scenario finding A02 named for /evaluate specifically: a student
    naming a session that isn't theirs could have its events read and
    scored, attributed as if it were their own evaluation."""
    _seed_session_with_events(fake_db)
    client = _client_as(fake_db, OTHER_STUDENT_UID)
    resp = client.post("/api/evaluate", json={
        "sessionId": "sess1", "studentId": OTHER_STUDENT_UID, "profile": "default", "persist": False,
    })
    assert resp.status_code == 403


def test_mapped_teacher_cannot_trigger_evaluation_of_a_students_session(fake_db):
    """Evaluation is attributed to the CALLING uid — a teacher-triggered
    evaluate would be persisted under the teacher's own id, which is
    meaningless. Only the session's owner may call this endpoint."""
    fake_db.store["users"][OWNER_UID]["teacherId"] = TEACHER_UID
    _seed_session_with_events(fake_db)
    client = _client_as(fake_db, TEACHER_UID)
    resp = client.post("/api/evaluate", json={
        "sessionId": "sess1", "studentId": OWNER_UID, "profile": "default", "persist": False,
    })
    assert resp.status_code == 403


def test_evaluating_a_nonexistent_session_returns_404(fake_db):
    client = _client_as(fake_db, OWNER_UID)
    resp = client.post("/api/evaluate", json={
        "sessionId": "ghost-session", "studentId": OWNER_UID, "profile": "default", "persist": False,
    })
    assert resp.status_code == 404


# ─────────────── GET /api/evaluation/{student_id} ───────────────


def test_student_can_read_their_own_evaluation_history(fake_db):
    client = _client_as(fake_db, OWNER_UID)
    resp = client.get(f"/api/evaluation/{OWNER_UID}")
    assert resp.status_code == 200


def test_mapped_teacher_can_read_a_students_evaluation_history(fake_db):
    fake_db.store["users"][OWNER_UID]["teacherId"] = TEACHER_UID
    client = _client_as(fake_db, TEACHER_UID)
    resp = client.get(f"/api/evaluation/{OWNER_UID}")
    assert resp.status_code == 200


def test_unrelated_student_cannot_read_someone_elses_evaluation_history(fake_db):
    client = _client_as(fake_db, OTHER_STUDENT_UID)
    resp = client.get(f"/api/evaluation/{OWNER_UID}")
    assert resp.status_code == 404


def test_unmapped_teacher_cannot_read_a_students_evaluation_history(fake_db):
    client = _client_as(fake_db, TEACHER_UID)
    resp = client.get(f"/api/evaluation/{OWNER_UID}")
    assert resp.status_code == 404


def test_unrelated_student_cannot_read_someone_elses_error_breakdown(fake_db):
    client = _client_as(fake_db, OTHER_STUDENT_UID)
    resp = client.get(f"/api/evaluation/{OWNER_UID}/errors")
    assert resp.status_code == 404
