"""HTTP-layer tests for Phase 4's new routers — auth/validation boundaries
and the visual-event-into-VIS_ENG round trip (roadmap P4-01, P4-04).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from routers import evaluation, glossary, visual
from fakes import FakeFirestore

STUDENT_UID = "student-1"
TEACHER_UID = "teacher-1"


def _client_as(app: FastAPI, uid: str, role: str = "student") -> TestClient:
    app.dependency_overrides[auth.verify_user] = lambda: {"uid": uid, "email": "x@test.com"}
    return TestClient(app)


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setattr(auth, "db", db)
    auth._acct.clear()
    db.seed("users", STUDENT_UID, {"role": "student", "status": "active", "mustChangePassword": False})
    db.seed("users", TEACHER_UID, {"role": "teacher", "status": "active", "mustChangePassword": False})
    yield db
    auth._acct.clear()


# ─────────────────────── glossary.py ───────────────────────


def _glossary_app() -> FastAPI:
    app = FastAPI()
    app.include_router(glossary.router, prefix="/api")
    return app


def test_student_cannot_add_a_glossary_entry(fake_db, monkeypatch):
    monkeypatch.setattr(glossary, "db", fake_db)
    client = _client_as(_glossary_app(), STUDENT_UID)
    resp = client.post("/api/glossary", json={
        "term": "photosynthesis", "lang": "asl", "videoUrl": "https://storage.example.com/clip.mp4",
    })
    assert resp.status_code == 403


def test_teacher_can_add_and_student_can_read_a_glossary_entry(fake_db, monkeypatch):
    monkeypatch.setattr(glossary, "db", fake_db)
    teacher_client = _client_as(_glossary_app(), TEACHER_UID)
    put_resp = teacher_client.post("/api/glossary", json={
        "term": "Photosynthesis", "lang": "ASL", "videoUrl": "https://storage.example.com/clip.mp4",
        "captions": "Photo-syn-thesis",
    })
    assert put_resp.status_code == 200

    student_client = _client_as(_glossary_app(), STUDENT_UID)
    get_resp = student_client.get("/api/glossary/photosynthesis", params={"lang": "asl"})
    assert get_resp.status_code == 200
    assert get_resp.json()["videoUrl"] == "https://storage.example.com/clip.mp4"


def test_glossary_rejects_a_non_https_video_url(fake_db, monkeypatch):
    monkeypatch.setattr(glossary, "db", fake_db)
    client = _client_as(_glossary_app(), TEACHER_UID)
    resp = client.post("/api/glossary", json={
        "term": "test", "lang": "asl", "videoUrl": "http://insecure.example.com/clip.mp4",
    })
    assert resp.status_code == 422


def test_glossary_lookup_for_unknown_term_is_404(fake_db, monkeypatch):
    monkeypatch.setattr(glossary, "db", fake_db)
    client = _client_as(_glossary_app(), STUDENT_UID)
    resp = client.get("/api/glossary/not-a-real-term")
    assert resp.status_code == 404


# ─────────────────────── visual.py rate limiting ───────────────────────


def _visual_app() -> FastAPI:
    app = FastAPI()
    app.include_router(visual.router, prefix="/api")
    return app


def test_visual_summary_rate_limit_kicks_in(fake_db, monkeypatch):
    monkeypatch.setattr(visual, "_calls", {})
    monkeypatch.setattr(
        visual.visual_generator, "generate_visual_summary",
        lambda text, profile: {"diagram": None, "diagramType": None, "concepts": [], "degraded": False},
    )
    client = _client_as(_visual_app(), STUDENT_UID)

    statuses = [
        client.post("/api/visual-summary", json={"text": f"lesson {i}"}).status_code
        for i in range(visual._RATE_LIMIT_MAX_CALLS + 1)
    ]
    assert statuses[:visual._RATE_LIMIT_MAX_CALLS] == [200] * visual._RATE_LIMIT_MAX_CALLS
    assert statuses[-1] == 429


# ─────────────────────── evaluation.py: visual events feed VIS_ENG ───────────────────────


def _evaluation_app() -> FastAPI:
    app = FastAPI()
    app.include_router(evaluation.router, prefix="/api")
    return app


def test_visual_events_are_loaded_and_feed_vis_eng(fake_db, monkeypatch):
    monkeypatch.setattr(evaluation, "db", fake_db)
    fake_db.seed("sessions", "sess1", {"studentId": STUDENT_UID, "summary": {}})
    for i in range(3):
        fake_db.seed(f"sessions/sess1/events", f"v{i}", {
            "type": "visual", "sessionId": "sess1", "studentId": STUDENT_UID,
            "dwellMs": 4000, "expanded": True, "replayed": False, "serverTs": i,
        })

    client = _client_as(_evaluation_app(), STUDENT_UID)
    resp = client.post("/api/evaluate", json={
        "sessionId": "sess1", "studentId": STUDENT_UID, "persist": False,
    })
    body = resp.json()
    assert body["parameters"].get("VIS_ENG") is not None
    assert body["parameters"]["VIS_ENG"] > 0.5  # dwell>=3s + expanded on every sample


def test_mean_chat_frustration_is_read_from_the_session_summary(fake_db, monkeypatch):
    monkeypatch.setattr(evaluation, "db", fake_db)
    fake_db.seed("sessions", "sess1", {"studentId": STUDENT_UID, "summary": {"meanChatFrustration": 0.9}})
    for i in range(4):
        fake_db.seed("sessions/sess1/events", f"q{i}", {
            "type": "question", "sessionId": "sess1", "studentId": STUDENT_UID,
            "questionId": f"q{i}", "correct": True, "timeMs": 9000, "answerChanges": 2, "serverTs": i,
        })

    client = _client_as(_evaluation_app(), STUDENT_UID)
    resp = client.post("/api/evaluate", json={
        "sessionId": "sess1", "studentId": STUDENT_UID, "persist": False,
    })
    body = resp.json()
    # RESIL should reflect a HIGH chat-frustration input (0.9) blended in —
    # i.e. noticeably less than 1.0 (fully resilient).
    assert body["parameters"].get("RESIL") is not None
    assert body["parameters"]["RESIL"] < 0.8
