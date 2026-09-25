"""Shared Firebase auth dependencies.

Extracted from app.py during the master/main integration so the new routers
(evaluation, telemetry, voice_intent, analytics) can require the same real
token verification app.py's original endpoints already used, without a
circular import back into app.py.
"""

from fastapi import Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from firebase_config import db, verify_firebase_token


async def verify_user(request: Request) -> dict:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token")
    token = header[7:]
    try:
        decoded = await run_in_threadpool(verify_firebase_token, token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    # Firebase tokens use 'sub' for UID; normalise to 'uid' for the rest of the app
    if "uid" not in decoded:
        decoded = {**decoded, "uid": decoded.get("sub", "")}
    return decoded


def verify_role(required_role: str):
    async def _check(user: dict = Depends(verify_user)) -> dict:
        uid = user.get("uid")
        if not uid:
            raise HTTPException(status_code=401, detail="Invalid token")
        if db is None:
            raise HTTPException(status_code=503, detail="Persistence unavailable")
        try:
            user_doc = db.collection("users").document(uid).get()
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to verify role")
        if not user_doc.exists:
            # A valid Firebase ID token with no matching users/{uid} document
            # used to auto-provision a Firestore profile on the spot — a
            # string-matched allow-list (_DEMO_ROLE_MAP) decided whether that
            # profile silently became an admin, a teacher, or (for anyone
            # else) a student. Removed per patent-readiness audit finding
            # A10: every account must come from admin provisioning
            # (services/accounts.py / scripts/create_admin.py /
            # scripts/seed_demo.py) — a missing profile is an error, never an
            # implicit account.
            raise HTTPException(status_code=403, detail="PROFILE_MISSING")
        role = user_doc.to_dict().get("role", "")
        if role != required_role:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        user["role"] = role
        return user
    return _check
