"""Shared Firebase auth dependencies.

Extracted from app.py during the master/main integration so the new routers
(evaluation, telemetry, voice_intent, analytics) can require the same real
token verification app.py's original endpoints already used, without a
circular import back into app.py.

Two layers, in dependency order:

  1. verify_user()        - pure Firebase ID token verification. Never
                             touches Firestore. Unchanged in shape since
                             before this file existed.
  2. require_active_user() - the account gate: is this uid provisioned at
                             all (PROFILE_MISSING), disabled
                             (ACCOUNT_DISABLED), or mid-forced-password-
                             change (PASSWORD_CHANGE_REQUIRED)? Patent-
                             readiness audit finding A06: mustChangePassword
                             was set by services/accounts.py on every
                             admin-provisioned account but nothing ever
                             read it — a student could keep the admin-issued
                             temporary password forever. This is that
                             enforcement point.

verify_role() builds on require_active_user() (not verify_user() directly),
so every role-gated endpoint gets the account gate for free without needing
its own changes.
"""

from cachetools import TTLCache
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


# ─────────────── account gate: status + mustChangePassword ───────────────

# Short TTL: long enough that a burst of requests from one page load doesn't
# each cost a Firestore read, short enough that a just-completed first-login
# password change (or a future admin disable/reset action) takes effect
# within seconds rather than indefinitely. invalidate_account_cache() below
# also lets a write-path clear a specific uid immediately rather than
# waiting out the TTL.
_ACCT_CACHE_TTL_S = 15
_acct: "TTLCache[str, dict]" = TTLCache(maxsize=2048, ttl=_ACCT_CACHE_TTL_S)

# The one route allowed to proceed while mustChangePassword is still True —
# it is the only way that flag can ever become False. Must match
# routers/auth_flow.py's route exactly (prefix "/auth" + "/first-login-password",
# mounted under "/api" in app.py).
FIRST_LOGIN_PASSWORD_PATH = "/api/auth/first-login-password"


def invalidate_account_cache(uid: str) -> None:
    """Call after any write to users/{uid} that this gate reads (status,
    mustChangePassword, role) — currently only routers/auth_flow.py, after
    it flips mustChangePassword to False — so the very next request in the
    same TTL window sees the fresh document instead of a stale cached one."""
    _acct.pop(uid, None)


def _fetch_account(uid: str) -> dict:
    if uid in _acct:
        return _acct[uid]
    if db is None:
        raise HTTPException(status_code=503, detail="Persistence unavailable")
    snap = db.collection("users").document(uid).get()
    if not snap.exists:
        # A valid Firebase ID token with no matching users/{uid} document
        # used to auto-provision a Firestore profile on the spot, deciding
        # its role from a string-matched allow-list of demo email
        # addresses. Removed per patent-readiness audit finding A10: every
        # account must come from admin provisioning (services/accounts.py /
        # scripts/create_admin.py / scripts/seed_demo.py) — a missing
        # profile is an error, never an implicit account.
        raise HTTPException(status_code=403, detail="PROFILE_MISSING")
    data = snap.to_dict() or {}
    _acct[uid] = data
    return data


async def require_active_user(request: Request, user: dict = Depends(verify_user)) -> dict:
    """The gate every authenticated route sits behind, except
    POST /api/auth/first-login-password itself — which needs the caller to
    be a real, undisabled account, but must NOT be blocked by the very flag
    it exists to clear.
    """
    uid = user.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid token")

    account = await run_in_threadpool(_fetch_account, uid)

    if account.get("status") == "disabled":
        raise HTTPException(status_code=403, detail="ACCOUNT_DISABLED")

    if account.get("mustChangePassword") and request.url.path != FIRST_LOGIN_PASSWORD_PATH:
        raise HTTPException(status_code=403, detail={"code": "PASSWORD_CHANGE_REQUIRED"})

    return {**user, "role": account.get("role", ""), "status": account.get("status"), "acct": account}


def verify_role(required_role: str):
    async def _check(user: dict = Depends(require_active_user)) -> dict:
        if user.get("role") != required_role:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _check


# ─────────────── per-student / per-session ownership (findings A01, A02) ───────────────


def can_access_student(user: dict, student_id: str) -> bool:
    """True if `user` may view student_id's data: the student themself, an
    admin, or a teacher actively mapped to that student. Checks both the
    dual-written teacher_id/teacherId fields on the student's own document
    (services/accounts.py writes both) and an active enrollments/ record,
    so a co-teacher relationship created only via enrollments still counts.
    """
    if not student_id or db is None:
        return False
    if user.get("uid") == student_id or user.get("role") == "admin":
        return True
    if user.get("role") != "teacher":
        return False
    teacher_uid = user.get("uid")
    snap = db.collection("users").document(student_id).get()
    if snap.exists:
        data = snap.to_dict() or {}
        if data.get("teacher_id") == teacher_uid or data.get("teacherId") == teacher_uid:
            return True
    enr = db.collection("enrollments").document(f"{teacher_uid}_{student_id}").get()
    return enr.exists and bool((enr.to_dict() or {}).get("active"))


def require_self_or_mapped_teacher(student_id: str, user: dict = Depends(require_active_user)) -> dict:
    """Use as Depends(require_self_or_mapped_teacher) on a route with a
    {student_id} path param where the student may see their OWN data, as
    well as their mapped teacher or an admin — e.g. "my evaluation
    history". 404, not 403, for anyone else: the response must never
    confirm a given uid exists to someone not allowed to see it."""
    if not can_access_student(user, student_id):
        raise HTTPException(status_code=404, detail="Student not found")
    return user


def require_teacher_of(student_id: str, user: dict = Depends(require_active_user)) -> dict:
    """Use as Depends(require_teacher_of) on a TEACHER-FACING route with a
    {student_id} path param (e.g. a class-roster analytics view) — unlike
    require_self_or_mapped_teacher, the student themself may NOT use this
    to view their own data through a route meant for a teacher's own
    dashboard. Only the student's mapped teacher, or an admin. 404 for
    everyone else, same reasoning as above.

    Patent-readiness audit finding A01 (Critical): GET /teacher/analytics/
    {student_id} previously checked only role == "teacher" — ANY teacher
    could read ANY student's analytics by guessing or enumerating uids.
    This is the fix.
    """
    if user.get("role") not in ("teacher", "admin"):
        raise HTTPException(status_code=404, detail="Student not found")
    if not can_access_student(user, student_id):
        raise HTTPException(status_code=404, detail="Student not found")
    return user


def assert_session_access(session_id: str, user: dict, *, write: bool = False) -> dict:
    """Load sessions/{session_id} and verify `user` may access it. Read
    access (write=False): the owning student, their mapped teacher, or an
    admin. Write access (write=True, for anything that adds events to a
    session, ends it, or evaluates it): the owning student ONLY — a
    teacher viewing a session must never be able to alter it, and DASE
    evaluation is attributed to the calling uid, so only the owner's call
    means anything.

    Patent-readiness audit finding A02 (Critical): ingest_events,
    end_session, evaluate and get_events all accepted any authenticated
    user and any id — a student could read another child's session
    telemetry, or write events into a session that was never theirs.
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Persistence unavailable")
    snap = db.collection("sessions").document(session_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Session not found")
    data = snap.to_dict() or {}
    owner = data.get("studentId")
    if write:
        if user.get("uid") != owner:
            raise HTTPException(status_code=403, detail="Not your session")
    elif not can_access_student(user, owner or ""):
        raise HTTPException(status_code=404, detail="Session not found")
    return data
