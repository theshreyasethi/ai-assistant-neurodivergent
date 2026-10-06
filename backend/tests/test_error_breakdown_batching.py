"""GET /api/evaluation/{student_id}/errors — roadmap P3-12.

Previously this read the student's session list, then did one MORE read per
session to fetch its events (N+1 reads), and always reported `sessionsScanned
= limit` regardless of how many sessions actually existed. Now it's a single
collection-group query across every sessions/*/events subcollection, and
sessionsScanned is the real count of distinct sessions the matched events
came from.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from routers import evaluation
from fakes import FakeFirestore

STUDENT_UID = "student-1"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(evaluation.router, prefix="/api")
    return app


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setattr(auth, "db", db)
    monkeypatch.setattr(evaluation, "db", db)
    auth._acct.clear()
    db.seed("users", STUDENT_UID, {"role": "student", "status": "active", "mustChangePassword": False})
    yield db
    auth._acct.clear()


def _client(fake_db):
    app = _build_app()
    app.dependency_overrides[auth.verify_user] = lambda: {"uid": STUDENT_UID, "email": "x@test.com"}
    return TestClient(app)


def test_sessions_scanned_reflects_real_distinct_sessions_not_the_limit(fake_db):
    for session_id in ("sessA", "sessB", "sessC"):
        fake_db.seed(f"sessions/{session_id}/events", "e1", {
            "type": "question", "correct": False, "studentId": STUDENT_UID,
            "sessionId": session_id, "questionId": "q1",
            "classification": {"label": "KNOWLEDGE_GAP", "confidence": 0.5, "alternatives": [], "signals": {}},
        })

    client = _client(fake_db)
    resp = client.get(f"/api/evaluation/{STUDENT_UID}/errors", params={"limit": 50})
    body = resp.json()
    assert body["sessionsScanned"] == 3
    assert body["counts"]["KNOWLEDGE_GAP"] == 3


def test_events_from_other_students_sessions_are_not_counted(fake_db):
    fake_db.seed("sessions/sessA/events", "e1", {
        "type": "question", "correct": False, "studentId": STUDENT_UID, "sessionId": "sessA", "questionId": "q1",
    })
    fake_db.seed("sessions/sessX/events", "e1", {
        "type": "question", "correct": False, "studentId": "someone-else", "sessionId": "sessX", "questionId": "q1",
    })
    client = _client(fake_db)
    resp = client.get(f"/api/evaluation/{STUDENT_UID}/errors")
    assert resp.json()["sessionsScanned"] == 1


def test_degraded_events_are_excluded_from_the_breakdown(fake_db):
    fake_db.seed("sessions/sessA/events", "e1", {
        "type": "question", "correct": False, "studentId": STUDENT_UID, "sessionId": "sessA", "questionId": "q1",
        "degraded": True,
        "classification": {"label": "KNOWLEDGE_GAP", "confidence": 0.5, "alternatives": [], "signals": {}},
    })
    client = _client(fake_db)
    resp = client.get(f"/api/evaluation/{STUDENT_UID}/errors")
    body = resp.json()
    assert body["degradedExcluded"] == 1
    assert body["totalWrong"] == 0
