"""KNOW (knowledge demonstrated) / EXPR (written expression quality) split
scoring for dysgraphia (roadmap P4-10).

KNOW = |{ c in expected_concepts : judge(c, answer).evidenced }| / |expected_concepts|

Each concept is judged by the LLM, but the LLM only LABELS which concepts
are evidenced and quotes the span it found — the aggregation (the fraction
above) is deterministic code, and a quoted span that doesn't actually
appear verbatim in the student's answer is rejected rather than trusted, so
a model that "finds" evidence that isn't there cannot inflate the score.

EXPR = 0.4*organisation + 0.3*completeness + 0.3*mechanics, each 0..1 from a
rubric — THIS is the part a more severe form of dysgraphia mechanically
depresses, which is exactly why dase_profiles.json marks EXPR
diagnosticOnly under that profile: two answers with identical content but
different spelling/organisation must get equal KNOW and different EXPR.
"""

from __future__ import annotations

from typing import Any, Dict, List

from services.llm import LLMUnavailable, call_json

_KNOW_SYSTEM = """You judge whether a student's written answer demonstrates understanding
of specific concepts. For EACH concept in the list, decide if the answer provides
evidence of understanding it, and if so, quote the EXACT verbatim span of the
answer (word-for-word, character-for-character) that is your evidence.

Do not judge spelling, grammar or organisation — only whether the IDEA is present.
A misspelled but recognisable version of the right idea still counts as evidenced.

Return ONLY this JSON shape:
{"judgments": [{"concept": "...", "evidenced": true|false, "quote": "exact text from the answer, or empty string"}]}
"""

_EXPR_SYSTEM = """You rate the WRITTEN EXPRESSION quality of a student's answer — never its
factual content. Score each 0.0 to 1.0:
- organisation: does it have a sensible beginning/middle/end or logical flow?
- completeness: does it read as a finished thought rather than cut off or fragmentary?
- mechanics: grammar, sentence structure, basic punctuation (NOT spelling — a
  dysgraphia-aware rubric never penalises spelling here).

Return ONLY: {"organisation": 0.0-1.0, "completeness": 0.0-1.0, "mechanics": 0.0-1.0}
"""


def score_know(expected_concepts: List[str], answer: str) -> Dict[str, Any]:
    answer = (answer or "").strip()
    if not expected_concepts or not answer:
        return {"know": None, "judgments": [], "degraded": False}

    try:
        raw = call_json(
            _KNOW_SYSTEM,
            f"Concepts: {expected_concepts}\n\nAnswer:\n{answer[:4000]}",
        )
        degraded = False
    except LLMUnavailable:
        return {"know": None, "judgments": [], "degraded": True}

    judgments = []
    evidenced_count = 0
    for item in raw.get("judgments") or []:
        concept = str(item.get("concept") or "").strip()
        quote = str(item.get("quote") or "").strip()
        # The deterministic check: a claimed quote must actually appear,
        # verbatim, in the student's own answer — an LLM asserting
        # "evidenced: true" with a quote that isn't really there is rejected
        # here in code, not trusted from the model.
        evidenced = bool(item.get("evidenced")) and bool(quote) and quote in answer
        if evidenced:
            evidenced_count += 1
        judgments.append({"concept": concept, "evidenced": evidenced, "quote": quote})

    know = evidenced_count / len(expected_concepts) if expected_concepts else None
    return {"know": know, "judgments": judgments, "degraded": degraded}


def score_expr(answer: str) -> Dict[str, Any]:
    answer = (answer or "").strip()
    if not answer:
        return {"expr": None, "rubric": {}, "degraded": False}

    try:
        raw = call_json(_EXPR_SYSTEM, f"Answer:\n{answer[:4000]}")
        degraded = False
    except LLMUnavailable:
        return {"expr": None, "rubric": {}, "degraded": True}

    def _clamp01(x: Any) -> float:
        try:
            return max(0.0, min(1.0, float(x)))
        except (TypeError, ValueError):
            return 0.0

    organisation = _clamp01(raw.get("organisation"))
    completeness = _clamp01(raw.get("completeness"))
    mechanics = _clamp01(raw.get("mechanics"))
    expr = 0.4 * organisation + 0.3 * completeness + 0.3 * mechanics

    return {
        "expr": round(expr, 4),
        "rubric": {"organisation": organisation, "completeness": completeness, "mechanics": mechanics},
        "degraded": degraded,
    }
