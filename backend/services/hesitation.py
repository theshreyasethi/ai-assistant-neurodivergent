"""Interaction-only hesitation index (roadmap P4-14/P4-15) — never facial
inference, never a clinical label. docs/ROADMAP.md explicitly rejects
inferring anxiety from face landmarks; HES is built entirely from
interaction signals already being measured for other reasons.

RESIL = 1 - HES feeds DASE (services/dase_engine.py), so "higher is better"
matches RESIL's positive weight — the opposite of FRUST, the parameter it
replaced, which was named for the thing to minimise but weighted as if
higher were good.

Interventions driven by a high HES (frontend/src/hooks/useIntervention.ts)
are SUGGESTIONS the student can decline, never an automatic action, and are
never labelled as a diagnosis of anything.
"""

from __future__ import annotations

from typing import Optional


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def hesitation_index(
    *,
    latency_ratio: Optional[float] = None,
    mean_answer_changes: Optional[float] = None,
    blur_per_question: Optional[float] = None,
    chat_frustration: Optional[float] = None,
) -> Optional[float]:
    """Blends whichever of the four interaction signals are actually
    available, renormalizing its own weights over the present ones — the
    same discipline dase_engine.compute_dase() applies to the overall
    composite score, so a session missing one signal (e.g. no chatbot use)
    is not penalised or inflated by its absence.

    Weights (0.30 / 0.25 / 0.20 / 0.25 when all four are present) are
    literature-informed, unvalidated assumptions — tune in the pilot.
    """
    parts: list = []
    if latency_ratio is not None:
        # 1x personal baseline -> 0 hesitation; >=3x -> fully hesitant.
        parts.append((0.30, _clamp((latency_ratio - 1.0) / 2.0)))
    if mean_answer_changes is not None:
        parts.append((0.25, _clamp(mean_answer_changes / 3.0)))
    if blur_per_question is not None:
        parts.append((0.20, _clamp(blur_per_question)))
    if chat_frustration is not None:
        parts.append((0.25, _clamp(chat_frustration)))

    if not parts:
        return None
    total_weight = sum(w for w, _ in parts)
    return _clamp(sum(w * v for w, v in parts) / total_weight)
