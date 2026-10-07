"""Unit tests for Phase 4's new pure-logic services — roadmap P4-06/07/08,
P4-10, P4-13, P4-14. Each test targets a specific correctness property the
roadmap calls out explicitly (never eval() on model output, a claimed quote
must actually appear verbatim, renormalize over whichever hesitation
signals are present, EMA pacing clamps to a safe range).
"""

import pytest

from services import hesitation, math_steps, pacing, visual_generator, writing_score


# ─────────────────────── math_steps: safe_eval / verify_steps ───────────────────────


def test_safe_eval_computes_simple_arithmetic():
    assert math_steps.safe_eval("12+7") == 19
    assert math_steps.safe_eval("3*4-2") == 10


def test_safe_eval_rejects_function_calls():
    with pytest.raises(math_steps.UnsafeExpression):
        math_steps.safe_eval("__import__('os').system('echo pwned')")


def test_safe_eval_rejects_overlong_expressions():
    with pytest.raises(math_steps.UnsafeExpression):
        math_steps.safe_eval("1+" * 100 + "1")


def test_safe_eval_rejects_power_operator():
    """No ast.Pow in the allowed operator set — an exponent on untrusted
    input is a cheap way to produce an astronomically large number."""
    with pytest.raises(math_steps.UnsafeExpression):
        math_steps.safe_eval("2**9999999")


def test_verify_steps_drops_a_step_whose_result_does_not_check_out():
    steps = [
        {"op": "add", "expr": "12+7", "result": "19", "say": "..."},
        {"op": "add", "expr": "12+7", "result": "20", "say": "wrong"},
        {"op": "add", "expr": "not an expr", "result": "5", "say": "unsafe"},
    ]
    verified = math_steps.verify_steps(steps)
    assert len(verified) == 1
    assert verified[0]["result"] == "19"


# ─────────────────────── math_steps: error typing truth table ───────────────────────


@pytest.mark.parametrize(
    "expression,correct,given,operation,expected",
    [
        ("8+5", 13, 3, "add", math_steps.OPERATION_CONFUSION),
        ("12*5", 60, 600, "mul", math_steps.PLACE_VALUE),
        ("7+8", 15, 99, "add", math_steps.FACT_RECALL),
        ("2+3*4", 14, 20, "add", math_steps.SEQUENCING),
        ("48+37", 85, 75, "add", math_steps.CARRY_BORROW),
    ],
)
def test_classify_math_error_truth_table(expression, correct, given, operation, expected):
    assert math_steps.classify_math_error(
        expression=expression, correct_answer=correct, student_answer=given, operation=operation,
    ) == expected


def test_classify_math_error_never_raises_on_unparseable_input():
    assert math_steps.classify_math_error(
        expression="garbage", correct_answer=5, student_answer=float("nan"), operation="add",
    ) in math_steps.ERROR_TYPES


# ─────────────────────── hesitation_index ───────────────────────


def test_hesitation_index_none_with_no_signals():
    assert hesitation.hesitation_index() is None


def test_hesitation_index_renormalizes_over_available_signals():
    """Two sessions with the SAME latency ratio but one also has an answer-
    change rate should not trivially equal each other — but a session with
    only ONE signal present must still produce a valid [0,1] value, not None,
    since that's the whole point of renormalizing over what's available."""
    only_latency = hesitation.hesitation_index(latency_ratio=3.0)
    assert only_latency is not None and 0.0 <= only_latency <= 1.0

    with_all_four = hesitation.hesitation_index(
        latency_ratio=3.0, mean_answer_changes=3.0, blur_per_question=1.0, chat_frustration=1.0,
    )
    assert with_all_four == pytest.approx(1.0, abs=1e-6)  # every signal maxed out


def test_hesitation_index_low_when_every_signal_is_calm():
    hes = hesitation.hesitation_index(
        latency_ratio=1.0, mean_answer_changes=0.0, blur_per_question=0.0, chat_frustration=0.0,
    )
    assert hes == pytest.approx(0.0, abs=1e-6)


# ─────────────────────── pacing ───────────────────────


def test_observed_wpm_requires_a_minimum_sample():
    assert pacing.observed_wpm(words_read=5, elapsed_ms=2000) is None  # too few words
    assert pacing.observed_wpm(words_read=100, elapsed_ms=500) is None  # too little active time


def test_observed_wpm_computes_correctly():
    # 200 words in 60 seconds (60000ms) = 200 wpm.
    assert pacing.observed_wpm(words_read=200, elapsed_ms=60000) == pytest.approx(200.0)


def test_next_wpm_clamps_to_safe_range():
    assert pacing.next_wpm(previous_wpm=170.0, observed=5000.0) <= pacing.MAX_WPM
    assert pacing.next_wpm(previous_wpm=170.0, observed=1.0) >= pacing.MIN_WPM


def test_next_wpm_does_not_whipsaw_on_a_single_session():
    """One fast session must not jump the suggested rate all the way to the
    observed value — the EMA blend dampens it."""
    result = pacing.next_wpm(previous_wpm=150.0, observed=300.0)
    assert 150.0 < result < 300.0


def test_high_replay_rate_slows_the_suggestion_down():
    without_replays = pacing.next_wpm(previous_wpm=170.0, observed=170.0, replay_rate=0.0)
    with_replays = pacing.next_wpm(previous_wpm=170.0, observed=170.0, replay_rate=0.5)
    assert with_replays < without_replays


# ─────────────────────── visual_generator sanitizer ───────────────────────


def test_sanitize_diagram_accepts_a_well_formed_flowchart():
    diagram = "flowchart TD\n  A[Water heats up] --> B[Evaporation]\n  B --> C[Clouds form]"
    result = visual_generator._sanitize_diagram(diagram)
    assert "A[Water heats up]" in result


@pytest.mark.parametrize("payload", [
    "flowchart TD\n  A[Start] --> B[End]\n  click A call someFn()",
    "flowchart TD\n  A[<img src=x onerror=alert(1)>] --> B[End]",
    "flowchart TD\n  A[Start] --> B[javascript:alert(1)]",
])
def test_sanitize_diagram_rejects_dangerous_payloads(payload):
    with pytest.raises(ValueError):
        visual_generator._sanitize_diagram(payload)


def test_sanitize_diagram_rejects_missing_directive():
    with pytest.raises(ValueError):
        visual_generator._sanitize_diagram("just some text\nnot a diagram at all")


# ─────────────────────── writing_score: deterministic quote-checking ───────────────────────


def test_score_know_rejects_a_claimed_quote_that_is_not_actually_in_the_answer(monkeypatch):
    """The LLM only LABELS; a quote it claims as evidence that doesn't
    actually appear verbatim in the student's own answer must never count,
    no matter what the model asserted about `evidenced`."""
    def fake_call_json(system, user):
        return {"judgments": [
            {"concept": "photosynthesis", "evidenced": True, "quote": "something not in the answer"},
        ]}
    monkeypatch.setattr(writing_score, "call_json", fake_call_json)

    result = writing_score.score_know(["photosynthesis"], "Plants use sunlight to make food.")
    assert result["know"] == 0.0
    assert result["judgments"][0]["evidenced"] is False


def test_score_know_accepts_a_quote_that_really_is_in_the_answer(monkeypatch):
    answer = "Plants use sunlight, water and carbon dioxide to make food."

    def fake_call_json(system, user):
        return {"judgments": [
            {"concept": "photosynthesis inputs", "evidenced": True, "quote": "sunlight, water and carbon dioxide"},
        ]}
    monkeypatch.setattr(writing_score, "call_json", fake_call_json)

    result = writing_score.score_know(["photosynthesis inputs"], answer)
    assert result["know"] == 1.0


def test_score_expr_computes_weighted_rubric(monkeypatch):
    monkeypatch.setattr(
        writing_score, "call_json",
        lambda system, user: {"organisation": 1.0, "completeness": 1.0, "mechanics": 0.0},
    )
    result = writing_score.score_expr("Some answer text.")
    assert result["expr"] == pytest.approx(0.4 * 1.0 + 0.3 * 1.0 + 0.3 * 0.0)
