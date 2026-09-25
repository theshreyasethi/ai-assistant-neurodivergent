"""Admin account provisioning — schema v2.

  POST /admin/users       - create one student/teacher account
  POST /admin/users/bulk  - CSV bulk import (role,name,username,grade,teacher_email)

Mounted under /api in app.py (matches every other router added since the
master/main integration), giving /api/admin/users and
/api/admin/users/bulk. Both replace app.py's original POST
/admin/create-user, which is kept there as a thin backward-compatible
alias — see app.py — so the current admin UI (AdminDashboardPage.tsx)
keeps working until it is rebuilt against this API (roadmap task P1-09).
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
