"""Explicit, opt-in demo roster seeding for local development.

Replaces app.py's old `_seed_demo_data()`, which ran automatically on every
process start — in every deployment, including production — and had
`"admin@123"` / `"teacher@123"` / `"student@123"` as literal strings in
source (patent-readiness audit finding A04). This script:

  - never runs implicitly (nothing imports it; app.py no longer calls it
    at startup),
  - refuses to run at all when ENV=production (backend/config.py),
  - reads every password from an environment variable — never a hard-coded
    default — so `git blame`/`grep` on this file can never leak a demo
    credential again.

These are throwaway LOCAL DEV accounts meant to be logged into immediately
with a memorable, known password, which is a different need from the real
admin-provisioning flow (services/accounts.py): that flow always generates
a random temporary password and forces a change on first login, because it
provisions REAL accounts for real teachers and children. This script's
accounts are created active, with no forced password change, purely for
exercising the app locally.

Usage (PowerShell):
    $env:DEMO_ADMIN_PASSWORD    = "..."
    $env:DEMO_TEACHER_PASSWORD  = "..."
    $env:DEMO_STUDENT_PASSWORD  = "..."
    python scripts/seed_demo.py

Usage (bash):
    DEMO_ADMIN_PASSWORD=... DEMO_TEACHER_PASSWORD=... DEMO_STUDENT_PASSWORD=... \
        python scripts/seed_demo.py

Does NOT seed an admin account — that always goes through
scripts/create_admin.py, out-of-band, one admin at a time. If
DEMO_ADMIN_PASSWORD is set, this script will also seed a demo admin purely
for local convenience; if it's unset, teachers/students are still seeded
and the admin step is skipped with a note.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run as `python scripts/seed_demo.py`

from config import ENV  # noqa: E402
from firebase_admin import auth as firebase_auth  # noqa: E402
from firebase_admin import firestore as admin_firestore  # noqa: E402
from firebase_config import db  # noqa: E402

# Synthetic actor identity for the audit trail — these accounts are created
# by a developer running a script, not by a real admin user document.
_SEED_ACTOR = "cli:seed_demo"


def _require_dev_env() -> None:
    if ENV == "production":
        print(
            "[seed_demo] Refusing to run: ENV=production. This script creates "
            "accounts with known, developer-chosen passwords and must never "
            "touch a production project.",
            file=sys.stderr,
        )
        sys.exit(1)


def _require_password(var_name: str) -> str:
    value = os.environ.get(var_name)
    if not value:
        print(
            f"[seed_demo] {var_name} is not set. Refusing to fall back to a "
            f"hard-coded password - export {var_name} and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


def _ensure_user(email: str, password: str, doc: dict) -> str:
    try:
        existing = firebase_auth.get_user_by_email(email)
        uid = existing.uid
    except firebase_auth.UserNotFoundError:
        record = firebase_auth.create_user(email=email, password=password, display_name=doc.get("username", email))
        uid = record.uid
    doc = {**doc, "createdBy": _SEED_ACTOR}
    existing_snap = db.collection("users").document(uid).get()
    if not existing_snap.exists:
        doc["createdAt"] = admin_firestore.SERVER_TIMESTAMP
    db.collection("users").document(uid).set(doc, merge=True)
    return uid


def main() -> None:
    _require_dev_env()
    if db is None:
        print("[seed_demo] Firestore is not configured (see firebase_config.py). Aborting.", file=sys.stderr)
        sys.exit(1)

    teacher_password = _require_password("DEMO_TEACHER_PASSWORD")
    student_password = _require_password("DEMO_STUDENT_PASSWORD")
    admin_password = os.environ.get("DEMO_ADMIN_PASSWORD")

    if admin_password:
        admin_uid = _ensure_user(
            "admin@demo.eduease.local", admin_password,
            {"email": "admin@demo.eduease.local", "username": "demo-admin", "role": "admin", "status": "active", "mustChangePassword": False},
        )
        print(f"[seed_demo] admin ready: admin@demo.eduease.local ({admin_uid})")
    else:
        print("[seed_demo] DEMO_ADMIN_PASSWORD not set - skipping demo admin (use scripts/create_admin.py for a real one).")

    teacher_uids: list[str] = []
    for i in range(1, 4):
        email = f"teacher{i}@demo.eduease.local"
        uid = _ensure_user(
            email, teacher_password,
            {"email": email, "username": f"teacher{i}", "role": "teacher", "status": "active", "mustChangePassword": False},
        )
        teacher_uids.append(uid)

    student_count = 0
    for i in range(1, 11):
        email = f"student{i}@demo.eduease.local"
        teacher_uid = teacher_uids[(i - 1) % len(teacher_uids)]
        grade = str(((i - 1) % 8) + 1)
        student_uid = _ensure_user(
            email, student_password,
            {
                "email": email, "username": f"student{i}", "role": "student",
                "status": "active", "mustChangePassword": False,
                # Dual-written for the same reason services/accounts.py dual-writes:
                # every existing snake_case reader (app.py /teacher/students,
                # routers/analytics.py _teacher_roster) keeps working.
                "grade_level": grade, "gradeLevel": grade,
                "teacher_id": teacher_uid, "teacherId": teacher_uid,
            },
        )
        db.collection("enrollments").document(f"{teacher_uid}_{student_uid}").set(
            {"teacherId": teacher_uid, "studentId": student_uid, "active": True,
             "since": admin_firestore.SERVER_TIMESTAMP, "createdBy": _SEED_ACTOR},
            merge=True,
        )
        student_count += 1

    # Deliberately no fake quiz_results/telemetry_sessions/evaluations seeding —
    # that used to wipe and refill those collections with random numbers on
    # every restart, corrupting the teacher dashboard with data disconnected
    # from anything a student actually did. Real usage populates them.
    print(f"[seed_demo] Seeded {student_count} students across {len(teacher_uids)} teachers (ENV={ENV}).")


if __name__ == "__main__":
    main()
