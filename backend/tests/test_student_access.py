"""auth.py's per-student / per-session ownership primitives (patent-
readiness audit findings A01, A02; roadmap tasks P1-06/P1-07):

  can_access_student()              - the low-level predicate
  require_self_or_mapped_teacher()  - Depends(...) for "my own data" routes
  require_teacher_of()              - Depends(...) for teacher-only routes
  assert_session_access()           - read/write check for a sessions/{id} doc

Called directly (bypassing FastAPI's Depends machinery, same trick used
throughout this test suite) so these are true unit tests of the access
logic, independent of any specific route.
"""

import pytest
from fastapi import HTTPException

import auth
from fakes import FakeFirestore


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setattr(auth, "db", db)
    return db


def _teacher(uid="t1"):
    return {"uid": uid, "role": "teacher"}


def _student(uid="s1"):
    return {"uid": uid, "role": "student"}


def _admin(uid="a1"):
    return {"uid": uid, "role": "admin"}


# ─────────────── can_access_student ───────────────


def test_student_can_access_their_own_data(fake_db):
    assert auth.can_access_student(_student("s1"), "s1") is True


def test_student_cannot_access_another_students_data(fake_db):
    assert auth.can_access_student(_student("s1"), "s2") is False


def test_admin_can_access_any_students_data(fake_db):
    assert auth.can_access_student(_admin(), "anyone") is True


def test_teacher_mapped_via_snake_case_teacher_id_can_access(fake_db):
    fake_db.seed("users", "s1", {"role": "student", "teacher_id": "t1"})
    assert auth.can_access_student(_teacher("t1"), "s1") is True


def test_teacher_mapped_via_camel_case_teacher_id_can_access(fake_db):
    fake_db.seed("users", "s1", {"role": "student", "teacherId": "t1"})
    assert auth.can_access_student(_teacher("t1"), "s1") is True


def test_teacher_mapped_only_via_enrollments_can_access(fake_db):
    """A co-teacher relationship that exists ONLY as an enrollments/ record
    (no teacher_id/teacherId on the student's own doc) must still count."""
    fake_db.seed("users", "s1", {"role": "student", "teacher_id": "someone-else"})
    fake_db.seed("enrollments", "t1_s1", {"teacherId": "t1", "studentId": "s1", "active": True})
    assert auth.can_access_student(_teacher("t1"), "s1") is True


def test_teacher_with_inactive_enrollment_cannot_access(fake_db):
    fake_db.seed("users", "s1", {"role": "student"})
    fake_db.seed("enrollments", "t1_s1", {"teacherId": "t1", "studentId": "s1", "active": False})
    assert auth.can_access_student(_teacher("t1"), "s1") is False


def test_unmapped_teacher_cannot_access(fake_db):
    """The exact scenario finding A01 named: any teacher could previously
    read any student's analytics."""
    fake_db.seed("users", "s1", {"role": "student", "teacher_id": "someone-else"})
    assert auth.can_access_student(_teacher("t1"), "s1") is False


def test_empty_student_id_is_never_accessible(fake_db):
    assert auth.can_access_student(_admin(), "") is False


# ─────────────── require_self_or_mapped_teacher ───────────────


def test_require_self_or_mapped_teacher_allows_self(fake_db):
    result = auth.require_self_or_mapped_teacher("s1", user=_student("s1"))
    assert result["uid"] == "s1"


def test_require_self_or_mapped_teacher_allows_mapped_teacher(fake_db):
    fake_db.seed("users", "s1", {"role": "student", "teacherId": "t1"})
    result = auth.require_self_or_mapped_teacher("s1", user=_teacher("t1"))
    assert result["uid"] == "t1"


def test_require_self_or_mapped_teacher_rejects_unrelated_student_with_404(fake_db):
    with pytest.raises(HTTPException) as exc_info:
        auth.require_self_or_mapped_teacher("s2", user=_student("s1"))
    assert exc_info.value.status_code == 404


def test_require_self_or_mapped_teacher_rejects_unmapped_teacher_with_404(fake_db):
    fake_db.seed("users", "s1", {"role": "student", "teacherId": "someone-else"})
    with pytest.raises(HTTPException) as exc_info:
        auth.require_self_or_mapped_teacher("s1", user=_teacher("t1"))
    assert exc_info.value.status_code == 404


# ─────────────── require_teacher_of ───────────────


def test_require_teacher_of_allows_mapped_teacher(fake_db):
    fake_db.seed("users", "s1", {"role": "student", "teacherId": "t1"})
    result = auth.require_teacher_of("s1", user=_teacher("t1"))
    assert result["uid"] == "t1"


def test_require_teacher_of_rejects_unmapped_teacher(fake_db):
    fake_db.seed("users", "s1", {"role": "student", "teacherId": "someone-else"})
    with pytest.raises(HTTPException) as exc_info:
        auth.require_teacher_of("s1", user=_teacher("t1"))
    assert exc_info.value.status_code == 404


def test_require_teacher_of_rejects_the_student_themself(fake_db):
    """The defining difference from require_self_or_mapped_teacher: a
    teacher-facing route must not open up to the student's own self-access."""
    with pytest.raises(HTTPException) as exc_info:
        auth.require_teacher_of("s1", user=_student("s1"))
    assert exc_info.value.status_code == 404


def test_require_teacher_of_allows_admin(fake_db):
    fake_db.seed("users", "s1", {"role": "student", "teacherId": "someone-else"})
    result = auth.require_teacher_of("s1", user=_admin())
    assert result["role"] == "admin"


# ─────────────── assert_session_access ───────────────


def test_assert_session_access_read_allows_owner(fake_db):
    fake_db.seed("sessions", "sess1", {"studentId": "s1"})
    data = auth.assert_session_access("sess1", _student("s1"), write=False)
    assert data["studentId"] == "s1"


def test_assert_session_access_read_allows_mapped_teacher(fake_db):
    fake_db.seed("sessions", "sess1", {"studentId": "s1"})
    fake_db.seed("users", "s1", {"role": "student", "teacherId": "t1"})
    auth.assert_session_access("sess1", _teacher("t1"), write=False)  # must not raise


def test_assert_session_access_read_rejects_unrelated_user(fake_db):
    fake_db.seed("sessions", "sess1", {"studentId": "s1"})
    with pytest.raises(HTTPException) as exc_info:
        auth.assert_session_access("sess1", _student("s2"), write=False)
    assert exc_info.value.status_code == 404


def test_assert_session_access_write_allows_only_the_owner(fake_db):
    fake_db.seed("sessions", "sess1", {"studentId": "s1"})
    auth.assert_session_access("sess1", _student("s1"), write=True)  # must not raise
    with pytest.raises(HTTPException) as exc_info:
        auth.assert_session_access("sess1", _student("s2"), write=True)
    assert exc_info.value.status_code == 403


def test_assert_session_access_write_rejects_even_the_mapped_teacher(fake_db):
    """A teacher may READ a mapped student's session but must never be able
    to end it or evaluate it on the student's behalf."""
    fake_db.seed("sessions", "sess1", {"studentId": "s1"})
    fake_db.seed("users", "s1", {"role": "student", "teacherId": "t1"})
    with pytest.raises(HTTPException) as exc_info:
        auth.assert_session_access("sess1", _teacher("t1"), write=True)
    assert exc_info.value.status_code == 403


def test_assert_session_access_missing_session_returns_404(fake_db):
    with pytest.raises(HTTPException) as exc_info:
        auth.assert_session_access("ghost-session", _student("s1"), write=False)
    assert exc_info.value.status_code == 404
