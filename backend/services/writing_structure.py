"""Dictation -> structured essay, under the same "no new facts" rule
nlp_simplify.BASE_RULES applies to simplification (roadmap P4-09).

A dysgraphia student's spoken ideas are often well-formed; what's hard is
the mechanical act of writing them down in an organised way. This takes a
raw transcript and returns an outline + structured paragraphs using the
student's OWN words wherever possible — it must never introduce a fact,
number or claim that wasn't in the dictation.

Honest limitation: full hallucination-proofing would need a second
LLM-judge pass cross-checking every sentence against the source, which this
does not do. As a cheaper first line of defense, every NUMBER in the
structured output is checked against the numbers that actually appeared in
the dictation (numbers are the easiest concrete hallucination to catch
deterministically); a mismatch is surfaced as a warning rather than hidden,
so a human reviewer knows exactly what to double-check.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from services.llm import LLMUnavailable, call_json

SYSTEM = """You organise a student's SPOKEN dictation into a structured essay outline.

ABSOLUTE RULES:
1. Use the student's OWN words and ideas wherever possible — you are organising,
   not composing new content.
2. NEVER add a fact, number, name, date or claim that was not in the dictation.
3. You may fix grammar, add paragraph breaks, and reorder for clarity, but the
   substance must be traceable to what the student actually said.
4. If the dictation is too short or unclear to structure, say so honestly in
   `outline` rather than inventing structure that isn't there.

Return ONLY this JSON shape:
{
  "outline": ["Introduction: ...", "Point 1: ...", "Conclusion: ..."],
  "paragraphs": ["First paragraph text...", "Second paragraph text..."]
}
"""

_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


def _numbers_in(text: str) -> set:
    return set(_NUMBER_RE.findall(text or ""))


def structure_dictation(transcript: str) -> Dict[str, Any]:
    transcript = (transcript or "").strip()
    if not transcript:
        return {"outline": [], "paragraphs": [], "warnings": [], "degraded": False}

    try:
        raw = call_json(SYSTEM, f"Dictation:\n\n{transcript[:6000]}")
        degraded = False
    except LLMUnavailable:
        return {
            "outline": [], "paragraphs": [transcript],
            "warnings": ["AI structuring unavailable — showing the raw dictation unorganised."],
            "degraded": True,
        }

    outline: List[str] = [str(x).strip() for x in (raw.get("outline") or []) if str(x).strip()]
    paragraphs: List[str] = [str(x).strip() for x in (raw.get("paragraphs") or []) if str(x).strip()]

    source_numbers = _numbers_in(transcript)
    produced_numbers = _numbers_in(" ".join(paragraphs))
    extra_numbers = produced_numbers - source_numbers
    warnings = (
        [f"Numbers {sorted(extra_numbers)} appear in the structured version but not in the dictation — please double-check."]
        if extra_numbers else []
    )

    return {"outline": outline, "paragraphs": paragraphs, "warnings": warnings, "degraded": degraded}
