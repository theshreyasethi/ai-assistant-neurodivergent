"""Out-of-band admin account bootstrapping.

The only way an `admin` account should ever come into existence: run this
script by hand, on a machine with access to the Firebase project's
credentials, and type the new admin's password directly into the terminal
(hidden — `getpass`, never echoed, never passed as a CLI argument where it
would land in shell history or `ps`).

Nothing in the HTTP API can create an admin account — `POST /api/admin/users`
(routers/admin.py) only accepts role "student" or "teacher" — by design:
letting anyone already holding an admin bearer token mint more admins over
HTTP is exactly the kind of self-perpetuating privilege loop this script
exists to avoid. Every admin account traces back to someone with terminal
access to the deployment running this script.

Usage:
    python scripts/create_admin.py
    python scripts/create_admin.py --email admin@example.org
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run as `python scripts/create_admin.py`

from firebase_admin import auth as firebase_auth  # noqa: E402
from firebase_admin import firestore as admin_firestore  # noqa: E402
from firebase_config import db  # noqa: E402

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LEN = 10


def _prompt_email(preset: str | None) -> str:
    if preset:
        email = preset.strip()
    else:
        email = input("Admin email address: ").strip()
    if not _EMAIL_RE.match(email):
        print(f"'{email}' doesn't look like a valid email address.", file=sys.stderr)
        sys.exit(1)
    return email


def _prompt_password() -> str:
    while True:
        pw1 = getpass.getpass(f"New admin password (min {_MIN_PASSWORD_LEN} characters, hidden): ")
        if len(pw1) < _MIN_PASSWORD_LEN:
            print(f"Password must be at least {_MIN_PASSWORD_LEN} characters. Try again.\n")
            continue
        pw2 = getpass.getpass("Type it again to confirm: ")
        if pw1 != pw2:
            print("Passwords didn't match. Try again.\n")
            continue
        return pw1


def create_admin(email: str, password: str, display_name: str | None = None) -> str:
    """Creates the Firebase Auth user + users/{uid} Firestore document, or —
    if a Firebase Auth user with this email already exists (e.g. a prior
    partial run, or an account created for testing before this script
    existed) — promotes their existing Firestore profile to role="admin"
    instead of failing outright."""
    if db is None:
        raise RuntimeError("Firestore is not configured (see backend/firebase_config.py)")

    try:
        record = firebase_auth.create_user(email=email, password=password, display_name=display_name or email)
        uid = record.uid
        created_new = True
    except firebase_auth.EmailAlreadyExistsError:
        record = firebase_auth.get_user_by_email(email)
        uid = record.uid
        firebase_auth.update_user(uid, password=password)
        created_new = False

    doc_ref = db.collection("users").document(uid)
    existing = doc_ref.get()
    payload = {
        "email": email,
        "username": email.split("@")[0],
        "displayName": display_name or email,
        "role": "admin",
        "status": "active",
        "mustChangePassword": False,  # the admin just chose this password themself, interactively
        "createdBy": "cli:create_admin",
    }
    if not existing.exists:
        payload["createdAt"] = admin_firestore.SERVER_TIMESTAMP
    doc_ref.set(payload, merge=True)

    db.collection("audit_log").document().set({
        "actor": "cli:create_admin",
        "action": "admin.create" if created_new else "admin.promote_existing",
        "target": uid,
        "details": {"email": email},
        "at": admin_firestore.SERVER_TIMESTAMP,
    })

    return uid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", help="Admin email address (prompted if omitted)")
    args = parser.parse_args()

    email = _prompt_email(args.email)
    password = _prompt_password()

    uid = create_admin(email, password)
    print(f"\n[create_admin] Admin account ready: {email} (uid={uid})")
    print("[create_admin] Hand this credential to the admin directly - it is not stored anywhere else.")


if __name__ == "__main__":
    main()
