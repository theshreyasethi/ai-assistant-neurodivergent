"""Teacher DASE weight overrides — PUT /api/teachers/students/{id}/dase-weights.

Roadmap P3-08: a teacher who knows a student better than the literature-
informed default profile does may need to adjust the weighting (e.g. a
student the teacher believes has more test anxiety than ADHD-related
distraction). This is a deliberate escape hatch from the shared config, so
every use of it is validated against known parameters, requires a written
reason, and is logged to audit_log the same way every other admin/teacher
action in this codebase is (services/accounts.py's exact pattern).

The override is read back and applied in routers/evaluation.py — this file
only writes it.
"""

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import firestore as admin_firestore
from pydantic import BaseModel, Field, field_validator

from auth import require_teacher_of
from firebase_config import db
from services import dase_engine

router = APIRouter()


class WeightOverrideRequest(BaseModel):
    weights: Dict[str, float]
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("weights")
    @classmethod
    def _validate_weights(cls, value: Dict[str, float]) -> Dict[str, float]:
        if not value:
            raise ValueError("weights must not be empty")
        known = set(dase_engine.load_config()["_parameters"])
        for name, weight in value.items():
            if name not in known:
                raise ValueError(f"Unknown DASE parameter: {name}")
            if weight < 0:
                raise ValueError(f"Weight for {name} must be non-negative")
        return value


@router.put("/teachers/students/{student_id}/dase-weights")
async def set_weight_override(
    student_id: str, body: WeightOverrideRequest, user: dict = Depends(require_teacher_of),
):
    """Only the student's own mapped teacher (or an admin) may set this —
    require_teacher_of 404s for anyone else, same as every other
    teacher-facing per-student route in this codebase."""
    if db is None:
        raise HTTPException(status_code=503, detail="Persistence unavailable")

    actor = user.get("uid", "")
    now = admin_firestore.SERVER_TIMESTAMP

    db.collection("dase_overrides").document(student_id).set(
        {
            "studentId": student_id,
            "weights": body.weights,
            "reason": body.reason,
            "setBy": actor,
            "updatedAt": now,
        }
    )
    db.collection("audit_log").document().set(
        {
            "actor": actor,
            "action": "dase_weights.override",
            "target": student_id,
            "details": {"weights": body.weights, "reason": body.reason},
            "at": now,
        }
    )
    return {"status": "ok", "studentId": student_id, "weights": body.weights}


@router.delete("/teachers/students/{student_id}/dase-weights")
async def clear_weight_override(student_id: str, user: dict = Depends(require_teacher_of)):
    """Revert a student to their profile's default weights."""
    if db is None:
        raise HTTPException(status_code=503, detail="Persistence unavailable")

    actor = user.get("uid", "")
    doc_ref = db.collection("dase_overrides").document(student_id)
    existed = doc_ref.get().exists
    if existed:
        doc_ref.delete()
        db.collection("audit_log").document().set(
            {
                "actor": actor,
                "action": "dase_weights.override_cleared",
                "target": student_id,
                "details": {},
                "at": admin_firestore.SERVER_TIMESTAMP,
            }
        )
    return {"status": "ok", "studentId": student_id, "cleared": existed}
