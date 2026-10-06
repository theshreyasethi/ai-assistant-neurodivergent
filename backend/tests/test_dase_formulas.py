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


# ─────────────────────── CONSIST (P3-06) ───────────────────────


def test_consist_does_not_reward_uniform_failure():
    """Audit finding: 1 - 4p(1-p) scored a student who missed every single
    question a perfect 1.0 — uniform FAILURE is not the same thing as
    consistency, and the old formula could not tell them apart."""
    all_wrong = [ev(i, False, t=5000 + i * 10) for i in range(8)]
    assert d.compute_parameters(all_wrong).get("CONSIST", 0.0) < 0.5


def test_consist_rewards_steady_correct_pace():
    steady = [ev(i, True, t=5000) for i in range(6)]
    assert d.compute_parameters(steady)["CONSIST"] == pytest.approx(1.0, abs=1e-6)


def test_consist_penalises_erratic_pace():
    erratic = [ev(i, True, t=t) for i, t in enumerate([1000, 9000, 500, 12000, 800, 15000])]
    steady = [ev(i, True, t=5000) for i in range(6)]
    assert d.compute_parameters(erratic)["CONSIST"] < d.compute_parameters(steady)["CONSIST"]


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
    low = d.compute_dase({"ACC": 0.3, "EFFORT": 0.7, "LRN_VEL": 0.7, "TIME_EFF": 0.7, "CONSIST": 0.7, "COMP": 0.7, "TASK_COMP": 0.7}, "default")
    high = d.compute_dase({"ACC": 0.9, "EFFORT": 0.7, "LRN_VEL": 0.7, "TIME_EFF": 0.7, "CONSIST": 0.7, "COMP": 0.7, "TASK_COMP": 0.7}, "default")
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


def test_config_sha256_and_version_are_stable_and_present():
    assert len(d.config_sha256()) == 64
    assert d.config_sha256() == d.config_sha256()
    assert d.config_version()
