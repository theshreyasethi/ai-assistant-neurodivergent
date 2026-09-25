"""auth.verify_role — no more _DEMO_ROLE_MAP auto-provisioning (finding A10).

`_check` is `async def _check(user: dict = Depends(verify_user)) -> dict`.
`Depends(...)` is just an unused default value outside of a real FastAPI
request — calling `_check(user={...})` directly, bypassing the dependency
machinery entirely, is the standard way to unit-test a FastAPI dependency
function in isolation, and is exactly what's done below.
"""

import asyncio

import pytest
from fastapi import HTTPException

import auth
from fakes import FakeFirestore


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setattr(auth, "db", db)
    return db


def test_demo_role_map_no_longer_exists():
    assert not hasattr(auth, "_DEMO_ROLE_MAP")


def test_missing_profile_returns_403_profile_missing_and_creates_nothing(fake_db):
    check = auth.verify_role("teacher")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(check(user={"uid": "ghost-uid", "email": "ghost@test.com"}))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "PROFILE_MISSING"
    # The old behaviour silently wrote a users/{uid} document here. The new
    # behaviour must not — a missing profile is an error, not an implicit account.
    assert fake_db.all_docs("users") == {}


def test_known_demo_email_no_longer_grants_a_role(fake_db):
    """Before this change, admin@test.com / teacher{1,2,3}@test.com got
    auto-provisioned into the matching role purely by string match on email
    — with no Firestore document and no real admin action involved."""
    check = auth.verify_role("admin")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(check(user={"uid": "some-uid", "email": "admin@test.com"}))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "PROFILE_MISSING"


def test_role_mismatch_returns_403_insufficient_permissions(fake_db):
    fake_db.seed("users", "u1", {"role": "student"})
    check = auth.verify_role("teacher")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(check(user={"uid": "u1"}))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Insufficient permissions"


def test_role_match_succeeds_and_annotates_user_with_role(fake_db):
    fake_db.seed("users", "u2", {"role": "teacher"})
    check = auth.verify_role("teacher")
    result = asyncio.run(check(user={"uid": "u2"}))
    assert result["role"] == "teacher"
