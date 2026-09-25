"""Telemetry ingest — the data layer DASE (Phase 2) reads from.

Event shapes are frozen in DATA_CONTRACT.md v1.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import firestore as admin_firestore

from auth import assert_session_access, require_active_user
from firebase_config import db
from models.schemas import (
    EventBatch,
    QuestionEvent,
    ReadingEvent,
    SessionEnd,
    SessionStart,
    VoiceEvent,
)

router = APIRouter()

_EVENT_TYPES = {"question": QuestionEvent, "reading": ReadingEvent, "voice": VoiceEvent}


def _require_db():
    if db is None:
        raise HTTPException(status_code=503, detail="Persistence unavailable (Firestore not configured)")


def _event_key(event: dict) -> str:
    """Idempotency key: re-sending a batch must not double-count a question.

    A question can legitimately appear twice in one session when the Phase 2.4
    closed loop re-presents it, so `attempts` is part of the key.
    """
    if event.get("type") == "question":
        return f"q_{event['questionId']}_{event.get('attempts', 1)}"
    if event.get("type") == "voice":
        return f"v_{uuid.uuid4().hex}"
    return f"r_{uuid.uuid4().hex}"


@router.post("/sessions")
async def start_session(payload: SessionStart, _user: dict = Depends(require_active_user)):
    _require_db()
    # Authoritative studentId is the calling user — added during the master/main
    # integration once real auth existed to enforce this rather than trust a
    # client-supplied id.
    student_id = _user.get("uid") or payload.studentId
    doc = {
        "studentId": student_id,
        "kind": payload.kind,
        "contentId": payload.contentId,
        "startedAt": admin_firestore.SERVER_TIMESTAMP,
        "endedAt": None,
        "summary": None,
    }
    ref = db.collection("sessions").document()
    ref.set(doc)
    return {"sessionId": ref.id}


@router.post("/events")
async def ingest_events(batch: EventBatch, _user: dict = Depends(require_active_user)):
    """Batch-write events. Validates each against its type schema and skips bad ones
    rather than failing the whole batch — losing one malformed event beats losing a
    student's entire session.

    Also verifies, per event, that its sessionId actually belongs to the
    caller (finding A02) — without this, a student could write events into
    (or read, via GET below) a session that was never theirs. A batch can
    in principle carry events for more than one sessionId, so ownership is
    checked per session, memoized so a batch of many events for the same
    session costs one Firestore read, not one per event."""
    _require_db()
    uid = _user.get("uid", "")

    written, skipped = 0, []
    bulk = db.batch()
    owns_session: dict[str, bool] = {}

    def _owns(session_id: str) -> bool:
        if session_id not in owns_session:
            snap = db.collection("sessions").document(session_id).get()
            owns_session[session_id] = snap.exists and (snap.to_dict() or {}).get("studentId") == uid
        return owns_session[session_id]

    for raw in batch.events:
        model = _EVENT_TYPES.get(raw.get("type"))
        if model is None:
            skipped.append({"reason": "unknown type", "type": raw.get("type")})
            continue
        try:
            event = model(**raw)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"reason": str(exc)[:200]})
            continue

        if not _owns(event.sessionId):
            skipped.append({"reason": "not your session", "sessionId": event.sessionId})
            continue

        data = event.model_dump()
        data["studentId"] = uid
        # serverTs is the trustworthy clock — client `ts` is kept but never used for analysis.
        data["serverTs"] = admin_firestore.SERVER_TIMESTAMP
        ref = (
            db.collection("sessions")
            .document(event.sessionId)
            .collection("events")
            .document(_event_key(data))
        )
        bulk.set(ref, data)
        written += 1

    if written:
        bulk.commit()
    return {"written": written, "skipped": skipped}


@router.patch("/sessions/{session_id}")
async def end_session(session_id: str, payload: SessionEnd, _user: dict = Depends(require_active_user)):
    _require_db()
    # write=True: only the session's own owner may end it — a mapped
    # teacher reading a session (GET below) must never be able to alter it.
    assert_session_access(session_id, _user, write=True)
    db.collection("sessions").document(session_id).update(
        {"summary": payload.summary.model_dump(), "endedAt": admin_firestore.SERVER_TIMESTAMP}
    )
    return {"status": "ok"}


@router.get("/sessions/{session_id}/events")
async def get_events(session_id: str, _user: dict = Depends(require_active_user)):
    """Read back a session. Phase 2 (DASE) and Phase 4 (dashboard) both consume this."""
    _require_db()
    # Read access: the owning student, their mapped teacher, or an admin —
    # unlike end_session above, a teacher legitimately needs to read a
    # mapped student's session for the dashboard, so this is write=False.
    assert_session_access(session_id, _user, write=False)
    events = [
        doc.to_dict()
        for doc in db.collection("sessions")
        .document(session_id)
        .collection("events")
        .order_by("serverTs")
        .stream()
    ]
    return {"sessionId": session_id, "count": len(events), "events": events}
