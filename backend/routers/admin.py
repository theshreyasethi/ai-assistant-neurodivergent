"""Admin account provisioning and lifecycle — schema v2.

  POST  /admin/users                         - create one student/teacher account
  POST  /admin/users/bulk                    - CSV bulk import
  PATCH /admin/students/{student_id}/teacher - reassign a student to a different teacher
  POST  /admin/users/{uid}/disable           - disable an account
  POST  /admin/users/{uid}/enable            - re-enable an account
  POST  /admin/users/{uid}/reset-password    - issue a fresh temporary password

Mounted under /api in app.py, giving /api/admin/users etc. POST
/admin/users replaces app.py's original POST /admin/create-user, which is
kept there as a thin backward-compatible alias — see app.py — so the
current admin UI (AdminDashboardPage.tsx) keeps working until it is
rebuilt against this API (roadmap task P1-09, done alongside these
lifecycle routes).
"""

import csv
import io
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from auth import verify_role
from services import accounts

router = APIRouter(prefix="/admin")

# A single, named dependency instance — NOT `Depends(verify_role("admin"))`
# inlined per-route — so tests can override it with
# app.dependency_overrides[require_admin]. FastAPI matches overrides by the
# exact callable object, and verify_role("admin") builds a new closure every
# time it's called, so two separate calls are never `==`.
require_admin = verify_role("admin")


class NewUserRequest(BaseModel):
    role: Literal["student", "teacher"]
    displayName: str = Field(min_length=1, max_length=80)
    username: str = Field(pattern=r"^[a-z0-9._-]{3,32}$")
    gradeLevel: Optional[str] = None
    teacherId: Optional[str] = None
    # Falls back to f"{username}@{SCHOOL_LOGIN_DOMAIN}" when omitted — most
    # students don't have a real email address.
    email: Optional[str] = None


def _account_error_to_http(exc: accounts.AccountError) -> HTTPException:
    if isinstance(exc, accounts.AccountNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, accounts.TeacherInvalid):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, accounts.UsernameTaken):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, accounts.ValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.post("/users")
async def create_user(body: NewUserRequest, admin: dict = Depends(require_admin)):
    try:
        return accounts.create_user(
            role=body.role,
            display_name=body.displayName,
            username=body.username,
            grade_level=body.gradeLevel,
            teacher_id=body.teacherId,
            email=body.email,
            created_by=admin.get("uid", ""),
        )
    except accounts.AccountError as exc:
        raise _account_error_to_http(exc)


@router.post("/users/bulk")
async def create_users_bulk(file: UploadFile = File(...), admin: dict = Depends(require_admin)):
    raw = (await file.read()).decode("utf-8-sig")  # -sig: tolerate an Excel-exported BOM
    reader = csv.DictReader(io.StringIO(raw))
    required = {"role", "name", "username"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=422,
            detail="CSV must have a header row with at least: role,name,username,grade,teacher_email",
        )
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=422, detail="CSV has no data rows")

    results = accounts.create_users_bulk(rows, created_by=admin.get("uid", ""))
    return {
        "total": len(results),
        "created": sum(1 for r in results if r["status"] == "created"),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }


class ReassignTeacherRequest(BaseModel):
    teacherId: str = Field(min_length=1)


@router.patch("/students/{student_id}/teacher")
async def reassign_student_teacher(
    student_id: str, body: ReassignTeacherRequest, admin: dict = Depends(require_admin),
):
    try:
        return accounts.reassign_teacher(student_id, body.teacherId, actor=admin.get("uid", ""))
    except accounts.AccountError as exc:
        raise _account_error_to_http(exc)


@router.post("/users/{uid}/disable")
async def disable_user(uid: str, admin: dict = Depends(require_admin)):
    try:
        return accounts.set_account_status(uid, "disabled", actor=admin.get("uid", ""))
    except accounts.AccountError as exc:
        raise _account_error_to_http(exc)


@router.post("/users/{uid}/enable")
async def enable_user(uid: str, admin: dict = Depends(require_admin)):
    try:
        return accounts.set_account_status(uid, "active", actor=admin.get("uid", ""))
    except accounts.AccountError as exc:
        raise _account_error_to_http(exc)


@router.post("/users/{uid}/reset-password")
async def reset_user_password(uid: str, admin: dict = Depends(require_admin)):
    """Returned ONCE, same as account creation — never stored in plaintext.
    See services.accounts.admin_reset_password for what this does to the
    account's mustChangePassword/status flags and existing sessions."""
    try:
        return accounts.admin_reset_password(uid, actor=admin.get("uid", ""))
    except accounts.AccountError as exc:
        raise _account_error_to_http(exc)
