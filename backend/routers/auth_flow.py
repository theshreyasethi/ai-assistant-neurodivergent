"""Forced first-login password change.

  POST /auth/first-login-password

Mounted under /api in app.py, giving /api/auth/first-login-password — the
one path auth.require_active_user() exempts from its
PASSWORD_CHANGE_REQUIRED block (see auth.py, FIRST_LOGIN_PASSWORD_PATH).
Every account services/accounts.py provisions gets mustChangePassword=True;
this is the only route that can ever turn it back off, and it does the
turning-off itself — never trust the client to report success.
"""

import re

from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import auth as firebase_auth
from firebase_admin import firestore as admin_firestore
from pydantic import BaseModel, Field, field_validator

from auth import invalidate_account_cache, require_active_user
from firebase_config import db

router = APIRouter(prefix="/auth")

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128

# A small, deliberately non-exhaustive deny-list — rejecting every weak
# password is a breached-password-API job (e.g. HaveIBeenPwned's
# k-anonymity range query; a real follow-up, not built here). This catches
# the most obvious "typed the minimum and stopped" choices: sequential
# digits/letters, keyboard walks, and generic placeholder words a hand-off
# sheet's format might tempt someone to reuse verbatim.
_COMMON_PASSWORDS = {
    "password123", "password1234", "passwordpassword",
    "1234567890", "0123456789", "12345678901", "123456789012",
    "qwertyuiop", "qwertyuiop1", "qwertyasdfgh",
    "letmein123", "letmein1234", "changeme123", "changeme1234",
    "welcome123", "welcome1234", "abcdefghij", "abcdefghijk",
}
_SEQUENTIAL_RE = re.compile(r"^(0123456789|1234567890|abcdefghij|abcdefghijklmnop)+")


class NewPasswordRequest(BaseModel):
    newPassword: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("newPassword")
    @classmethod
    def _reject_obvious(cls, value: str) -> str:
        normalised = value.strip().lower()
        if normalised in _COMMON_PASSWORDS:
            raise ValueError("That password is too easy to guess. Please choose a different one.")
        if len(set(normalised)) <= 2:
            raise ValueError("That password doesn't have enough variety. Please choose a different one.")
        if _SEQUENTIAL_RE.match(normalised):
            raise ValueError("That password is too predictable. Please choose a different one.")
        return value


@router.post("/first-login-password")
async def first_login_password(
    body: NewPasswordRequest, user: dict = Depends(require_active_user),
):
    uid = user.get("uid", "")
    if db is None:
        raise HTTPException(status_code=503, detail="Persistence unavailable")

    # Server-side, via the Admin SDK — never the client's own updatePassword,
    # which a compromised or buggy client could simply skip while still
    # reporting success. This IS the only place mustChangePassword may be
    # cleared, so the actual password change has to happen here too.
    try:
        firebase_auth.update_user(uid, password=body.newPassword)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Could not update password: {exc}")

    db.collection("users").document(uid).update({
        "mustChangePassword": False,
        "status": "active",
        "passwordChangedAt": admin_firestore.SERVER_TIMESTAMP,
    })

    # Every session issued before this change — including whoever the temp
    # credential was read aloud to, or shoulder-surfed — stops working
    # immediately rather than at natural token expiry (up to 1 hour later).
    try:
        firebase_auth.revoke_refresh_tokens(uid)
    except Exception:  # noqa: BLE001
        pass  # best-effort: the password itself is already changed either way

    invalidate_account_cache(uid)

    return {"status": "ok", "next": "sign_in_again"}
