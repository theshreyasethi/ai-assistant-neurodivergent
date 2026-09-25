"""HTTP-layer test of routers/telemetry.py's session-ownership enforcement
(patent-readiness audit finding A02, roadmap task P1-07).

Mounts routers.telemetry on a throwaway app, one caller identity
overridden per test via auth.verify_user — the same pattern as
test_first_login_password.py, so the REAL require_active_user /
assert_session_access logic runs end to end, not a stand-in for it.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from routers import telemetry
from fakes import FakeFirestore

OWNER_UID = "student-owner"
OTHER_STUDENT_UID = "student-other"
TEACHER_UID = "teacher-1"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(telemetry.router, prefix="/api")
    return app


def _client_as(monkeypatch, fake_db, uid: str, email: str = "x@test.com") -> TestClient:
    app = _build_app()
    app.dependency_overrides[auth.verify_user] = lambda: {"uid": uid, "email": email}
    client = TestClient(app)
    client.fake_db = fake_db  # type: ignore[attr-defined]
    return client


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setattr(auth, "db", db)
    monkeypatch.setattr(telemetry, "db", db)
    auth._acct.clear()

    db.seed("users", OWNER_UID, {"role": "student", "status": "active", "mustChangePassword": False})
    db.seed("users", OTHER_STUDENT_UID, {"role": "student", "status": "active", "mustChangePassword": False})
    db.seed("users", TEACHER_UID, {"role": "teacher", "status": "active", "mustChangePassword": False})
    yield db
    auth._acct.clear()


def _seed_session(fake_db, session_id="sess1", owner=OWNER_UID):
    fake_db.seed("sessions", session_id, {"studentId": owner, "kind": "quiz", "summary": None})


def _question_event(session_id="sess1"):
    return {
        "type": "question", "sessionId": session_id, "studentId": "irrelevant-client-value", "ts": 1,
        "questionId": "q1", "correct": True, "timeMs": 4000,
    }


# ─────────────── POST /api/events ───────────────


def test_owner_can_write_events_to_their_own_session(fake_db, monkeypatch):
    _seed_session(fake_db)
    client = _client_as(monkeypatch, fake_db, OWNER_UID)
    resp = client.post("/api/events", json={"events": [_question_event()]})
    assert resp.status_code == 200
    assert resp.json()["written"] == 1
    assert resp.json()["skipped"] == []


def test_other_student_cannot_write_events_into_someone_elses_session(fake_db, monkeypatch):
    """The exact scenario finding A02 named: ingest_events wrote into
    whatever sessionId the client named, with no ownership check."""
    _seed_session(fake_db)
    client = _client_as(monkeypatch, fake_db, OTHER_STUDENT_UID)
    resp = client.post("/api/events", json={"events": [_question_event()]})
    assert resp.status_code == 200  # batch endpoint: per-event skip, not a hard failure
    assert resp.json()["written"] == 0
    assert resp.json()["skipped"][0]["reason"] == "not your session"
    # and nothing was actually persisted
    assert fake_db.all_docs("sessions").get("sess1", {}).get("studentId") == OWNER_UID


def test_events_for_a_nonexistent_session_are_skipped_not_written(fake_db, monkeypatch):
    client = _client_as(monkeypatch, fake_db, OWNER_UID)
    resp = client.post("/api/events", json={"events": [_question_event("ghost-session")]})
    assert resp.json()["written"] == 0
    assert resp.json()["skipped"][0]["reason"] == "not your session"


def test_mixed_batch_writes_only_the_owned_session_events(fake_db, monkeypatch):
    _seed_session(fake_db, "sess-mine", OWNER_UID)
    _seed_session(fake_db, "sess-theirs", OTHER_STUDENT_UID)
    client = _client_as(monkeypatch, fake_db, OWNER_UID)
    resp = client.post("/api/events", json={
        "events": [_question_event("sess-mine"), _question_event("sess-theirs")],
    })
    body = resp.json()
    assert body["written"] == 1
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["sessionId"] == "sess-theirs"


# ─────────────── PATCH /api/sessions/{id} (end_session) ───────────────


def _summary():
    return {"summary": {"totalQuestions": 5, "correct": 4, "totalTimeMs": 12000, "completed": True}}


def test_owner_can_end_their_own_session(fake_db, monkeypatch):
    _seed_session(fake_db)
    client = _client_as(monkeypatch, fake_db, OWNER_UID)
    resp = client.patch("/api/sessions/sess1", json=_summary())
    assert resp.status_code == 200
    assert fake_db.get_doc("sessions", "sess1")["summary"]["completed"] is True


def test_other_student_cannot_end_someone_elses_session(fake_db, monkeypatch):
    _seed_session(fake_db)
    client = _client_as(monkeypatch, fake_db, OTHER_STUDENT_UID)
    resp = client.patch("/api/sessions/sess1", json=_summary())
    assert resp.status_code == 403


def test_mapped_teacher_cannot_end_a_students_session(fake_db, monkeypatch):
    """Read access for a mapped teacher is legitimate (see GET test below);
    write access is not — ending a session is the student's own action."""
    fake_db.store["users"][OWNER_UID]["teacherId"] = TEACHER_UID
    _seed_session(fake_db)
    client = _client_as(monkeypatch, fake_db, TEACHER_UID)
    resp = client.patch("/api/sessions/sess1", json=_summary())
    assert resp.status_code == 403


def test_ending_a_nonexistent_session_returns_404(fake_db, monkeypatch):
    client = _client_as(monkeypatch, fake_db, OWNER_UID)
    resp = client.patch("/api/sessions/ghost-session", json=_summary())
    assert resp.status_code == 404


# ─────────────── GET /api/sessions/{id}/events ───────────────


def test_owner_can_read_their_own_session_events(fake_db, monkeypatch):
    _seed_session(fake_db)
    client = _client_as(monkeypatch, fake_db, OWNER_UID)
    resp = client.get("/api/sessions/sess1/events")
    assert resp.status_code == 200


def test_mapped_teacher_can_read_a_students_session_events(fake_db, monkeypatch):
    fake_db.store["users"][OWNER_UID]["teacherId"] = TEACHER_UID
    _seed_session(fake_db)
    client = _client_as(monkeypatch, fake_db, TEACHER_UID)
    resp = client.get("/api/sessions/sess1/events")
    assert resp.status_code == 200


def test_unrelated_student_cannot_read_someone_elses_session_events(fake_db, monkeypatch):
    """The other half of finding A02: get_events accepted any authenticated
    user and any id — a student could read another child's session telemetry."""
    _seed_session(fake_db)
    client = _client_as(monkeypatch, fake_db, OTHER_STUDENT_UID)
    resp = client.get("/api/sessions/sess1/events")
    assert resp.status_code == 404


def test_unmapped_teacher_cannot_read_a_students_session_events(fake_db, monkeypatch):
    _seed_session(fake_db)  # no teacherId set on OWNER_UID
    client = _client_as(monkeypatch, fake_db, TEACHER_UID)
    resp = client.get("/api/sessions/sess1/events")
    assert resp.status_code == 404
