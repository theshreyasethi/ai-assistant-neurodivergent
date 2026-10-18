"""Golden-vector tests for backend/services/dase_engine.py's parameter
formulas and the composite scoring invariants — roadmap P3-09.

Each test below corresponds to a specific defect the patent-readiness audit
found and P3-06/P3-07/P3-10 fixed: ADJ_ACC vanishing for a perfect session,
CONSIST rewarding uniform failure with a perfect score, TIME_EFF crediting
fast WRONG answers against a same-session baseline, TASK_COMP always reading
1.0 because only the just-evaluated session was ever counted, LRN_VEL scoring
a straight-A student and a straight-F student identically, and declared
profile weights that didn't sum to 1 or named an undefined parameter.
"""

from typing import List

import pytest

from services import dase_engine as d


def ev(i, correct, t=5000, **kw):
    base = dict(
        type="question", questionId=f"q{i}", difficulty=3, correct=correct, selected="x", timeMs=t,
        answerChanges=0, reRead=False, revisits=0, focusRatio=None, focusSamples=0,
    )
    return {**base, **kw}


# ─────────────────────── ADJ_ACC (P3-06) ───────────────────────


def test_adj_acc_exists_for_a_perfect_session():
    """Audit finding: ADJ_ACC previously required at least one classified
    wrong answer to appear at all, so a perfect session reported NOTHING for
    this parameter instead of the obviously correct answer (1.0)."""
    params = d.compute_parameters([ev(i, True) for i in range(6)])
    assert params.get("ADJ_ACC") == 1.0


def test_adj_acc_absent_when_classifier_coverage_is_thin():
    """Emitting ADJ_ACC on < 80% classified wrong answers would be a claim
    the data doesn't support — stays absent rather than being computed from
    mostly-unlabelled errors."""
    events = [ev(i, True) for i in range(4)] + [
        ev(10, False, classification={"label": "KNOWLEDGE_GAP", "confidence": 0.9}),
        ev(11, False),  # unclassified
        ev(12, False),  # unclassified
    ]
    assert "ADJ_ACC" not in d.compute_parameters(events)


def test_adj_acc_credits_attention_lapse_by_confidence():
    events = [ev(i, True) for i in range(5)] + [
        ev(10, False, classification={"label": "ATTENTION_LAPSE", "confidence": 0.8}),
    ]
    params = d.compute_parameters(events)
    # 5 correct (5.0) + 0.75*0.8 credit, over 6 answers.
    assert params["ADJ_ACC"] == pytest.approx((5.0 + 0.75 * 0.8) / 6, abs=1e-6)


def _synthetic_wrong_answers(n_correct: int, n_attention_lapse: int, *, confidence: float = 0.8) -> List[dict]:
    """A synthetic session with explicit, fully-classified wrong answers — the
    scoring-ablation case roadmap requested for comparing ADJ_ACC's effect
    across profiles. 100% classifier coverage, well above the 80% floor
    _adj_acc() requires before it will compute at all."""
    correct = [ev(i, True) for i in range(n_correct)]
    lapses = [
        ev(n_correct + i, False, classification={"label": "ATTENTION_LAPSE", "confidence": confidence})
        for i in range(n_attention_lapse)
    ]
    return correct + lapses


def test_adj_acc_raises_the_adhd_score_but_is_irrelevant_to_default():
    """Explicitly validates how ADJ_ACC computes and affects scores under
    the ADHD profile compared to default (the scoring-ablation extension
    roadmap requested): ADHD weights ADJ_ACC as its single largest term
    (0.2544) specifically to forgive attention-lapse-classified wrong
    answers; default never declares ADJ_ACC at all, so the same forgiveness
    has zero effect there."""
    events = _synthetic_wrong_answers(n_correct=6, n_attention_lapse=4, confidence=0.8)
    params = d.compute_parameters(events)
    assert params["ACC"] == pytest.approx(0.6, abs=1e-6)
    assert params["ADJ_ACC"] > params["ACC"]  # attention-lapse credit raises it above raw accuracy

    without_adj_acc = {k: v for k, v in params.items() if k != "ADJ_ACC"}

    adhd_with = d.compute_dase(params, "adhd")["score"]
    adhd_without = d.compute_dase(without_adj_acc, "adhd")["score"]
    assert adhd_with > adhd_without  # ADHD's own largest weight is ADJ_ACC — removing it must lower the score

    default_with = d.compute_dase(params, "default")["score"]
    default_without = d.compute_dase(without_adj_acc, "default")["score"]
    assert default_with == pytest.approx(default_without, abs=1e-9)  # default never weights ADJ_ACC at all


# ─────────────── PACE_STAB / ACC_STAB (P3-06, split from CONSIST) ───────────────
# CONSIST used to blend response-time stability with cross-session accuracy
# stability into one number. They're split into two separate parameters so
# that pace (diagnostic-only under adhd/autism — see dase_profiles.json) can
# be excluded from those profiles' scores independently of accuracy
# stability, which is never diagnostic-only for anyone.


def test_pace_stability_rewards_steady_correct_pace():
    steady = [ev(i, True, t=5000) for i in range(6)]
    assert d.compute_parameters(steady)["PACE_STAB"] == pytest.approx(1.0, abs=1e-6)


def test_pace_stability_penalises_erratic_pace():
    erratic = [ev(i, True, t=t) for i, t in enumerate([1000, 9000, 500, 12000, 800, 15000])]
    steady = [ev(i, True, t=5000) for i in range(6)]
    assert d.compute_parameters(erratic)["PACE_STAB"] < d.compute_parameters(steady)["PACE_STAB"]


def test_accuracy_stability_is_independent_of_accuracy_level():
    """A student reliably scoring 0% across sessions is exactly as
    'consistent' as one reliably scoring 90% — ACC_STAB measures variance
    across sessions, never the level itself (that's ACC's job)."""
    reliably_zero = d._accuracy_stability([0.0, 0.0, 0.0])
    reliably_high = d._accuracy_stability([0.9, 0.9, 0.9])
    assert reliably_zero == pytest.approx(1.0, abs=1e-6)
    assert reliably_high == pytest.approx(1.0, abs=1e-6)


def test_accuracy_stability_penalises_session_to_session_swings():
    erratic = d._accuracy_stability([0.0, 1.0, 0.0])
    steady = d._accuracy_stability([0.5, 0.5, 0.5])
    assert erratic < steady


# ─────────────────────── TIME_EFF (P3-06) ───────────────────────


def test_time_eff_ignores_wrong_answers_and_uses_cross_session_baseline():
    """Audit finding: the old formula averaged ALL answers (correct or not)
    against a same-session median, so a uniformly fast-but-wrong session
    scored as "efficient". Correct answers only, against an explicit
    cross-session baseline passed in from services/baselines.py."""
    events = [ev(i, False, t=500) for i in range(5)] + [ev(10, True, t=4000)]
    without_baseline = d.compute_parameters(events)
    assert "TIME_EFF" not in without_baseline  # only 1 correct answer: below the n>=3 floor

    events2 = [ev(i, True, t=4000) for i in range(5)]
    params = d.compute_parameters(events2, baseline_ms=4000)
    assert params["TIME_EFF"] == pytest.approx(1.0, abs=1e-6)

    params_slow = d.compute_parameters(events2, baseline_ms=2000)
    assert params_slow["TIME_EFF"] == pytest.approx(0.5, abs=1e-6)


# ─────────────────────── TASK_COMP (P3-06) ───────────────────────


def test_task_comp_counts_abandoned_sessions_as_started_not_completed():
    """Audit finding: TASK_COMP always read 1.0 because only the single
    session currently being evaluated was ever in the denominator, and that
    session obviously counts as "completed" simply by being the one you're
    scoring. Abandoned sessions (summary never written) must drag it down."""
    sessions = [
        {"summary": {"completed": True}},
        {"summary": {"completed": True}},
        {"summary": None},  # tab closed, never ended
        {"summary": {"completed": False}},
    ]
    params = d.compute_parameters([ev(0, True)], sessions=sessions)
    assert params["TASK_COMP"] == pytest.approx(0.5, abs=1e-6)


# ─────────────────────── LRN_VEL (P3-06) ───────────────────────


def test_lrn_vel_separates_mastery_from_failure():
    """Audit finding: both a straight-A and a straight-F student scored
    LRN_VEL = 0.5 ("no change"), because both have a first/second-half delta
    of zero. Sustained mastery must read as mastery, not as "nothing happened"."""
    good = d.compute_parameters([ev(i, True) for i in range(8)]).get("LRN_VEL")
    bad = d.compute_parameters([ev(i, False, t=5000 + i) for i in range(8)]).get("LRN_VEL")
    assert good is not None and bad is not None
    assert good > bad
    assert good == pytest.approx(0.9, abs=1e-6)


def test_lrn_vel_rewards_real_improvement_without_hitting_the_mastery_ceiling():
    # First half 1/3 correct, second half 2/3 correct: real improvement, but
    # neither half reaches the >=0.9 sustained-mastery ceiling.
    first_half = [ev(0, False), ev(1, False), ev(2, True)]
    second_half = [ev(3, True), ev(4, True), ev(5, False)]
    vel = d.compute_parameters(first_half + second_half)["LRN_VEL"]
    assert 0.5 < vel < 0.9


# ─────────────────────── PATTERN / RESIL (P3-07) ───────────────────────


def test_pattern_requires_at_least_three_tagged_items():
    events = [ev(i, True, itemKind="sequence") for i in range(2)]
    assert "PATTERN" not in d.compute_parameters(events)


def test_pattern_scores_only_tagged_item_kinds():
    events = (
        [ev(i, True, itemKind="sequence") for i in range(3)]
        + [ev(i, False, itemKind="recall") for i in range(10, 13)]
    )
    params = d.compute_parameters(events)
    assert params["PATTERN"] == pytest.approx(1.0, abs=1e-6)


def test_resil_present_from_answer_changes_and_latency_alone():
    """RESIL = 1 - HES. Full HES (roadmap P4-15) also needs tab-blur and chat
    sentiment, neither of which exists yet — this asserts the PARTIAL index
    still computes from what's available today (latency vs baseline,
    answer-change rate) rather than silently vanishing."""
    events = [ev(i, True, t=8000, answerChanges=2) for i in range(4)]
    params = d.compute_parameters(events, baseline_ms=4000)
    assert "RESIL" in params
    assert 0.0 <= params["RESIL"] <= 1.0
    assert params["RESIL"] < 1.0  # slower than baseline + changed answers -> some hesitation


# ─────────────────────── degraded exclusion (P3-11) ───────────────────────


def test_degraded_items_excluded_from_every_parameter():
    clean = [ev(i, True) for i in range(6)]
    degraded = [ev(i, False, degraded=True) for i in range(10, 16)]
    with_degraded = d.compute_parameters(clean + degraded)
    without_degraded = d.compute_parameters(clean)
    assert with_degraded["ACC"] == without_degraded["ACC"] == 1.0


def test_error_breakdown_excludes_degraded_and_reports_the_count():
    events = [ev(0, False, classification={"label": "KNOWLEDGE_GAP", "confidence": 0.9})]
    degraded = [ev(1, False, degraded=True), ev(2, False, degraded=True)]
    result = d.error_breakdown(events + degraded)
    assert result["degradedExcluded"] == 2
    assert result["totalWrong"] == 1


# ─────────────────────── composite invariants (P3-09, P3-10) ───────────────────────


@pytest.mark.parametrize("profile", list(d.load_config()["profiles"]))
def test_composite_invariants(profile):
    params = {k: 0.7 for k in d.load_config()["_parameters"]}
    r = d.compute_dase(params, profile)
    assert 0.0 <= r["score"] <= 1.0
    assert 0.0 <= r["coverage"] <= 1.0
    # Audit finding: adhd and dyslexia declared weights summing to 1.10
    # (double-counted intent); deaf summed to 0.85 after a dead-weight
    # parameter (WRIT_EXP) with no computation source. P3-10 normalised
    # every profile to exactly 1.0.
    assert abs(sum(d.profile_weights(profile).values()) - 1.0) < 1e-6


def test_every_weighted_parameter_is_defined():
    """Audit finding: PATTERN was weighted at 0.20 in the autism profile but
    did not appear in `_parameters` at all — a schema-validation gap that let
    an undefined, unimplemented parameter sit in a literature-informed
    config and silently never contribute to anyone's score."""
    cfg = d.load_config()
    for name, p in cfg["profiles"].items():
        assert set(p["weights"]) <= set(cfg["_parameters"]), name


def test_composite_is_monotonic_in_accuracy_when_all_else_equal():
    low = d.compute_dase({"ACC": 0.3, "EFFORT": 0.7, "LRN_VEL": 0.7, "TIME_EFF": 0.7, "PACE_STAB": 0.7, "ACC_STAB": 0.7, "COMP": 0.7, "TASK_COMP": 0.7}, "default")
    high = d.compute_dase({"ACC": 0.9, "EFFORT": 0.7, "LRN_VEL": 0.7, "TIME_EFF": 0.7, "PACE_STAB": 0.7, "ACC_STAB": 0.7, "COMP": 0.7, "TASK_COMP": 0.7}, "default")
    assert high["score"] > low["score"]


def test_override_weights_replace_profile_defaults_but_keep_diagnostic_rule():
    params = {"ACC": 1.0, "ATT_SPAN": 1.0, "EFFORT": 1.0}
    default_result = d.compute_dase(params, "adhd")
    override_result = d.compute_dase(params, "adhd", override_weights={"ACC": 1.0, "ATT_SPAN": 1.0, "EFFORT": 1.0})
    # ATT_SPAN stays diagnostic-only (a fact about ADHD, not a teacher
    # preference) even though the override's own weights still name it.
    assert "ATT_SPAN" not in override_result["usedWeights"]
    assert override_result["score"] == pytest.approx(1.0, abs=1e-6)
    assert default_result["score"] == pytest.approx(1.0, abs=1e-6)


# ─────────────────────── confidence intervals (U8) ───────────────────────


def test_wilson_interval_widens_as_n_shrinks_for_the_same_proportion():
    """The whole point of reporting an interval for a 9-item session: the
    SAME observed proportion (2/3) should report a much wider interval at
    n=3 than the same 2/3 ratio scaled up to n=300."""
    small = d.wilson_interval(2, 3)
    large = d.wilson_interval(200, 300)
    assert (small[1] - small[0]) > (large[1] - large[0])


def test_wilson_interval_is_maximally_uninformative_at_n_zero():
    assert d.wilson_interval(0, 0) == (0.0, 1.0)


def test_wilson_interval_bounds_never_escape_zero_one():
    lo, hi = d.wilson_interval(9, 9)  # a perfect small sample
    assert 0.0 <= lo <= hi <= 1.0


def test_parameter_intervals_match_the_n_behind_each_point_estimate():
    events = [ev(i, i < 6) for i in range(9)]  # 6/9 correct, difficulty=3 (>=3 -> also COMP-eligible)
    params = d.compute_parameters(events)
    intervals = d.parameter_intervals(events)
    assert set(intervals) == {"ACC", "COMP"}  # no itemKind data -> PATTERN absent, no sessions -> TASK_COMP absent
    for name in ("ACC", "COMP"):
        lo, hi = intervals[name]
        assert lo <= params[name] <= hi


def test_bootstrap_score_interval_contains_the_point_estimate_and_has_positive_width():
    events = [ev(i, i < 6) for i in range(9)]
    params = d.compute_parameters(events)
    point_score = d.compute_dase(params, "default")["score"]
    lo, hi = d.bootstrap_score_interval(events, profile="default", n_resamples=300, seed=7)
    assert lo <= point_score <= hi
    assert hi > lo  # a mixed 6/9 session must not collapse to a zero-width interval


def test_bootstrap_score_interval_is_none_with_no_question_events():
    assert d.bootstrap_score_interval([], profile="default") is None


def test_config_sha256_and_version_are_stable_and_present():
    assert len(d.config_sha256()) == 64
    assert d.config_sha256() == d.config_sha256()
    assert d.config_version()
