"""Cross-session personal response-time baselines — student_baselines/{uid}.

TIME_EFF (roadmap P3-06) must compare a correct answer's response time against
the student's OWN history across every session they've ever had, never a
same-session median (that credits a uniformly slow or fast session against
itself) and never a cohort statistic (the engine's governing rule throughout
dase_engine.py). This module is the read/write boundary for that history.

Storage shape, one document per student:
    {
      "times": [float, ...],                 # most recent CORRECT answer times, newest last
      "byDifficulty": {"1": [...], "3": [...], ...},
    }

Lists are capped (_MAX_SAMPLES) so the document can't grow without bound over
a student's whole enrollment — a rolling window of recent behaviour is the
right comparison, not a lifetime one that drifts further from "now" every term.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Sequence

# Below this many cross-session samples the "personal baseline" is really just
# noise from a handful of answers — TIME_EFF stays absent rather than being
# computed against a baseline that doesn't mean anything yet.
MIN_BASELINE_SAMPLES = 20
# Per-difficulty baselines need their own sample floor, smaller than the
# overall one since any single difficulty band sees fewer answers.
MIN_DIFFICULTY_SAMPLES = 8
_MAX_SAMPLES = 200


def _doc_ref(db, uid: str):
    return db.collection("student_baselines").document(uid)


def load_baseline(db, uid: str) -> Dict[str, Any]:
    """Raw stored baseline doc, or empty structure if none exists yet."""
    snap = _doc_ref(db, uid).get()
    data = snap.to_dict() if snap.exists else None
    return {
        "times": list((data or {}).get("times") or []),
        "byDifficulty": dict((data or {}).get("byDifficulty") or {}),
    }


def baseline_ms(db, uid: str) -> Optional[float]:
    """Cross-session median correct-answer time, or None below the sample floor."""
    times = load_baseline(db, uid)["times"]
    usable = [t for t in times if t and t > 0]
    if len(usable) < MIN_BASELINE_SAMPLES:
        return None
    return statistics.median(usable)


def baseline_ms_for_difficulty(db, uid: str, difficulty: int) -> Optional[float]:
    """Per-difficulty-band median when there's enough of that band's own
    history; falls back to the overall cross-session baseline otherwise."""
    by_difficulty = load_baseline(db, uid)["byDifficulty"]
    band = [t for t in (by_difficulty.get(str(difficulty)) or []) if t and t > 0]
    if len(band) >= MIN_DIFFICULTY_SAMPLES:
        return statistics.median(band)
    return baseline_ms(db, uid)


def record_correct_times(db, uid: str, events: Sequence[dict]) -> None:
    """Append this session's correct-answer times into the rolling baseline.

    Called once per /api/evaluate — the session's events are already loaded
    there, so this costs one extra read + one write rather than touching
    Firestore per question. Only CORRECT answers feed the baseline: a wrong
    answer's time says nothing about how fast the student normally responds
    when they actually know the material.
    """
    new_times = [
        float(e["timeMs"]) for e in events if e.get("correct") and e.get("timeMs")
    ]
    if not new_times:
        return

    current = load_baseline(db, uid)
    times = (current["times"] + new_times)[-_MAX_SAMPLES:]
    by_difficulty = {k: list(v) for k, v in current["byDifficulty"].items()}
    for e in events:
        if not e.get("correct") or not e.get("timeMs"):
            continue
        band = str(e.get("difficulty") or 3)
        by_difficulty.setdefault(band, []).append(float(e["timeMs"]))
        by_difficulty[band] = by_difficulty[band][-_MAX_SAMPLES:]

    _doc_ref(db, uid).set({"times": times, "byDifficulty": by_difficulty}, merge=True)
