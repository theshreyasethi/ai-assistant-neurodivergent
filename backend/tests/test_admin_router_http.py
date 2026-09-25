"""HTTP-layer test of POST /api/admin/users and /api/admin/users/bulk.

Proves the 422/409/200 status codes actually reach the wire, not just that
the underlying Python function raises the right exception class (see
test_admin_provisioning.py for that). Mounts ONLY routers.admin on a
throwaway FastAPI app — not the real app.py — so this doesn't need to
import app.py's much heavier module-level setup (LLM clients, the RAG
ingestion pipeline, etc.), none of which this test exercises.
"""

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import admin as admin_router
from services import accounts
from fakes import FakeAuth, FakeFirestore


def _fake_admin_user():
    return {"uid": "admin-1", "role": "admin"}


@pytest.fixture
def client(monkeypatch):
    fake_db = FakeFirestore()
    fake_auth = FakeAuth()
    monkeypatch.setattr(accounts, "db", fake_db)
    monkeypatch.setattr(accounts, "firebase_auth", fake_auth)

    app = FastAPI()
    app.include_router(admin_router.router, prefix="/api")
    app.dependency_overrides[admin_router.require_admin] = _fake_admin_user

    with TestClient(app) as test_client:
        test_client.fake_db = fake_db  # type: ignore[attr-defined]
        yield test_client


def _seed_teacher(client, uid="t1", **extra):
    client.fake_db.seed("users", uid, {"role": "teacher", "status": "active", **extra})
    return uid


# ─────────────── POST /api/admin/users ───────────────


def test_create_student_without_teacher_returns_422(client):
    resp = client.post("/api/admin/users", json={
        "role": "student", "displayName": "Kid", "username": "kid1",
    })
    assert resp.status_code == 422


def test_create_student_with_unknown_teacher_id_returns_422(client):
    resp = client.post("/api/admin/users", json={
        "role": "student", "displayName": "Kid", "username": "kid1", "teacherId": "ghost",
    })
    assert resp.status_code == 422


def test_create_student_with_disabled_teacher_returns_422(client):
    _seed_teacher(client, "t1", status="disabled")
    resp = client.post("/api/admin/users", json={
        "role": "student", "displayName": "Kid", "username": "kid1", "teacherId": "t1",
    })
    assert resp.status_code == 422


def test_create_student_with_active_teacher_succeeds(client):
    _seed_teacher(client, "t1")
    resp = client.post("/api/admin/users", json={
        "role": "student", "displayName": "Kid One", "username": "kid1",
        "teacherId": "t1", "gradeLevel": "5",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending_first_login"
    assert "temporaryPassword" in body and len(body["temporaryPassword"]) == 14

    stored = client.fake_db.get_doc("users", body["uid"])
    assert stored["mustChangePassword"] is True
    assert len(client.fake_db.all_docs("audit_log")) == 1


def test_duplicate_username_returns_409(client):
    resp1 = client.post("/api/admin/users", json={
        "role": "teacher", "displayName": "A", "username": "dupe",
    })
    assert resp1.status_code == 200
    resp2 = client.post("/api/admin/users", json={
        "role": "teacher", "displayName": "B", "username": "dupe",
    })
    assert resp2.status_code == 409


def test_malformed_username_returns_422_before_touching_the_backend(client):
    # Pydantic-level rejection (pattern mismatch) — never calls accounts.create_user.
    resp = client.post("/api/admin/users", json={
        "role": "teacher", "displayName": "A", "username": "no spaces allowed",
    })
    assert resp.status_code == 422
    assert client.fake_db.all_docs("users") == {}


def test_unauthenticated_caller_cannot_create_users():
    """Without the dependency override, the real require_admin (verify_role)
    is in effect and rejects a request carrying no bearer token at all."""
    app = FastAPI()
    app.include_router(admin_router.router, prefix="/api")
    with TestClient(app) as unauthed_client:
        resp = unauthed_client.post("/api/admin/users", json={
            "role": "teacher", "displayName": "A", "username": "sneaky",
        })
    assert resp.status_code == 401


# ─────────────── POST /api/admin/users/bulk ───────────────


def test_bulk_csv_creates_rows_and_reports_totals(client):
    _seed_teacher(client, "t1", email="teach@school.org")
    csv_body = (
        "role,name,username,grade,teacher_email\n"
        "student,Good Kid,goodkid,3,teach@school.org\n"
        "student,Orphan Kid,orphankid,3,nobody@school.org\n"
    )
    resp = client.post(
        "/api/admin/users/bulk",
        files={"file": ("roster.csv", io.BytesIO(csv_body.encode()), "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["created"] == 1
    assert body["failed"] == 1
    assert body["results"][1]["status"] == "error"


def test_bulk_csv_missing_required_headers_returns_422(client):
    csv_body = "email,x\nsomething,else\n"
    resp = client.post(
        "/api/admin/users/bulk",
        files={"file": ("roster.csv", io.BytesIO(csv_body.encode()), "text/csv")},
    )
    assert resp.status_code == 422
