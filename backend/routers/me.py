"""Self-service profile updates — GET /me, PATCH /me (mounted at /api/me).

Patent-readiness audit finding A08: Settings only ever edited accessibility
prefs and the disability profile; there was no account page at all for any
role, so nobody — student, teacher or admin — could change their own
display name or username once an admin created their account.

Password changes are NOT handled here. A voluntary, already-signed-in
password change (frontend/src/pages/AccountPage.tsx) uses Firebase's own
client-side reauthenticateWithCredential + updatePassword, which is the
standard, idiomatic way to gate a password change on a recent login with
the Firebase Auth SDK, and needs no backend route at all. Contrast
routers/auth_flow.py's FORCED first-login change, which has different
requirements entirely — a server-generated temporary password, revoking
every existing session — and is deliberately server-enforced instead.
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import auth as firebase_auth
from pydantic import BaseModel, Field

from auth import invalidate_account_cache, require_active_user
from config import SCHOOL_LOGIN_DOMAIN
from firebase_config import db

router = APIRouter(prefix="/me")

_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")


@router.get("")
async def get_me(user: dict = Depends(require_active_user)):
    acct = user.get("acct") or {}
    return {
        "uid": user.get("uid"),
        "email": acct.get("email"),
        "username": acct.get("username"),
        "displayName": acct.get("displayName"),
        "role": acct.get("role"),
        "gradeLevel": acct.get("gradeLevel") or acct.get("grade_level"),
        "teacherId": acct.get("teacherId") or acct.get("teacher_id"),
    }


class UpdateMeRequest(BaseModel):
    displayName: Optional[str] = Field(default=None, min_length=1, max_length=80)
    username: Optional[str] = Field(default=None, pattern=r"^[a-z0-9._-]{3,32}$")


@router.patch("")
async def update_me(body: UpdateMeRequest, user: dict = Depends(require_active_user)):
    uid = user.get("uid", "")
    if db is None:
        raise HTTPException(status_code=503, detail="Persistence unavailable")
    if body.displayName is None and body.username is None:
        raise HTTPException(status_code=422, detail="Nothing to update")

    updates: dict = {}

    if body.displayName is not None:
        new_name = body.displayName.strip()
        if not new_name:
            raise HTTPException(status_code=422, detail="displayName cannot be blank")
        try:
            firebase_auth.update_user(uid, display_name=new_name)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Could not update display name: {exc}")
        updates["displayName"] = new_name

    if body.username is not None:
        new_username = body.username.strip().lower()
        acct = user.get("acct") or {}
        current_email = acct.get("email", "")
        # Only roll the login email forward when it was the synthetic
        # username@SCHOOL_LOGIN_DOMAIN form in the first place (most
        # students — see services/accounts.py). A real external email
        # (a teacher/admin created with one) is left alone; changing a
        # login address someone actually reads mail at is a bigger,
        # separate action than renaming a display handle.
        if current_email.endswith(f"@{SCHOOL_LOGIN_DOMAIN}"):
            new_email = f"{new_username}@{SCHOOL_LOGIN_DOMAIN}"
            if new_email != current_email:
                try:
                    firebase_auth.update_user(uid, email=new_email)
                except firebase_auth.EmailAlreadyExistsError:
                    raise HTTPException(status_code=409, detail="That username is already in use")
                except Exception as exc:  # noqa: BLE001
                    raise HTTPException(status_code=500, detail=f"Could not update username: {exc}")
                updates["email"] = new_email
        updates["username"] = new_username

    db.collection("users").document(uid).update(updates)
    invalidate_account_cache(uid)

    return {"status": "ok", **updates}
