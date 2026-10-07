"""Dysgraphia writing pipeline (roadmap P4-09, P4-10).

  POST /api/writing/structure - dictation -> outline + paragraphs
  POST /api/writing/score     - KNOW (concept coverage) + EXPR (mechanics)
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import require_active_user
from services import writing_score, writing_structure

router = APIRouter(prefix="/writing")


class StructureRequest(BaseModel):
    transcript: str


@router.post("/structure")
async def structure(req: StructureRequest, _user: dict = Depends(require_active_user)):
    transcript = (req.transcript or "").strip()
    if not transcript:
        raise HTTPException(status_code=422, detail="transcript must not be empty")
    return writing_structure.structure_dictation(transcript)


class ScoreRequest(BaseModel):
    answer: str
    expectedConcepts: List[str] = []


@router.post("/score")
async def score(req: ScoreRequest, _user: dict = Depends(require_active_user)):
    answer = (req.answer or "").strip()
    if not answer:
        raise HTTPException(status_code=422, detail="answer must not be empty")

    know_result = writing_score.score_know(req.expectedConcepts, answer)
    expr_result = writing_score.score_expr(answer)
    return {
        "know": know_result["know"],
        "knowJudgments": know_result["judgments"],
        "expr": expr_result["expr"],
        "exprRubric": expr_result["rubric"],
        "degraded": know_result["degraded"] or expr_result["degraded"],
    }
