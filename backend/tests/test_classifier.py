"""Truth table for services/dase_engine.classify_error — roadmap P3-09.

classify_error is only ever called on a WRONG answer, so every case here
asks the same question with a different combination of (response-time ratio
vs the student's own baseline, focus data, re-read, timeout): what probable
cause explains this wrong answer, and how confident is that label? The
abstention paths (no usable focus data, too few prior samples) are as much
the point of the classifier as its confident paths — a system that always
produces a label even when it doesn't know is a worse system than one that
sometimes says so.
"""

import pytest

from services import dase_engine as d

BASELINE_TIMES = [5000.0] * 6  # a well-established personal baseline


def test_timed_out_is_always_processing_delay():
    c = d.classify_error(time_ms=30000, prior_times_ms=BASELINE_TIMES, timed_out=True)
    assert c.label == d.PROCESSING_DELAY
    assert c.confidence == pytest.approx(0.9)


def test_very_slow_relative_to_baseline_is_processing_delay():
    c = d.classify_error(time_ms=12000, prior_times_ms=BASELINE_TIMES)  # 2.4x baseline
    assert c.label == d.PROCESSING_DELAY


def test_fast_and_looking_away_is_attention_lapse():
    c = d.classify_error(
        time_ms=1500, prior_times_ms=BASELINE_TIMES, focus_ratio=0.3, focus_samples=10,
    )
    assert c.label == d.ATTENTION_LAPSE


def test_very_fast_present_and_no_reread_is_comprehension_barrier():
    c = d.classify_error(
        time_ms=1000, prior_times_ms=BASELINE_TIMES, focus_ratio=0.95, focus_samples=10,
        re_read=False,
    )
    assert c.label == d.COMPREHENSION_BARRIER


def test_fast_present_but_reread_falls_through_to_knowledge_gap_default():
    """Present, looking at the screen, answered very fast, but DID go back to
    re-read the stem — the comprehension-barrier branch explicitly excludes
    this (re-reading is evidence the question DID land, it just didn't help),
    so this falls through to the honest residual label."""
    c = d.classify_error(
        time_ms=1000, prior_times_ms=BASELINE_TIMES, focus_ratio=0.95, focus_samples=10,
        re_read=True,
    )
    assert c.label == d.KNOWLEDGE_GAP


def test_classifier_abstains_without_focus_data():
    """Audit finding: a fast wrong answer with no webcam data at all must not
    be forced into ATTENTION_LAPSE or COMPREHENSION_BARRIER — abstains to
    KNOWLEDGE_GAP at low confidence and records BOTH as live alternatives."""
    c = d.classify_error(time_ms=1200, prior_times_ms=BASELINE_TIMES)
    assert c.label == d.KNOWLEDGE_GAP
    assert c.confidence <= 0.3
    assert d.ATTENTION_LAPSE in c.alternatives
    assert d.COMPREHENSION_BARRIER in c.alternatives


def test_classifier_abstains_with_too_few_focus_samples():
    """Focus data below MIN_FOCUS_SAMPLES is not trustworthy even if a ratio
    number exists — must be treated the same as no data at all."""
    c = d.classify_error(time_ms=1200, prior_times_ms=BASELINE_TIMES, focus_ratio=0.2, focus_samples=2)
    assert c.label == d.KNOWLEDGE_GAP
    assert c.confidence <= 0.3


def test_hesitation_narrows_abstention_toward_attention_lapse():
    """A long pre-interaction freeze followed by a fast final answer, with no
    focus data, narrows the abstention's alternatives toward ATTENTION_LAPSE
    rather than treating both candidates as equally likely — froze-then-
    guessed looks more like disengagement than a stable knowledge gap."""
    c = d.classify_error(
        time_ms=1200, prior_times_ms=BASELINE_TIMES, time_to_first_interaction_ms=900,
    )
    assert c.label == d.KNOWLEDGE_GAP
    assert c.alternatives == [d.ATTENTION_LAPSE]


def test_normal_timing_with_no_signals_is_knowledge_gap_with_moderate_confidence():
    c = d.classify_error(time_ms=5100, prior_times_ms=BASELINE_TIMES)
    assert c.label == d.KNOWLEDGE_GAP
    assert c.confidence > 0.5


def test_thin_baseline_caps_confidence_even_on_a_clear_processing_delay():
    c_thin = d.classify_error(time_ms=12000, prior_times_ms=[5000.0])
    c_rich = d.classify_error(time_ms=12000, prior_times_ms=BASELINE_TIMES)
    assert c_thin.confidence <= c_rich.confidence


# ─────────────── item-length normalization (G10) ───────────────
# A long item's stem + options simply take longer to READ, independent of
# hesitation or attention — without subtracting an estimated reading-time
# floor first, a long item could read as a processing delay purely because
# reading it took a while, never because the student was actually slow
# relative to their own baseline.


def test_long_time_without_word_count_reads_as_processing_delay():
    """Baseline for the next test: the exact same raw time, with no item
    length supplied (item_word_count defaults to 0, i.e. no adjustment —
    identical to this classifier's behaviour before G10)."""
    c = d.classify_error(time_ms=11000, prior_times_ms=BASELINE_TIMES)
    assert c.label == d.PROCESSING_DELAY


def test_item_word_count_normalizes_away_a_false_processing_delay():
    """Same raw time (11000ms) and the same baseline as the test above, but
    this item's stem + options are 30 words long — a ~9000ms reading floor
    at 300ms/word. Once that's subtracted, the student's actual (post-
    reading) response time is 2000ms, a FAST answer relative to their
    5000ms baseline, not a slow one — the opposite classification from the
    unadjusted case, which is exactly the false positive G10 exists to fix."""
    c = d.classify_error(time_ms=11000, prior_times_ms=BASELINE_TIMES, item_word_count=30)
    assert c.label != d.PROCESSING_DELAY
    assert c.signals["itemWordCount"] == 30
    assert c.signals["readingFloorMs"] == 9000
    assert c.signals["adjustedTimeMs"] == 2000


def test_should_represent_true_only_for_confident_comprehension_barrier():
    confident = d.Classification(d.COMPREHENSION_BARRIER, 0.6)
    weak = d.Classification(d.COMPREHENSION_BARRIER, 0.2)
    wrong_label = d.Classification(d.KNOWLEDGE_GAP, 0.9)
    assert d.should_represent(confident) is True
    assert d.should_represent(weak) is False
    assert d.should_represent(wrong_label) is False
