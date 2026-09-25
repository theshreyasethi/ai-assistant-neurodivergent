"""Minimal in-memory doubles for the Firestore and Firebase Auth Admin SDK
surfaces `services/accounts.py` and `auth.py` actually use.

Deliberately NOT a real Firestore/Auth emulator: these tests are unit tests
of our own validation and bookkeeping logic (teacher-must-be-active,
mustChangePassword gets set, an audit_log row gets written, ...), not of
Firebase itself. Keeping them in-process makes them fast, deterministic,
and safe to run with zero risk of ever touching a real Firebase project —
tests monkeypatch `services.accounts.db` / `services.accounts.firebase_auth`
(and `auth.db`) to instances of these classes, so the real SDKs are never
called even though this repo's backend/.env does point at a real project
for normal (non-test) use.

(See tests/firestore-rules/ at the repo root for the complementary,
real-emulator-backed test of firestore.rules itself — a different layer,
deliberately tested a different way.)
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple


class FakeDocSnapshot:
    def __init__(self, doc_id: str, data: Optional[dict]):
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Optional[dict]:
        return dict(self._data) if self._data is not None else None


class FakeDocRef:
    def __init__(self, db: "FakeFirestore", collection: str, doc_id: str):
        self._db = db
        self._store = db.store
        self._collection = collection
        self._doc_id = doc_id

    def get(self) -> FakeDocSnapshot:
        data = self._store.setdefault(self._collection, {}).get(self._doc_id)
        return FakeDocSnapshot(self._doc_id, data)

    def set(self, data: dict, merge: bool = False) -> None:
        coll = self._store.setdefault(self._collection, {})
        if merge and self._doc_id in coll:
            coll[self._doc_id] = {**coll[self._doc_id], **data}
        else:
            coll[self._doc_id] = dict(data)

    def update(self, data: dict) -> None:
        """Firestore's partial-update — distinct from .set(): merges into an
        EXISTING document and raises if it doesn't exist, rather than
        silently creating one (that's what .set() is for)."""
        coll = self._store.setdefault(self._collection, {})
        if self._doc_id not in coll:
            raise KeyError(f"No document to update at {self._collection}/{self._doc_id}")
        coll[self._doc_id] = {**coll[self._doc_id], **data}

    def collection(self, name: str) -> "_FakeCollection":
        """A subcollection (e.g. sessions/{id}/events) — modelled as a
        flat collection keyed by the composite path "parent/doc/name", so
        it can't collide with a genuine top-level collection of the same
        name and needs no tree structure."""
        return _FakeCollection(self._db, f"{self._collection}/{self._doc_id}/{name}")


class FakeQuery:
    def __init__(self, store: Dict[str, Dict[str, dict]], collection: str, filters: List[Tuple[str, Any]]):
        self._store = store
        self._collection = collection
        self._filters = filters

    def where(self, field: Optional[str] = None, op: Optional[str] = None, value: Any = None, *,
              filter: Any = None) -> "FakeQuery":
        # Two call shapes both appear in this codebase: the older positional
        # .where(field, op, value), and the modern .where(filter=FieldFilter
        # (field, op, value)) used by routers/evaluation.py and
        # routers/analytics.py. Both reduce to the same (field, op, value).
        if filter is not None:
            field, op, value = filter.field_path, filter.op_string, filter.value
        assert op == "==", f"FakeQuery only supports '==', got {op!r}"
        return FakeQuery(self._store, self._collection, self._filters + [(field, value)])

    def limit(self, _n: int) -> "FakeQuery":
        return self  # not bothering to truncate — these tests use tiny fixtures

    def order_by(self, _field: str) -> "FakeQuery":
        return self  # ordering isn't asserted by any current test; keep results as-is

    def stream(self) -> Iterator[FakeDocSnapshot]:
        for doc_id, data in self._store.get(self._collection, {}).items():
            if all(data.get(field) == value for field, value in self._filters):
                yield FakeDocSnapshot(doc_id, data)


class _FakeCollection:
    def __init__(self, db: "FakeFirestore", name: str):
        self._db = db
        self._name = name

    def document(self, doc_id: Optional[str] = None) -> FakeDocRef:
        if doc_id is None:
            self._db._auto_id += 1
            doc_id = f"auto{self._db._auto_id}"
        return FakeDocRef(self._db, self._name, doc_id)

    def where(self, field: Optional[str] = None, op: Optional[str] = None, value: Any = None, *,
              filter: Any = None) -> FakeQuery:
        return FakeQuery(self._db.store, self._name, []).where(field, op, value, filter=filter)

    def order_by(self, _field: str) -> FakeQuery:
        return FakeQuery(self._db.store, self._name, [])

    def stream(self) -> Iterator[FakeDocSnapshot]:
        for doc_id, data in self._db.store.get(self._name, {}).items():
            yield FakeDocSnapshot(doc_id, data)


class FakeBatch:
    def __init__(self) -> None:
        self._ops: List[Tuple[FakeDocRef, dict]] = []

    def set(self, ref: FakeDocRef, data: dict) -> None:
        self._ops.append((ref, data))

    def commit(self) -> None:
        for ref, data in self._ops:
            ref.set(data)


class FakeFirestore:
    """Implements exactly the surface services/accounts.py and auth.py use:
    .collection(name).document(id).get()/.set(), .collection(name).where(...)
    .stream(), .batch()."""

    def __init__(self) -> None:
        self.store: Dict[str, Dict[str, dict]] = {}
        self._auto_id = 0

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self, name)

    def batch(self) -> FakeBatch:
        return FakeBatch()

    # test-only helpers, not part of the real Firestore client API
    def seed(self, collection: str, doc_id: str, data: dict) -> None:
        self.store.setdefault(collection, {})[doc_id] = dict(data)

    def get_doc(self, collection: str, doc_id: str) -> Optional[dict]:
        return self.store.get(collection, {}).get(doc_id)

    def all_docs(self, collection: str) -> Dict[str, dict]:
        return dict(self.store.get(collection, {}))


class FakeEmailAlreadyExistsError(Exception):
    pass


class FakeAuthRecord:
    def __init__(self, uid: str):
        self.uid = uid


class FakeAuth:
    """Stands in for `firebase_admin.auth` — only the handful of names
    services/accounts.py and scripts/create_admin.py reference."""

    EmailAlreadyExistsError = FakeEmailAlreadyExistsError

    class UserNotFoundError(Exception):
        pass

    def __init__(self) -> None:
        self._by_email: Dict[str, FakeAuthRecord] = {}
        self._next = 0
        self.deleted: List[str] = []
        # Records of what update_user() / revoke_refresh_tokens() were
        # called with, for tests that need to assert the Admin SDK was
        # actually invoked (e.g. routers/auth_flow.py's first-login change).
        self.updated_passwords: Dict[str, str] = {}
        self.revoked: List[str] = []

    def create_user(self, *, email: str, password: str, display_name: Optional[str] = None) -> FakeAuthRecord:
        if email in self._by_email:
            raise self.EmailAlreadyExistsError(email)
        self._next += 1
        record = FakeAuthRecord(f"uid{self._next}")
        self._by_email[email] = record
        return record

    def get_user_by_email(self, email: str) -> FakeAuthRecord:
        if email not in self._by_email:
            raise self.UserNotFoundError(email)
        return self._by_email[email]

    def update_user(self, uid: str, *, password: Optional[str] = None, **_kwargs: Any) -> None:
        if password is not None:
            self.updated_passwords[uid] = password

    def revoke_refresh_tokens(self, uid: str) -> None:
        self.revoked.append(uid)

    def delete_user(self, uid: str) -> None:
        self.deleted.append(uid)
        self._by_email = {e: r for e, r in self._by_email.items() if r.uid != uid}
