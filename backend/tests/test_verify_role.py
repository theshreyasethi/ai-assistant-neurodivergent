"""auth.verify_role — role comparison only.

As of the require_active_user refactor (P1-05), verify_role no longer does
its own Firestore lookup — it trusts the `role` already resolved onto the
user dict by require_active_user (which it depends on). See
test_require_active_user.py for PROFILE_MISSING / ACCOUNT_DISABLED /
PASSWORD_CHANGE_REQUIRED coverage, and test_admin_router_http.py /
test_first_login_password.py for the same logic exercised through real
HTTP requests.

`_check` is `async def _check(user: dict = Depends(require_active_user))`.
`Depends(...)` is just an unused default value outside of a real FastAPI
request — calling `_check(user={...})` directly, bypassing the dependency
machinery entirely, is the standard way to unit-test a FastAPI dependency
function in isolation, and is exactly what's done below.
"""

import asyncio

import pytest
from fastapi import HTTPException

import auth


def test_demo_role_map_no_longer_exists():
    assert not hasattr(auth, "_DEMO_ROLE_MAP")


def test_role_mismatch_returns_403_insufficient_permissions():
    check = auth.verify_role("teacher")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(check(user={"uid": "u1", "role": "student"}))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Insufficient permissions"


def test_missing_role_returns_403_insufficient_permissions():
    check = auth.verify_role("teacher")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(check(user={"uid": "u1"}))  # no "role" key at all
    assert exc_info.value.status_code == 403


def test_role_match_succeeds_and_returns_the_user_dict():
    check = auth.verify_role("teacher")
    result = asyncio.run(check(user={"uid": "u2", "role": "teacher"}))
    assert result["role"] == "teacher"
    assert result["uid"] == "u2"
