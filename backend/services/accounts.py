"""Admin-provisioned account creation — the single path by which a
`users/{uid}` document may come into existence.

Replaces two things the patent-readiness audit flagged (findings A04, A05,
A07, A10):
  - app.py's `_seed_demo_data()`, which hard-coded admin/teacher/student
    passwords in source and ran on every process start, in every
    deployment.
  - the original `POST /admin/create-user`, which accepted ANY string as
    `teacher_id` with no check it belonged to an active teacher, let the
    admin choose the new account's password (so a weak or reused password
    becomes the student's password), and wrote no audit trail.

Every account created here gets a server-generated temporary password
(never the caller's choice), `status="pending_first_login"` +
`mustChangePassword=True` (the flag a forced-change flow will enforce —
not yet built; this module only sets it), a matching `enrollments/` record
for students, and an `audit_log` entry.

Deliberately framework-agnostic (no FastAPI import): usable from the HTTP
routers (`routers/admin.py`), the CLI scripts (`scripts/seed_demo.py`,
`scripts/create_admin.py`), and unit-testable without spinning up FastAPI
or a live Firebase project — see `tests/test_admin_provisioning.py`, which
monkeypatches the `db` and `firebase_auth` names below.
"""

from __future__ import annotations

import re
import secrets
from typing import Any, Dict, List, Literal, Optional

from firebase_admin import auth as firebase_auth
from firebase_admin import firestore as admin_firestore

from config import SCHOOL_LOGIN_DOMAIN
from firebase_config import db

Role = Literal["student", "teacher"]

# Unambiguous when read aloud or handwritten on a printed hand-off sheet:
# no 0/O, 1/l/I.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")


class AccountError(Exception):
    """Base for every error create_user() / create_users_bulk() can raise."""


class TeacherInvalid(AccountError):
    """A student account was requested with no teacherId, or a teacherId
    that does not point at an active teacher account."""


class UsernameTaken(AccountError):
    """The requested login (explicit email, or username@SCHOOL_LOGIN_DOMAIN)
    is already in use."""


class ValidationError(AccountError):
    """Malformed input that isn't already a Pydantic-level shape error."""


def generate_temp_password() -> str:
    """12 characters, grouped XXXX-XXXX-XXXX. Cryptographically random —
    never derived from, or reused across, any other account, and never
    chosen by the admin doing the creating."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(12))
    return "-".join(raw[i : i + 4] for i in range(0, 12, 4))


def _require_db() -> None:
    if db is None:
        raise AccountError("Persistence unavailable (Firestore not configured)")


def _validate_teacher(teacher_id: Optional[str]) -> None:
    if not teacher_id:
        raise TeacherInvalid("A student account must be assigned to a teacher")
    snap = db.collection("users").document(teacher_id).get()
    if not snap.exists:
        raise TeacherInvalid(f"teacherId '{teacher_id}' does not exist")
    data = snap.to_dict() or {}
    if data.get("role") != "teacher":
        raise TeacherInvalid(f"teacherId '{teacher_id}' is not a teacher account")
    if data.get("status", "active") == "disabled":
        raise TeacherInvalid(f"teacherId '{teacher_id}' is disabled")


def create_user(
    *,
    role: Role,
    display_name: str,
    username: str,
    grade_level: Optional[str] = None,
    teacher_id: Optional[str] = None,
    email: Optional[str] = None,
    created_by: str,
) -> Dict[str, Any]:
    """Create one admin-provisioned account.

    Raises TeacherInvalid, UsernameTaken or ValidationError on bad input,
    plain AccountError if Firestore is unavailable. On any failure after the
    Firebase Auth user was created (Firestore write failed), the Auth user
    is deleted again rather than left as an orphaned, roleless login.
    """
    _require_db()

    if role not in ("student", "teacher"):
        raise ValidationError(f"Unsupported role for admin provisioning: {role!r}")
    if not _USERNAME_RE.match(username or ""):
        raise ValidationError(
            "username must be 3-32 characters: lowercase letters, digits, '.', '_' or '-'"
        )
    if not (display_name or "").strip():
        raise ValidationError("displayName is required")

    if role == "student":
        _validate_teacher(teacher_id)
    else:
        teacher_id = None  # a teacher is never itself "assigned to" a teacherId

    login = email or f"{username}@{SCHOOL_LOGIN_DOMAIN}"
    temp_password = generate_temp_password()

    try:
        record = firebase_auth.create_user(
            email=login, password=temp_password, display_name=display_name,
        )
    except firebase_auth.EmailAlreadyExistsError as exc:
        raise UsernameTaken(f"'{login}' is already in use") from exc

    uid = record.uid
    now = admin_firestore.SERVER_TIMESTAMP

    user_doc: Dict[str, Any] = {
        "role": role,
        "email": login,
        "username": username,
        "displayName": display_name,
        "status": "pending_first_login",
        "mustChangePassword": True,
        "createdBy": created_by,
        "createdAt": now,
    }
    if grade_level is not None:
        # Dual-written under both spellings. DATA_CONTRACT v1 (and every
        # existing reader: app.py's /teacher/students, /teacher/analytics/
        # {id}, routers/analytics.py's _teacher_roster) uses snake_case
        # grade_level/teacher_id; the v2 schema this module writes uses
        # camelCase. Writing both keeps every current reader working
        # unmodified until roadmap task P1-06 migrates them to
        # camelCase-only — see docs/PROJECT_EXPLANATION.md.
        user_doc["grade_level"] = grade_level
        user_doc["gradeLevel"] = grade_level
    if teacher_id is not None:
        user_doc["teacher_id"] = teacher_id
        user_doc["teacherId"] = teacher_id

    try:
        batch = db.batch()
        batch.set(db.collection("users").document(uid), user_doc)
        if role == "student":
            batch.set(
                db.collection("enrollments").document(f"{teacher_id}_{uid}"),
                {
                    "teacherId": teacher_id,
                    "studentId": uid,
                    "classId": None,
                    "active": True,
                    "since": now,
                    "endedAt": None,
                    "createdBy": created_by,
                },
            )
        batch.set(
            db.collection("audit_log").document(),
            {
                "actor": created_by,
                "action": f"{role}.create",
                "target": uid,
                "details": {"username": username, "teacherId": teacher_id},
                "at": now,
            },
        )
        batch.commit()
    except Exception:
        # The Firebase Auth user already exists at this point — clean it up
        # rather than leave an orphaned login with no role and no owner.
        try:
            firebase_auth.delete_user(uid)
        except Exception:
            pass
        raise

    return {
        "uid": uid,
        "loginId": login,
        "temporaryPassword": temp_password,
        "role": role,
        "username": username,
        "displayName": display_name,
        "status": "pending_first_login",
    }


def _resolve_teacher_id_by_email(email: str) -> Optional[str]:
    """Single-field query on purpose — combining it with a second `.where`
    for role risks needing a composite index in a real Firestore project;
    filtering role/status in Python over the (small) result set avoids that
    entirely."""
    if not email:
        return None
    docs = db.collection("users").where("email", "==", email).stream()
    for d in docs:
        data = d.to_dict() or {}
        if data.get("role") == "teacher" and data.get("status", "active") != "disabled":
            return d.id
    return None


def create_users_bulk(rows: List[Dict[str, str]], created_by: str) -> List[Dict[str, Any]]:
    """rows: [{"role", "name", "username", "grade", "teacher_email"}, ...] —
    the CSV shape POST /admin/users/bulk parses. `teacher_email` is resolved
    to a teacherId per row; every other validation is the same as
    create_user(). Never raises for a single bad row — each row gets its own
    result so one typo in a 40-row import doesn't lose the other 39."""
    _require_db()
    results: List[Dict[str, Any]] = []

    for i, row in enumerate(rows):
        row_result: Dict[str, Any] = {"row": i + 1, "input": row}
        try:
            role = (row.get("role") or "").strip().lower()
            teacher_id = None
            if role == "student":
                teacher_email = (row.get("teacher_email") or "").strip()
                teacher_id = _resolve_teacher_id_by_email(teacher_email)
                if teacher_id is None:
                    raise TeacherInvalid(
                        f"no active teacher found with email '{teacher_email}'"
                    )
            created = create_user(
                role=role,  # type: ignore[arg-type]  # validated inside create_user
                display_name=(row.get("name") or "").strip(),
                username=(row.get("username") or "").strip().lower(),
                grade_level=(row.get("grade") or "").strip() or None,
                teacher_id=teacher_id,
                created_by=created_by,
            )
            # NOT `row_result.update(status="created", **created)` — `created`
            # already has its own "status" key ("pending_first_login"), which
            # collides with the row-outcome "status" ("created"/"error") and
            # raises TypeError: got multiple values for keyword argument
            # 'status'. Rename the account's own status on the way in instead.
            created["accountStatus"] = created.pop("status")
            row_result.update(status="created", **created)
        except AccountError as exc:
            row_result.update(status="error", error=str(exc))
        except Exception as exc:  # noqa: BLE001 — one bad row must never abort the batch
            row_result.update(status="error", error=f"unexpected error: {exc}")
        results.append(row_result)

    return results
