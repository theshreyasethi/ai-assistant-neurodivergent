"""POST /api/visual-summary — the DHH visual-summary pipeline (roadmap P4-01).

services/visual_generator.py has existed since before this file but was
never mounted on any router — a real, working service with zero reachable
endpoint (patent-readiness audit finding: "Service exists but is
unreachable"). This is that endpoint.
"""

import time
from typing import Optional

from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import require_active_user
from services import visual_generator

router = APIRouter()

# Per-user rate limit: a lesson's visual summary is cached (text, profile),
# so a legitimate student re-opening the same lesson costs nothing extra —
# this only throttles someone hammering the endpoint with NEW text, which is
# the one path that actually spends a Gemini call every time.
_RATE_LIMIT_WINDOW_S = 60
_RATE_LIMIT_MAX_CALLS = 10
_calls: "TTLCache[str, list]" = TTLCache(maxsize=4096, ttl=_RATE_LIMIT_WINDOW_S)


def _check_rate_limit(uid: str) -> None:
    now = time.time()
    recent = [t for t in _calls.get(uid, []) if now - t < _RATE_LIMIT_WINDOW_S]
    if len(recent) >= _RATE_LIMIT_MAX_CALLS:
        raise HTTPException(status_code=429, detail="Too many visual-summary requests. Try again shortly.")
    recent.append(now)
    _calls[uid] = recent


class VisualSummaryRequest(BaseModel):
    text: str
    profile: Optional[str] = "deaf"


@router.post("/visual-summary")
async def visual_summary(req: VisualSummaryRequest, user: dict = Depends(require_active_user)):
    _check_rate_limit(user.get("uid", ""))
    return visual_generator.generate_visual_summary(req.text, req.profile or "deaf")
