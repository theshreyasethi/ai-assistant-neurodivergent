"""HTTP-layer tests for GET /api/analytics/class (roadmap U1): the
measurement-invariance warning on the pooled class-average DASE score.

DASE scores are each disability profile's OWN weighted composite, not a
shared scale — pooling a blind student's score with an ADHD student's score
treats two differently-measured constructs as if they were one. These tests
pin the behaviour: the pooled classAverageScore is still returned (a single
"classroom at a glance" number remains useful), but measurementInvarianceWarning
is populated whenever more than one distinct profile actually contributes a
scored student, and is None when the class has none or only one.

Same pattern as test_overrides_and_scoring.py: mounts the real router on a
throwaway app, overrides only auth.verify_user, so require_active_user /
verify_role / the actual aggregation logic in routers/analytics.py all run
end to end.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from routers import analytics
from fakes import FakeFirestore

TEACHER_UID = "teacher-1"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(analytics.router, prefix="/api")
    return app


def _client_as(uid: str) -> TestClient:
    app = _build_app()
    app.dependency_overrides[auth.verify_user] = lambda: {"uid": uid, "email": "x@test.com"}
    return TestClient(app)


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setattr(auth, "db", db)
    monkeypatch.setattr(analytics, "db", db)
    auth._acct.clear()

    db.seed("users", TEACHER_UID, {"role": "teacher", "status": "active", "mustChangePassword": False})
    yield db
    auth._acct.clear()


def _seed_student(fake_db, uid: str, primary: str, score: float) -> None:
    # analytics.py's _teacher_roster filters on snake_case teacher_id —
    # confirmed by reading routers/analytics.py directly, not assumed.
    fake_db.seed("users", uid, {
        "role": "student", "status": "active", "mustChangePassword": False,
        "teacher_id": TEACHER_UID, "email": f"{uid}@test.com",
        "profile": {"primary": primary, "disabilities": [primary]},
    })
    fake_db.seed("evaluations", f"eval-{uid}", {
        "studentId": uid, "score": score, "coverage": 0.9, "computedAt": 1,
    })


def test_warning_present_when_scored_students_span_more_than_one_profile(fake_db):
    _seed_student(fake_db, "student-adhd", "adhd", 0.8)
    _seed_student(fake_db, "student-blind", "blind", 0.4)

    resp = _client_as(TEACHER_UID).get("/api/analytics/class")
    assert resp.status_code == 200
    body = resp.json()

    assert body["classAverageScore"] == pytest.approx(0.6, abs=1e-6)
    assert body["measurementInvarianceWarning"] is not None
    assert "different disability profiles" in body["measurementInvarianceWarning"]
    assert set(body["averageByPrimaryDisability"]) == {"adhd", "blind"}


def test_warning_absent_when_every_scored_student_shares_one_profile(fake_db):
    _seed_student(fake_db, "student-1", "adhd", 0.7)
    _seed_student(fake_db, "student-2", "adhd", 0.9)

    resp = _client_as(TEACHER_UID).get("/api/analytics/class")
    assert resp.status_code == 200
    body = resp.json()

    assert body["measurementInvarianceWarning"] is None


def test_warning_absent_when_no_student_is_scored_yet(fake_db):
    fake_db.seed("users", "student-1", {
        "role": "student", "status": "active", "mustChangePassword": False,
        "teacher_id": TEACHER_UID, "email": "student-1@test.com",
        "profile": {"primary": "adhd", "disabilities": ["adhd"]},
    })

    resp = _client_as(TEACHER_UID).get("/api/analytics/class")
    assert resp.status_code == 200
    body = resp.json()

    assert body["classAverageScore"] is None
    assert body["measurementInvarianceWarning"] is None
