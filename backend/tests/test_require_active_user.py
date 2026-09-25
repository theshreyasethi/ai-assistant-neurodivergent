"""auth.require_active_user — the account gate.

Covers, by actually calling the real function (not a paraphrase of it):
  - PROFILE_MISSING: valid token, no users/{uid} document
  - ACCOUNT_DISABLED: status == "disabled"
  - PASSWORD_CHANGE_REQUIRED: mustChangePassword == True, on any path other
    than the one exempt path
  - the exempt path (/api/auth/first-login-password) is let through even
    with mustChangePassword == True
  - a normal active account passes through and gets role/status merged
    onto the returned dict
  - the _acct TTL cache: a second call within the TTL does not re-read
    Firestore, and invalidate_account_cache() forces a fresh read

`require_active_user(request, user=Depends(verify_user))` needs a
request-like object with `.url.path` — a bare SimpleNamespace is enough,
since that's the only attribute this function reads from it.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import auth
from fakes import FakeFirestore


def _req(path: str = "/api/some/other/route"):
    return SimpleNamespace(url=SimpleNamespace(path=path))


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setattr(auth, "db", db)
    auth._acct.clear()
    yield db
    auth._acct.clear()


def _check(uid: str, path: str = "/api/some/other/route", email: str = "x@test.com"):
    return asyncio.run(auth.require_active_user(_req(path), user={"uid": uid, "email": email}))


def test_missing_profile_returns_403_profile_missing(fake_db):
    with pytest.raises(HTTPException) as exc_info:
        _check("ghost-uid")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "PROFILE_MISSING"


def test_disabled_account_returns_403_account_disabled(fake_db):
    fake_db.seed("users", "u1", {"role": "teacher", "status": "disabled", "mustChangePassword": False})
    with pytest.raises(HTTPException) as exc_info:
        _check("u1")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "ACCOUNT_DISABLED"


def test_must_change_password_blocks_an_ordinary_route(fake_db):
    fake_db.seed("users", "u2", {"role": "student", "status": "pending_first_login", "mustChangePassword": True})
    with pytest.raises(HTTPException) as exc_info:
        _check("u2", path="/api/analytics/roster")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {"code": "PASSWORD_CHANGE_REQUIRED"}


def test_must_change_password_still_blocks_the_admin_users_route(fake_db):
    """Regression guard: mustChangePassword must block EVERY route except
    the one named exemption — not just a sample of routes."""
    fake_db.seed("users", "u2b", {"role": "admin", "status": "pending_first_login", "mustChangePassword": True})
    with pytest.raises(HTTPException):
        _check("u2b", path="/api/admin/users")


def test_must_change_password_does_not_block_the_first_login_route_itself(fake_db):
    fake_db.seed("users", "u3", {"role": "student", "status": "pending_first_login", "mustChangePassword": True})
    result = _check("u3", path=auth.FIRST_LOGIN_PASSWORD_PATH)
    assert result["uid"] == "u3"
    assert result["role"] == "student"


def test_active_account_passes_through_with_role_and_status_merged(fake_db):
    fake_db.seed("users", "u4", {"role": "teacher", "status": "active", "mustChangePassword": False})
    result = _check("u4")
    assert result["role"] == "teacher"
    assert result["status"] == "active"
    assert result["uid"] == "u4"  # fields from verify_user's output are preserved


def test_account_with_no_must_change_password_field_is_not_blocked(fake_db):
    """Pre-v2 accounts (or any doc missing the field) must not be treated as
    None == True — absence must mean "not required", not an error."""
    fake_db.seed("users", "u5", {"role": "teacher", "status": "active"})
    result = _check("u5")
    assert result["role"] == "teacher"


def test_second_call_within_ttl_does_not_re_read_firestore(fake_db):
    fake_db.seed("users", "u6", {"role": "student", "status": "active", "mustChangePassword": False})
    _check("u6")
    # Mutate the underlying store directly (bypassing the cache) — if the
    # gate is genuinely caching, this change must NOT be visible yet.
    fake_db.store["users"]["u6"]["mustChangePassword"] = True
    result = _check("u6")  # still within the 15s TTL
    assert result["role"] == "student"  # would have raised if it re-read


def test_invalidate_account_cache_forces_a_fresh_read(fake_db):
    fake_db.seed("users", "u7", {"role": "student", "status": "active", "mustChangePassword": False})
    _check("u7")
    fake_db.store["users"]["u7"]["mustChangePassword"] = True
    auth.invalidate_account_cache("u7")
    with pytest.raises(HTTPException) as exc_info:
        _check("u7")
    assert exc_info.value.detail == {"code": "PASSWORD_CHANGE_REQUIRED"}
