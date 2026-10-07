"""POST /api/nlp/pos — experimental part-of-speech tagging for Deaf/HoH
readers (roadmap P4-03).

Deliberately labelled experimental everywhere it surfaces (API response and
UI copy): there is no evidence in this codebase's research docs that
colour-coding POS tags improves comprehension for this population — it is a
testable hypothesis, not a patent-pillar claim (docs/ROADMAP.md explicitly
says not to treat it as one). The endpoint exists so the hypothesis CAN be
tested (log toggle use against downstream COMP), not because the research
already supports it.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import require_active_user

router = APIRouter()

MAX_CHARS = 4000

# Collapsed to a small, UI-friendly set — spaCy's full tag set (NNP, VBZ, ...)
# is too granular to colour-code legibly. Coarse POS (pos_) already gives
# this grouping; this is just spaCy's own coarse tags, named for the API.
_COARSE = {"NOUN", "PROPN", "VERB", "ADJ", "ADV", "PRON", "DET", "ADP", "CONJ", "CCONJ", "SCONJ", "NUM", "PART", "INTJ"}


class PosRequest(BaseModel):
    text: str


class PosToken(BaseModel):
    text: str
    pos: str
    whitespaceAfter: bool


class PosResponse(BaseModel):
    tokens: List[PosToken]
    degraded: bool
    experimental: bool = True


def _tag(text: str) -> List[PosToken]:
    import spacy

    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        return []

    doc = nlp(text[:MAX_CHARS])
    return [
        PosToken(
            text=token.text,
            pos=token.pos_ if token.pos_ in _COARSE else "OTHER",
            whitespaceAfter=bool(token.whitespace_),
        )
        for token in doc
    ]


@router.post("/nlp/pos", response_model=PosResponse)
async def pos_tag(req: PosRequest, _user: dict = Depends(require_active_user)):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="text must not be empty")

    tokens = _tag(text)
    return PosResponse(tokens=tokens, degraded=not tokens)
