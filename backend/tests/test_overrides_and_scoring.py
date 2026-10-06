"""HTTP-layer tests for roadmap P3-08: server-derived scoring profile and
teacher DASE weight overrides.

Same pattern as test_evaluation_ownership.py — mounts the real routers on a
throwaway app, overrides only auth.verify_user, so require_active_user /
require_teacher_of / the actual override-application logic in
routers/evaluation.py all run end to end rather than being mocked away.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from routers import evaluation, overrides
from fakes import FakeFirestore

STUDENT_UID = "student-1"
TEACHER_UID = "teacher-1"
OTHER_TEACHER_UID = "teacher-2"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(evaluation.router, prefix="/api")
    app.include_router(overrides.router, prefix="/api")
    return app


def _client_as(uid: str) -> TestClient:
    app = _build_app()
    app.dependency_overrides[auth.verify_user] = lambda: {"uid": uid, "email": "x@test.com"}
    return TestClient(app)


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setattr(auth, "db", db)
    monkeypatch.setattr(evaluation, "db", db)
    monkeypatch.setattr(overrides, "db", db)
    auth._acct.clear()

    db.seed("users", STUDENT_UID, {
        "role": "student", "status": "active", "mustChangePassword": False,
        "teacherId": TEACHER_UID,
        "profile": {"primary": "adhd", "disabilities": ["adhd"]},
    })
    db.seed("users", TEACHER_UID, {"role": "teacher", "status": "active", "mustChangePassword": False})
    db.seed("users", OTHER_TEACHER_UID, {"role": "teacher", "status": "active", "mustChangePassword": False})
    yield db
    auth._acct.clear()


def _seed_session_with_events(fake_db, session_id="sess1"):
    fake_db.seed("sessions", session_id, {"studentId": STUDENT_UID})
    for i in range(6):
        fake_db.seed(f"sessions/{session_id}/events", f"e{i}", {
            "type": "question", "correct": True, "timeMs": 4000, "difficulty": 3,
            "questionId": f"q{i}", "serverTs": i,
        })


# ─────────────── server-derived profile (ignores body.profile) ───────────────


def test_evaluate_derives_profile_from_stored_data_not_the_request_body(fake_db):
    """The student's stored profile is 'adhd'. Sending profile='default' in
    the request body must have NO effect on what's actually scored."""
    _seed_session_with_events(fake_db)
    client = _client_as(STUDENT_UID)
    resp = client.post("/api/evaluate", json={
        "sessionId": "sess1", "studentId": STUDENT_UID, "profile": "default", "persist": False,
    })
    assert resp.status_code == 200
    assert resp.json()["profile"] == "adhd"


def test_evaluate_falls_back_to_default_with_no_stored_profile(fake_db):
    fake_db.store["users"][STUDENT_UID]["profile"] = {}
    _seed_session_with_events(fake_db)
    client = _client_as(STUDENT_UID)
    resp = client.post("/api/evaluate", json={
        "sessionId": "sess1", "studentId": STUDENT_UID, "profile": "adhd", "persist": False,
    })
    assert resp.json()["profile"] == "default"


def test_evaluate_stamps_config_version_and_sha(fake_db):
    _seed_session_with_events(fake_db)
    client = _client_as(STUDENT_UID)
    resp = client.post("/api/evaluate", json={
        "sessionId": "sess1", "studentId": STUDENT_UID, "persist": False,
    })
    body = resp.json()
    assert body["configVersion"]
    assert len(body["configSha256"]) == 64


# ─────────────── teacher weight overrides ───────────────


def test_mapped_teacher_can_set_an_override_and_it_changes_the_next_score(fake_db):
    _seed_session_with_events(fake_db)

    teacher_client = _client_as(TEACHER_UID)
    put_resp = teacher_client.put(
        f"/api/teachers/students/{STUDENT_UID}/dase-weights",
        json={"weights": {"ACC": 1.0}, "reason": "Testing override application end to end"},
    )
    assert put_resp.status_code == 200

    student_client = _client_as(STUDENT_UID)
    eval_resp = student_client.post("/api/evaluate", json={
        "sessionId": "sess1", "studentId": STUDENT_UID, "persist": False,
    })
    body = eval_resp.json()
    assert body["overrideId"] == STUDENT_UID
    assert body["usedWeights"] == {"ACC": 1.0}


def test_override_write_is_logged_to_audit_log(fake_db):
    teacher_client = _client_as(TEACHER_UID)
    teacher_client.put(
        f"/api/teachers/students/{STUDENT_UID}/dase-weights",
        json={"weights": {"ACC": 1.0}, "reason": "Student shows more anxiety than distraction"},
    )
    entries = list(fake_db.all_docs("audit_log").values())
    assert len(entries) == 1
    assert entries[0]["action"] == "dase_weights.override"
    assert entries[0]["actor"] == TEACHER_UID
    assert entries[0]["target"] == STUDENT_UID
    assert "reason" in entries[0]["details"]


def test_unmapped_teacher_cannot_set_an_override(fake_db):
    client = _client_as(OTHER_TEACHER_UID)
    resp = client.put(
        f"/api/teachers/students/{STUDENT_UID}/dase-weights",
        json={"weights": {"ACC": 1.0}, "reason": "Not my student"},
    )
    assert resp.status_code == 404


def test_student_cannot_set_their_own_override(fake_db):
    """require_teacher_of explicitly excludes the student themself, even for
    their own id — this is a teacher-facing action, not self-service."""
    client = _client_as(STUDENT_UID)
    resp = client.put(
        f"/api/teachers/students/{STUDENT_UID}/dase-weights",
        json={"weights": {"ACC": 1.0}, "reason": "Trying to self-override"},
    )
    assert resp.status_code == 404


def test_override_rejects_unknown_parameter(fake_db):
    client = _client_as(TEACHER_UID)
    resp = client.put(
        f"/api/teachers/students/{STUDENT_UID}/dase-weights",
        json={"weights": {"NOT_A_REAL_PARAM": 1.0}, "reason": "Should be rejected"},
    )
    assert resp.status_code == 422


def test_override_rejects_negative_weight(fake_db):
    client = _client_as(TEACHER_UID)
    resp = client.put(
        f"/api/teachers/students/{STUDENT_UID}/dase-weights",
        json={"weights": {"ACC": -0.5}, "reason": "Should be rejected"},
    )
    assert resp.status_code == 422


def test_clearing_an_override_reverts_to_profile_default(fake_db):
    _seed_session_with_events(fake_db)
    teacher_client = _client_as(TEACHER_UID)
    teacher_client.put(
        f"/api/teachers/students/{STUDENT_UID}/dase-weights",
        json={"weights": {"ACC": 1.0}, "reason": "Temporary override"},
    )
    clear_resp = teacher_client.delete(f"/api/teachers/students/{STUDENT_UID}/dase-weights")
    assert clear_resp.json()["cleared"] is True

    student_client = _client_as(STUDENT_UID)
    eval_resp = student_client.post("/api/evaluate", json={
        "sessionId": "sess1", "studentId": STUDENT_UID, "persist": False,
    })
    assert "overrideId" not in eval_resp.json()
