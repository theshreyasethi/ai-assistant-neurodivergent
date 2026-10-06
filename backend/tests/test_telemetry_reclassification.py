"""Server-side re-classification on ingest — roadmap P3-04.

The client's own classification is never trusted as final: a wrong answer
with no label, or one stamped by a classifier version that has since
changed, gets relabelled from its own stored raw signals at ingest time.
This is what makes a stored event's classification reproducible later from
(events, configSha256) rather than a one-time client-side guess.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from routers import telemetry
from services import dase_engine
from fakes import FakeFirestore

OWNER_UID = "student-owner"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(telemetry.router, prefix="/api")
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
    monkeypatch.setattr(telemetry, "db", db)
    auth._acct.clear()
    db.seed("users", OWNER_UID, {"role": "student", "status": "active", "mustChangePassword": False})
    db.seed("sessions", "sess1", {"studentId": OWNER_UID, "kind": "quiz", "summary": None})
    yield db
    auth._acct.clear()


def _wrong_event(**overrides):
    base = {
        "type": "question", "sessionId": "sess1", "studentId": "irrelevant-client-value", "ts": 1,
        "questionId": "q1", "correct": False, "timeMs": 1200, "focusRatio": 0.2, "focusSamples": 10,
    }
    return {**base, **overrides}


def _seed_baseline(client, n=5, time_ms=5000):
    """classify_error needs prior same-session response times to compute a
    baseline at all; a cold session with no history falls through to the
    honest no-comparison default (KNOWLEDGE_GAP), same as test_classifier.py."""
    for i in range(n):
        client.post("/api/events", json={"events": [_wrong_event(
            questionId=f"baseline{i}", correct=True, timeMs=time_ms, focusRatio=None, focusSamples=0,
        )]})


def test_wrong_answer_with_no_classification_gets_one_stamped_on_ingest(fake_db):
    client = _client_as(fake_db, OWNER_UID)
    _seed_baseline(client)
    resp = client.post("/api/events", json={"events": [_wrong_event(timeMs=1200)]})
    assert resp.json()["written"] == 1

    stored = fake_db.get_doc("sessions/sess1/events", "q_q1_1")
    assert stored["classification"] is not None
    assert stored["classification"]["label"] == dase_engine.ATTENTION_LAPSE
    assert stored["classifierVersion"] == dase_engine.CLASSIFIER_VERSION
    assert len(stored["configSha256"]) == 64


def test_stale_classifier_version_is_recomputed(fake_db):
    client = _client_as(fake_db, OWNER_UID)
    _seed_baseline(client)
    client.post("/api/events", json={"events": [_wrong_event(
        timeMs=1200,
        classification={"label": "KNOWLEDGE_GAP", "confidence": 0.1, "alternatives": [], "signals": {}},
        classifierVersion="0.1-stale",
    )]})
    stored = fake_db.get_doc("sessions/sess1/events", "q_q1_1")
    assert stored["classifierVersion"] == dase_engine.CLASSIFIER_VERSION
    assert stored["classification"]["label"] == dase_engine.ATTENTION_LAPSE  # recomputed, not the stale label


def test_current_classifier_version_is_left_alone(fake_db):
    """A client that already carries a current-version label (the closed
    loop called POST /api/classify itself) must not be silently overwritten
    with a result computed from different prior-times context."""
    client = _client_as(fake_db, OWNER_UID)
    client.post("/api/events", json={"events": [_wrong_event(
        classification={"label": "PROCESSING_DELAY", "confidence": 0.77, "alternatives": [], "signals": {}},
        classifierVersion=dase_engine.CLASSIFIER_VERSION,
    )]})
    stored = fake_db.get_doc("sessions/sess1/events", "q_q1_1")
    assert stored["classification"]["label"] == "PROCESSING_DELAY"
    assert stored["classification"]["confidence"] == 0.77


def test_correct_answers_are_never_classified(fake_db):
    client = _client_as(fake_db, OWNER_UID)
    client.post("/api/events", json={"events": [_wrong_event(correct=True)]})
    stored = fake_db.get_doc("sessions/sess1/events", "q_q1_1")
    assert stored["classification"] is None


def test_prior_times_come_from_already_committed_events_in_the_same_session(fake_db):
    client = _client_as(fake_db, OWNER_UID)
    # A fast, well-established personal baseline of 5000ms, then one very
    # slow wrong answer -> PROCESSING_DELAY, which needs those prior
    # events to already be visible to the classifier.
    for i in range(5):
        client.post("/api/events", json={"events": [_wrong_event(
            questionId=f"q{i}", correct=True, timeMs=5000, focusRatio=None, focusSamples=0,
        )]})
    client.post("/api/events", json={"events": [_wrong_event(questionId="q9", timeMs=12000)]})
    stored = fake_db.get_doc("sessions/sess1/events", "q_q9_1")
    assert stored["classification"]["label"] == dase_engine.PROCESSING_DELAY
