"""Unit tests for services/accounts.py — the account-creation logic behind
POST /api/admin/users, POST /api/admin/users/bulk, and the legacy
POST /admin/create-user alias.

Directly verifies the two things patent-readiness-audit task P1-04's
verification step asked for:
  - creating a student without an active teacher yields a 422 at the HTTP
    layer (test_admin_router_http.py) / a TeacherInvalid here (this file)
  - admin creations populate mustChangePassword=True and write an
    audit_log entry

See tests/fakes.py for why these use in-memory doubles rather than a live
Firebase project.
"""

import pytest

from services import accounts
from fakes import FakeAuth, FakeFirestore


@pytest.fixture
def fake_backend(monkeypatch):
    fake_db = FakeFirestore()
    fake_auth = FakeAuth()
    monkeypatch.setattr(accounts, "db", fake_db)
    monkeypatch.setattr(accounts, "firebase_auth", fake_auth)
    return fake_db, fake_auth


def _seed_teacher(fake_db, uid="teacher-1", **extra):
    fake_db.seed("users", uid, {"role": "teacher", "status": "active", "email": f"{uid}@school.org", **extra})
    return uid


# ─────────────── teacher validation (finding A07) ───────────────


def test_student_with_no_teacher_id_is_rejected(fake_backend):
    fake_db, _ = fake_backend
    with pytest.raises(accounts.TeacherInvalid):
        accounts.create_user(role="student", display_name="Kid", username="kid1", created_by="admin-1")


def test_student_with_unknown_teacher_id_is_rejected(fake_backend):
    fake_db, _ = fake_backend
    with pytest.raises(accounts.TeacherInvalid):
        accounts.create_user(
            role="student", display_name="Kid", username="kid1",
            teacher_id="does-not-exist", created_by="admin-1",
        )


def test_student_with_disabled_teacher_is_rejected(fake_backend):
    fake_db, _ = fake_backend
    _seed_teacher(fake_db, "t1", status="disabled")
    with pytest.raises(accounts.TeacherInvalid):
        accounts.create_user(
            role="student", display_name="Kid", username="kid1",
            teacher_id="t1", created_by="admin-1",
        )


def test_student_with_non_teacher_account_as_teacher_id_is_rejected(fake_backend):
    fake_db, _ = fake_backend
    fake_db.seed("users", "s1", {"role": "student", "status": "active"})
    with pytest.raises(accounts.TeacherInvalid):
        accounts.create_user(
            role="student", display_name="Kid", username="kid1",
            teacher_id="s1", created_by="admin-1",
        )


def test_teacher_creation_needs_no_teacher_id(fake_backend):
    fake_db, _ = fake_backend
    result = accounts.create_user(role="teacher", display_name="Ms Lee", username="mslee", created_by="admin-1")
    assert result["status"] == "pending_first_login"
    assert fake_db.all_docs("enrollments") == {}


# ─────────────── successful creation: schema + security properties ───────────────


def test_valid_student_creation_sets_pending_first_login_and_must_change_password(fake_backend):
    fake_db, _ = fake_backend
    _seed_teacher(fake_db, "t1")

    result = accounts.create_user(
        role="student", display_name="Kid One", username="kid1",
        teacher_id="t1", grade_level="4", created_by="admin-1",
    )

    assert result["status"] == "pending_first_login"
    stored = fake_db.get_doc("users", result["uid"])
    assert stored["status"] == "pending_first_login"
    assert stored["mustChangePassword"] is True


def test_temporary_password_shape_and_never_client_supplied(fake_backend):
    fake_db, _ = fake_backend
    _seed_teacher(fake_db, "t1")
    result = accounts.create_user(
        role="student", display_name="Kid", username="kid1",
        teacher_id="t1", created_by="admin-1",
    )
    pw = result["temporaryPassword"]
    assert len(pw) == 14  # XXXX-XXXX-XXXX
    assert pw.count("-") == 2
    for c in "0O1lI":
        assert c not in pw.replace("-", "")


def test_two_created_accounts_never_share_a_generated_password(fake_backend):
    r1 = accounts.create_user(role="teacher", display_name="A", username="teacha", created_by="admin-1")
    r2 = accounts.create_user(role="teacher", display_name="B", username="teachb", created_by="admin-1")
    assert r1["temporaryPassword"] != r2["temporaryPassword"]


def test_fields_dual_written_snake_and_camel_case_for_existing_readers(fake_backend):
    """app.py's /teacher/students and routers/analytics.py's _teacher_roster
    both query .where("teacher_id", "==", uid) — must keep matching v2 docs."""
    fake_db, _ = fake_backend
    _seed_teacher(fake_db, "t1")
    result = accounts.create_user(
        role="student", display_name="Kid", username="kid1",
        teacher_id="t1", grade_level="6", created_by="admin-1",
    )
    stored = fake_db.get_doc("users", result["uid"])
    assert stored["teacher_id"] == "t1" and stored["teacherId"] == "t1"
    assert stored["grade_level"] == "6" and stored["gradeLevel"] == "6"


def test_enrollment_record_created_for_student(fake_backend):
    fake_db, _ = fake_backend
    _seed_teacher(fake_db, "t1")
    result = accounts.create_user(
        role="student", display_name="Kid", username="kid1",
        teacher_id="t1", created_by="admin-1",
    )
    enrollment = fake_db.get_doc("enrollments", f"t1_{result['uid']}")
    assert enrollment is not None
    assert enrollment["active"] is True
    assert enrollment["teacherId"] == "t1"
    assert enrollment["studentId"] == result["uid"]


def test_audit_log_entry_written_on_creation(fake_backend):
    fake_db, _ = fake_backend
    _seed_teacher(fake_db, "t1")
    result = accounts.create_user(
        role="student", display_name="Kid", username="kid1",
        teacher_id="t1", created_by="admin-42",
    )
    entries = list(fake_db.all_docs("audit_log").values())
    assert len(entries) == 1
    assert entries[0]["actor"] == "admin-42"
    assert entries[0]["action"] == "student.create"
    assert entries[0]["target"] == result["uid"]


def test_duplicate_login_raises_username_taken(fake_backend):
    accounts.create_user(role="teacher", display_name="A", username="dupe", created_by="admin-1")
    with pytest.raises(accounts.UsernameTaken):
        accounts.create_user(role="teacher", display_name="B", username="dupe", created_by="admin-1")


def test_invalid_username_shape_raises_validation_error(fake_backend):
    with pytest.raises(accounts.ValidationError):
        accounts.create_user(role="teacher", display_name="A", username="!!", created_by="admin-1")


def test_firestore_failure_rolls_back_the_auth_user(fake_backend, monkeypatch):
    """If the Firestore batch fails after Firebase Auth already created the
    login, the account must not be left as an orphaned, roleless login."""
    fake_db, fake_auth = fake_backend
    _seed_teacher(fake_db, "t1")

    def _boom(*_a, **_kw):
        raise RuntimeError("Firestore is down")

    monkeypatch.setattr(fake_db, "batch", _boom)

    with pytest.raises(RuntimeError):
        accounts.create_user(
            role="student", display_name="Kid", username="kid1",
            teacher_id="t1", created_by="admin-1",
        )
    assert len(fake_auth.deleted) == 1


# ─────────────── bulk CSV import ───────────────


def test_bulk_import_reports_row_level_status(fake_backend):
    fake_db, _ = fake_backend
    _seed_teacher(fake_db, "t1", email="teach@school.org")

    rows = [
        {"role": "student", "name": "Good Kid", "username": "goodkid", "grade": "3", "teacher_email": "teach@school.org"},
        {"role": "student", "name": "Orphan Kid", "username": "orphankid", "grade": "3", "teacher_email": "nobody@school.org"},
    ]
    results = accounts.create_users_bulk(rows, created_by="admin-1")

    assert results[0]["status"] == "created"
    assert results[1]["status"] == "error"
    assert "no active teacher" in results[1]["error"]
    # one bad row must not prevent the good row from being created: the
    # seeded teacher (1) plus goodkid (1) — orphankid was never created.
    assert len(fake_db.all_docs("users")) == 2
