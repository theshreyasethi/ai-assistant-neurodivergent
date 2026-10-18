"""DASE ablation study — 5 synthetic student archetypes x every configured
weight profile (roadmap P3-09).

Purpose: the weights in data/dase_profiles.json are literature-informed, not
empirically validated (the config's own _readme says so). The one way to
catch an obviously wrong weighting before a real student sees it is to run
every profile against a handful of synthetic archetypes and eyeball whether
the rank order makes sense. This is exactly how the ADHD profile's original
ATT_SPAN weight (0.15) was caught: it ranked "distracted but capable" LAST
among all five archetypes under the one profile meant to support that
student (see dase_profiles.json's _diagnosticOnlyNote).

This is offline analysis against synthetic data — no Firestore connection,
no real student data, safe to run anywhere including against this repo's
live-project .env, because it never imports firebase_config.

Usage:
    python scripts/run_ablation.py
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run as `python scripts/run_ablation.py`

from services import dase_engine as d  # noqa: E402

random.seed(42)  # deterministic archetypes: a re-run should print the same table


def _questions(
    n: int, *, p_correct: float, time_ms: int, jitter: int = 0, answer_changes: int = 0,
    re_read: bool = False, revisits: int = 0, focus_ratio: float | None = None,
    item_kinds: List[str] | None = None,
) -> List[dict]:
    events = []
    for i in range(n):
        correct = random.random() < p_correct
        t = max(300, time_ms + random.randint(-jitter, jitter))
        events.append({
            "type": "question", "questionId": f"q{i}", "difficulty": (i % 5) + 1,
            "selected": "x", "correct": correct, "timeMs": t,
            "answerChanges": answer_changes, "reRead": re_read, "revisits": revisits,
            "focusRatio": focus_ratio, "focusSamples": 10 if focus_ratio is not None else 0,
            "itemKind": (item_kinds[i % len(item_kinds)] if item_kinds else "recall"),
        })
    return events


def _voice(n: int, *, understood_rate: float) -> List[dict]:
    return [
        {
            "understood": random.random() < understood_rate,
            "sttConfidence": round(random.uniform(0.6, 0.95), 2),
            "repeats": 0 if random.random() < understood_rate else 1,
            "actionMs": random.randint(800, 3000),
        }
        for _ in range(n)
    ]


def _reading(n: int, *, wpm: int) -> List[dict]:
    return [{"wordsRead": 200, "elapsedMs": int(200 / wpm * 60000)} for _ in range(n)]


def _sessions(n_completed: int, n_abandoned: int) -> List[dict]:
    return [{"summary": {"completed": True}} for _ in range(n_completed)] + [
        {"summary": None} for _ in range(n_abandoned)
    ]


# ─────────────────────── archetypes ───────────────────────

ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "high_achiever": dict(
        questions=_questions(16, p_correct=0.9, time_ms=4500, jitter=500, focus_ratio=0.95,
                              item_kinds=["sequence", "category", "matching", "recall"]),
        voice=_voice(5, understood_rate=0.9),
        reading=_reading(3, wpm=190),
        sessions=_sessions(9, 1),
        baseline_ms=4500,
    ),
    "struggling_but_trying": dict(
        questions=_questions(16, p_correct=0.35, time_ms=9000, jitter=1500, answer_changes=2,
                              re_read=True, revisits=1, focus_ratio=0.85),
        voice=_voice(5, understood_rate=0.6),
        reading=_reading(3, wpm=110),
        sessions=_sessions(5, 4),
        baseline_ms=7000,
    ),
    "fast_guesser": dict(
        questions=_questions(16, p_correct=0.3, time_ms=1200, jitter=300, focus_ratio=0.5),
        voice=_voice(5, understood_rate=0.5),
        reading=_reading(3, wpm=150),
        sessions=_sessions(4, 5),
        baseline_ms=5000,
    ),
    "distracted_but_capable": dict(
        # The archetype that originally exposed the ADHD ATT_SPAN bug: gets
        # answers right, but the webcam signal shows a lot of looking away.
        questions=_questions(16, p_correct=0.8, time_ms=5000, jitter=800, focus_ratio=0.4,
                              answer_changes=1),
        voice=_voice(5, understood_rate=0.85),
        reading=_reading(3, wpm=170),
        sessions=_sessions(8, 2),
        baseline_ms=5000,
    ),
    "uniformly_failing": dict(
        # The audit's own prescribed addition: everything wrong, but with a
        # perfectly steady pace — the kind of input that exposed CONSIST
        # scoring uniform failure as 1.0 (S08).
        questions=_questions(16, p_correct=0.0, time_ms=5000, jitter=50, focus_ratio=0.9),
        voice=_voice(5, understood_rate=0.3),
        reading=_reading(3, wpm=130),
        sessions=_sessions(2, 8),
        baseline_ms=5000,
    ),
}


def _attention_lapse_session(n_correct: int, n_lapses: int, confidence: float = 0.8) -> List[dict]:
    """Synthetic wrong answers, fully classified, for the ADJ_ACC ablation
    below — same construction as the deterministic unit test in
    tests/test_dase_formulas.py, duplicated here because this script is
    intentionally dependency-free of the test suite (it is meant to be
    runnable standalone, including against this repo's live .env)."""
    correct = [
        {"type": "question", "questionId": f"q{i}", "difficulty": (i % 5) + 1, "selected": "x",
         "correct": True, "timeMs": 5000, "answerChanges": 0, "reRead": False, "revisits": 0,
         "focusRatio": None, "focusSamples": 0, "itemKind": "recall"}
        for i in range(n_correct)
    ]
    lapses = [
        {"type": "question", "questionId": f"q{n_correct + i}", "difficulty": (i % 5) + 1, "selected": "x",
         "correct": False, "timeMs": 2000, "answerChanges": 0, "reRead": False, "revisits": 0,
         "focusRatio": None, "focusSamples": 0, "itemKind": "recall",
         "classification": {"label": "ATTENTION_LAPSE", "confidence": confidence}}
        for i in range(n_lapses)
    ]
    return correct + lapses


def run() -> None:
    cfg = d.load_config()
    profiles = list(cfg["profiles"])

    results: Dict[str, Dict[str, Dict[str, Any]]] = {}  # archetype -> profile -> result
    for arche_name, data in ARCHETYPES.items():
        params = d.compute_parameters(
            data["questions"], data["reading"], data["sessions"], data["voice"],
            baseline_ms=data["baseline_ms"],
        )
        results[arche_name] = {p: d.compute_dase(params, p) for p in profiles}

    print("=" * 100)
    print("DASE ABLATION — 5 archetypes x", len(profiles), "profiles")
    print("Weights are literature-informed, NOT empirically validated (dase_profiles.json _readme).")
    print("=" * 100)

    for arche_name in ARCHETYPES:
        print(f"\n--- {arche_name} --- (rank order, highest score first)")
        ranked = sorted(
            ((p, results[arche_name][p]) for p in profiles),
            key=lambda kv: (kv[1]["score"] if kv[1]["score"] is not None else -1),
            reverse=True,
        )
        for rank, (profile, r) in enumerate(ranked, start=1):
            score = f"{r['score']:.3f}" if r["score"] is not None else "N/A"
            print(f"  {rank:2d}. {profile:16s} score={score:6s} coverage={r['coverage']:.2f}"
                  f"  missing={r['missingParameters']}")

    # Per-profile view: does any archetype rank suspiciously out of place
    # under the profile meant to support exactly that kind of student? This
    # is the check that originally caught ADHD/ATT_SPAN.
    print("\n" + "=" * 100)
    print("PER-PROFILE ARCHETYPE RANKING (sanity check for inversions)")
    print("=" * 100)
    for profile in profiles:
        print(f"\n--- {profile} ---")
        ranked = sorted(
            ((a, results[a][profile]) for a in ARCHETYPES),
            key=lambda kv: (kv[1]["score"] if kv[1]["score"] is not None else -1),
            reverse=True,
        )
        for rank, (arche_name, r) in enumerate(ranked, start=1):
            score = f"{r['score']:.3f}" if r["score"] is not None else "N/A"
            print(f"  {rank}. {arche_name:24s} score={score}")

    # Flag the specific failure mode the audit found: "uniformly_failing"
    # should never outrank "struggling_but_trying" or "distracted_but_capable"
    # under ANY profile — if it does, some parameter is still rewarding
    # uniform failure.
    print("\n" + "=" * 100)
    print("REGRESSION CHECK")
    print("=" * 100)
    problems = []
    for profile in profiles:
        fail_score = results["uniformly_failing"][profile]["score"] or 0.0
        trying_score = results["struggling_but_trying"][profile]["score"] or 0.0
        if fail_score >= trying_score:
            problems.append(profile)
    if problems:
        print(f"FAIL: uniformly_failing outranks struggling_but_trying under: {problems}")
    else:
        print("OK: uniformly_failing never outranks struggling_but_trying, under any profile.")

    # ─── Synthetic wrong-answer ablation: ADJ_ACC, adhd vs default ───
    # Explicitly validates how the attention-lapse-forgiveness mechanism
    # computes and moves the score under the one profile that weights it
    # heavily (adhd, 0.2544 — its single largest term) versus a profile
    # that never weights it at all (default).
    print("\n" + "=" * 100)
    print("SYNTHETIC WRONG-ANSWER ABLATION — ADJ_ACC under adhd vs default")
    print("=" * 100)
    lapse_events = _attention_lapse_session(n_correct=6, n_lapses=4, confidence=0.8)
    lapse_params = d.compute_parameters(lapse_events)
    no_adj_acc = {k: v for k, v in lapse_params.items() if k != "ADJ_ACC"}
    print(f"6 correct / 4 wrong, all 4 classified ATTENTION_LAPSE @ confidence 0.8")
    print(f"  ACC     = {lapse_params['ACC']:.3f}")
    print(f"  ADJ_ACC = {lapse_params['ADJ_ACC']:.3f}  (forgiveness credit raises it above raw ACC)")
    for profile in ("adhd", "default"):
        with_score = d.compute_dase(lapse_params, profile)["score"]
        without_score = d.compute_dase(no_adj_acc, profile)["score"]
        delta = with_score - without_score
        print(f"  {profile:8s}: score with ADJ_ACC = {with_score:.3f}, without = {without_score:.3f}"
              f"  (delta {delta:+.3f})")


if __name__ == "__main__":
    run()
