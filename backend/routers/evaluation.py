"""DASE evaluation endpoints.

  POST /api/classify              - classify one wrong answer, drive the closed loop
  POST /api/evaluate              - compute a DASE profile for a session
  GET  /api/evaluation/{student}  - historical DASE profiles
  GET  /api/evaluation/{student}/errors - error-cause breakdown
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import firestore as admin_firestore
from pydantic import BaseModel

from auth import assert_session_access, require_active_user, require_self_or_mapped_teacher
from firebase_config import db
from services import baselines, dase_engine

router = APIRouter()

# Sessions scanned for TASK_COMP (completed ÷ started) and for the
# cross-session CONSIST accuracy-stability input — a window, not the
# student's whole history, so a score reflects recent behaviour.
RECENT_SESSIONS_WINDOW = 20


class ClassifyRequest(BaseModel):
    timeMs: int
    priorTimesMs: List[float] = []
    focusRatio: Optional[float] = None
    focusSamples: int = 0
    answerChanges: int = 0
    timeToFirstInteractionMs: Optional[int] = None
    reRead: bool = False
    timedOut: bool = False
    hasSimplerVariant: bool = False


@router.post("/classify")
async def classify(req: ClassifyRequest, _user: dict = Depends(require_active_user)):
    """Classify a single wrong answer and say whether to re-present it.

    Called synchronously by the quiz on wrong answers only, so the closed loop can
    act immediately. Deliberately stateless — the caller passes the student's own
    prior response times, which it already has in memory for the current session.
    """
    result = dase_engine.classify_error(
        time_ms=req.timeMs,
        prior_times_ms=req.priorTimesMs,
        focus_ratio=req.focusRatio,
        focus_samples=req.focusSamples,
        answer_changes=req.answerChanges,
        time_to_first_interaction_ms=req.timeToFirstInteractionMs,
        re_read=req.reRead,
        timed_out=req.timedOut,
    )
    return {
        "classification": result.to_dict(),
        "shouldRepresent": bool(
            req.hasSimplerVariant and dase_engine.should_represent(result)
        ),
    }


def _require_db():
    if db is None:
        raise HTTPException(status_code=503, detail="Persistence unavailable")


def _load_session_events(session_id: str):
    docs = (
        db.collection("sessions")
        .document(session_id)
        .collection("events")
        .order_by("serverTs")
        .stream()
    )
    events = [d.to_dict() for d in docs]
    return (
        [e for e in events if e.get("type") == "question"],
        [e for e in events if e.get("type") == "reading"],
        [e for e in events if e.get("type") == "voice"],
    )


def _scoring_profile(user: dict) -> str:
    """The profile /evaluate actually scores against is derived from the
    student's own stored profile, never the request body (roadmap P3-08) —
    a client sending `profile: "default"` must not be able to dodge the
    disability-weighted scoring it would otherwise get. `acct` is the
    users/{uid} document require_active_user already fetched, so this costs
    no extra read."""
    stored_profile = (user.get("acct") or {}).get("profile") or {}
    primary = stored_profile.get("primary")
    if primary:
        return primary
    disabilities = stored_profile.get("disabilities") or []
    return disabilities[0] if disabilities else "default"


def _load_override_weights(student_id: str) -> tuple:
    """A teacher's weight override (routers/overrides.py), if one is active
    for this student. Returns (weights_or_None, override_id_or_None)."""
    if db is None:
        return None, None
    doc = db.collection("dase_overrides").document(student_id).get()
    if not doc.exists:
        return None, None
    weights = (doc.to_dict() or {}).get("weights")
    return (weights, student_id) if weights else (None, None)


def _recent_sessions(student_id: str, limit: int = RECENT_SESSIONS_WINDOW) -> List[dict]:
    """The student's last N session documents, abandoned ones included — a
    session that was started (it has a document) but never ended (summary is
    still None) is exactly what TASK_COMP needs to count as "started, not
    completed"."""
    if db is None:
        return []
    docs = (
        db.collection("sessions")
        .where(filter=admin_firestore.FieldFilter("studentId", "==", student_id))
        .limit(limit)
        .stream()
    )
    return [d.to_dict() for d in docs]


class EvaluateRequest(BaseModel):
    sessionId: str
    studentId: str
    # DEPRECATED, IGNORED: the scoring profile is now always derived
    # server-side from the student's own stored profile (roadmap P3-08) —
    # kept only so existing callers (frontend/src/services/telemetry.ts)
    # don't fail client-side validation while they still send it.
    profile: str = "default"
    persist: bool = True


@router.post("/evaluate")
async def evaluate(req: EvaluateRequest, _user: dict = Depends(require_active_user)):
    _require_db()
    # Authoritative studentId is the CALLING user, never the client-sent value —
    # a student must not be able to evaluate a session as someone else. Added
    # during the master/main integration once real auth existed to enforce it.
    student_id = _user.get("uid") or req.studentId

    # The result above stops a student naming a DIFFERENT studentId; it does
    # NOT stop them naming a DIFFERENT sessionId — without this, any
    # authenticated user could read another student's session events by
    # evaluating that session and inspecting the returned parameters/error
    # breakdown (finding A02). write=True: evaluation is attributed to the
    # caller, so only the session's own owner may trigger it — a mapped
    # teacher reading it is a separate, read-only concern (GET /evaluation/
    # {student_id} below), not this endpoint.
    assert_session_access(req.sessionId, _user, write=True)

    questions, readings, voices = _load_session_events(req.sessionId)
    if not questions and not readings and not voices:
        raise HTTPException(status_code=404, detail="No events found for this session")

    profile = _scoring_profile(_user)
    override_weights, override_id = _load_override_weights(student_id)
    sessions = _recent_sessions(student_id)
    baseline = baselines.baseline_ms(db, student_id)

    parameters = dase_engine.compute_parameters(
        questions, readings, sessions, voices, baseline_ms=baseline,
    )
    result = dase_engine.compute_dase(parameters, profile, override_weights=override_weights)
    result["errorBreakdown"] = dase_engine.error_breakdown(questions)
    result["sessionId"] = req.sessionId
    result["studentId"] = student_id
    # configVersion/configSha256 (roadmap P3-10): so a score can be
    # reproduced later from (events, configSha256) even after the weights
    # file has since changed.
    result["configVersion"] = dase_engine.config_version()
    result["configSha256"] = dase_engine.config_sha256()
    if override_id:
        result["overrideId"] = override_id

    baselines.record_correct_times(db, student_id, questions)

    if req.persist:
        db.collection("evaluations").add({**result, "computedAt": admin_firestore.SERVER_TIMESTAMP})

    return result


@router.get("/evaluation/{student_id}")
async def get_evaluations(student_id: str, limit: int = 20, _user: dict = Depends(require_self_or_mapped_teacher)):
    _require_db()
    docs = (
        db.collection("evaluations")
        .where(filter=admin_firestore.FieldFilter("studentId", "==", student_id))
        .limit(limit)
        .stream()
    )
    evaluations = [d.to_dict() for d in docs]
    # Sort in Python rather than with order_by: a composite where+order_by query
    # needs a Firestore index that has to be created by hand, and a missing index
    # fails at runtime rather than at deploy. Fine at this scale.
    evaluations.sort(key=lambda e: e.get("computedAt") or 0, reverse=True)
    return {"studentId": student_id, "count": len(evaluations), "evaluations": evaluations}


@router.get("/evaluation/{student_id}/errors")
async def get_error_breakdown(student_id: str, limit: int = 50, _user: dict = Depends(require_self_or_mapped_teacher)):
    """Aggregate error causes across a student's recent sessions.

    One collection-group query across every sessions/*/events subcollection,
    filtered by studentId + type, instead of one query PER session to
    discover its events (previously: one read to list sessions, then N more
    reads, one per session, to fetch that session's own events). Every event
    already carries its own studentId (routers/telemetry.py's ingest stamps
    it), so the session list is never even needed. `sessionsScanned` is the
    real count of distinct sessions the matched events came from, not
    whatever `limit` happened to be passed in (roadmap P3-12 — previously
    always reported `limit` itself, regardless of how many sessions actually
    existed).
    """
    _require_db()
    docs = (
        db.collection_group("events")
        .where(filter=admin_firestore.FieldFilter("studentId", "==", student_id))
        .where(filter=admin_firestore.FieldFilter("type", "==", "question"))
        .limit(limit)
        .stream()
    )
    all_questions = [d.to_dict() for d in docs]
    sessions_scanned = len({q.get("sessionId") for q in all_questions if q.get("sessionId")})

    return {
        "studentId": student_id,
        "sessionsScanned": sessions_scanned,
        **dase_engine.error_breakdown(all_questions),
    }


@router.get("/dase/profiles")
async def list_profiles(_user: dict = Depends(require_active_user)):
    """Weight profiles and their rationale — the teacher dashboard renders these,
    and they are what a teacher edits when overriding weights."""
    config = dase_engine.load_config()
    return {
        "profiles": {
            name: {"rationale": entry["rationale"], "weights": entry["weights"]}
            for name, entry in config["profiles"].items()
        },
        "parameters": config["_parameters"],
    }
