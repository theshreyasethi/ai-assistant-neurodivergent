"""Auto-pacing: personal reading speed and replay behaviour -> a suggested
TTS/highlight rate (roadmap P4-13).

Constants (0.7/0.3 EMA blend, 0.9 replay penalty, 80-300 wpm clamp) are
literature-informed, UNVALIDATED assumptions — name them as such, tune in
the pilot. This module only ever SUGGESTS a rate; frontend/src/hooks/
useAutoPacing.ts presents it as "Shall I read slower?" rather than silently
changing anything, and never speeds a student up automatically for a
profile where slower is the expected, accommodated pace.
"""

from __future__ import annotations

from typing import Optional

DEFAULT_WPM = 170.0
MIN_WPM = 80.0
MAX_WPM = 300.0
_EMA_PREV_WEIGHT = 0.7
_EMA_OBSERVED_WEIGHT = 0.3
_HIGH_REPLAY_RATE = 0.3
_REPLAY_SLOWDOWN = 0.9


def observed_wpm(words_read: int, elapsed_ms: int, paused_ms: int = 0) -> Optional[float]:
    """None below a floor where the measurement is too noisy to trust (a
    few words read in a couple of seconds says nothing about pace)."""
    active_ms = elapsed_ms - paused_ms
    if words_read < 20 or active_ms <= 1000:
        return None
    return words_read / (active_ms / 60000)


def next_wpm(previous_wpm: float, observed: Optional[float], replay_rate: float = 0.0) -> float:
    """One slow or fast session must not whip-saw the suggested rate — the
    EMA blend means it takes several sessions of a consistent pace to move
    far from where a student already is."""
    if observed is None:
        return _clamp(previous_wpm)
    ema = _EMA_PREV_WEIGHT * previous_wpm + _EMA_OBSERVED_WEIGHT * observed
    if replay_rate > _HIGH_REPLAY_RATE:
        # Re-listening to >30% of sentences is a signal the current rate is
        # already too fast for comfort, independent of the raw wpm measured.
        ema *= _REPLAY_SLOWDOWN
    return _clamp(ema)


def _clamp(wpm: float) -> float:
    return max(MIN_WPM, min(MAX_WPM, wpm))


def soft_prompt_after_ms(personal_median_ms: float) -> float:
    """A gentle "want a hint?" nudge point — never a timeout. Three times the
    student's own median response time is long enough that a prompt this
    early would almost never interrupt someone who is simply still reading
    the question."""
    return 3.0 * personal_median_ms
