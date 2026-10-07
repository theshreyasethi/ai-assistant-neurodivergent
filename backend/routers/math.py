"""Verified math micro-steps + deterministic error typing (roadmap P4-07).

  POST /api/math/steps           - decompose a problem into verified steps
  POST /api/math/classify-error  - type a wrong numeric answer
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import require_active_user
from services import math_steps
from services.llm import LLMUnavailable, call_json

router = APIRouter(prefix="/math")

_STEPS_SYSTEM = """Break this arithmetic problem into single-operation micro-steps for a
student with dyscalculia. Rules:
1. Each step performs EXACTLY ONE operation (add, subtract, multiply, or divide).
2. Return the step's arithmetic as a plain expression using only digits, + - * / and
   parentheses — e.g. "12+7", never algebra or variables.
3. `say` is a short, concrete sentence naming the operation and the numbers
   ("12 plus 7 is 19"), never jargon.
4. Order steps the way a person would actually work through the problem.

Return ONLY this JSON shape:
{"steps": [{"op": "add"|"sub"|"mul"|"div", "expr": "12+7", "result": "19", "say": "..."}]}
"""


class StepsRequest(BaseModel):
    problem: str


class VerifiedStep(BaseModel):
    op: str
    expr: str
    result: str
    say: str


class StepsResponse(BaseModel):
    steps: List[VerifiedStep]
    degraded: bool


def _template_fallback(problem: str) -> List[dict]:
    """LLM unreachable, or every proposed step failed verification: a single
    honest step beats a confidently wrong breakdown, so this just states the
    problem is best solved with a calculator or a teacher's help rather than
    inventing a decomposition with nothing behind it."""
    return []


@router.post("/steps", response_model=StepsResponse)
async def get_steps(req: StepsRequest, _user: dict = Depends(require_active_user)):
    problem = (req.problem or "").strip()
    if not problem:
        raise HTTPException(status_code=422, detail="problem must not be empty")

    try:
        raw = call_json(_STEPS_SYSTEM, f"Problem: {problem}")
        proposed = raw.get("steps", []) if isinstance(raw, dict) else []
        degraded = False
    except LLMUnavailable:
        proposed, degraded = [], True

    verified = math_steps.verify_steps(proposed)
    if not verified and not degraded:
        # The LLM responded, but NOTHING it proposed re-verified — treat this
        # the same as an outage rather than serving zero steps silently.
        verified, degraded = _template_fallback(problem), True

    return StepsResponse(steps=[VerifiedStep(**s) for s in verified], degraded=degraded)


class ClassifyErrorRequest(BaseModel):
    expression: str
    correctAnswer: float
    studentAnswer: float
    operation: Optional[str] = None


@router.post("/classify-error")
async def classify_error(req: ClassifyErrorRequest, _user: dict = Depends(require_active_user)):
    error_type = math_steps.classify_math_error(
        expression=req.expression,
        correct_answer=req.correctAnswer,
        student_answer=req.studentAnswer,
        operation=req.operation,
    )
    return {"errorType": error_type}
