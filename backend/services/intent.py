"""Voice command intent matching.

Rule-first by design. Three reasons:

  1. Speed — a blind student waiting 1.5s for an LLM round trip to hear "going to
     your quizzes" is a worse experience than a screen reader.
  2. Cost — the Gemini free tier is 5 requests/minute. A voice layer that called
     the LLM per utterance would exhaust the quota in under a minute of use.
  3. Reliability — the ~20 core commands are a closed set. Regex is exactly right
     for a closed set, and it cannot hallucinate a navigation target.

The LLM is the fallback for phrasings the rules miss, not the primary path.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# ─────────────── intents ───────────────

NAVIGATE = "NAVIGATE"
READ_NEXT = "READ_NEXT"
READ_PREVIOUS = "READ_PREVIOUS"
READ_ALL = "READ_ALL"
REPEAT = "REPEAT"
STOP = "STOP"
DESCRIBE_PAGE = "DESCRIBE_PAGE"
EXPLAIN = "EXPLAIN"
PROGRESS = "PROGRESS"
HELP = "HELP"
FASTER = "FASTER"
SLOWER = "SLOWER"
ANSWER = "ANSWER"
SUBMIT = "SUBMIT"
SKIP_QUESTION = "SKIP_QUESTION"
EXIT_QUIZ = "EXIT_QUIZ"
PLAY = "PLAY"
SET_WPM = "SET_WPM"
UNKNOWN = "UNKNOWN"

ROUTES = {
    "dashboard": "/student-dashboard",
    "quiz": "/quiz",
    "learning": "/learning",
    "upload": "/upload",
    "content": "/content",
    "teacher": "/teacher-dashboard",
}

# Spoken option names -> zero-based index. A blind student cannot click, so
# answering by voice is not a convenience here, it is the only route in.
# "true"/"false" map onto the same 0/1 slots as a/first and b/second since
# services/quiz_gen.py always renders true_false questions as
# options=["True", "False"] in that order.
_OPTION_WORDS = {
    "a": 0, "first": 0, "one": 0, "1": 0, "true": 0,
    "b": 1, "second": 1, "two": 1, "2": 1, "false": 1,
    "c": 2, "third": 2, "three": 2, "3": 2,
    "d": 3, "fourth": 3, "four": 3, "4": 3,
}


@dataclass
class Intent:
    name: str
    slots: Dict[str, Any]
    confidence: float
    source: str  # "rules" | "llm" | "none"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.name,
            "slots": self.slots,
            "confidence": round(self.confidence, 2),
            "source": self.source,
        }


# Order matters: the first pattern that matches wins, so put the urgent and the
# unambiguous first. STOP must come before everything — a student saying "stop"
# while the page is talking needs it honoured immediately, not parsed as a topic.
_RULES: List[tuple] = [
    (STOP, re.compile(r"\b(stop|quiet|silence|shut up|be quiet|pause|cancel|nevermind|never mind)\b")),

    (HELP, re.compile(r"\b(help|what can (i|you) (say|do)|commands|options available)\b")),

    (PROGRESS, re.compile(
        r"\b(my )?(progress|score|how (am i|i am) doing|how did i do|results?|marks)\b")),

    (DESCRIBE_PAGE, re.compile(
        r"\b(what('s| is) (on |in )?(this |the )?(page|screen)|where am i|describe( the)?"
        r"( page| screen)?|what can i do here)\b")),

    (EXPLAIN, re.compile(
        r"\b(explain|what does (this|that) mean|i don'?t understand|simpler|"
        r"say (that )?(again )?(in )?(simpler|easier)|break (it|this) down)\b")),

    (READ_NEXT, re.compile(
        r"\b(read (the )?next|next (paragraph|sentence|part|section|bit)|continue|"
        r"carry on|go on|keep reading)\b")),

    (READ_PREVIOUS, re.compile(
        r"\b(read (the )?(previous|last)|previous (paragraph|sentence|part|section)|"
        r"go back|back up)\b")),

    (REPEAT, re.compile(r"\b(repeat|say (that|it) again|again|once more|pardon|what)\b")),

    (READ_ALL, re.compile(
        r"\b(read (it |this |the )?(all|everything|whole|page|aloud)|start reading|read to me)\b")),

    (FASTER, re.compile(r"\b(faster|speed up|quicker|too slow)\b")),
    (SLOWER, re.compile(r"\b(slower|slow down|too fast)\b")),

    (SUBMIT, re.compile(r"\b(submit|confirm|next question|done|that'?s my answer|lock it in)\b")),

    # Blind/voice-first students have no "Skip" or "Exit" button to click —
    # these are the only route to either action (same reasoning as ANSWER).
    (SKIP_QUESTION, re.compile(
        r"\bskip\b(\s+(this|that|the)\s+question)?|\bpass\b\s+(this|on this)\s+question\b")),
    (EXIT_QUIZ, re.compile(r"\b(exit|quit|leave)\b(\s+(this|the))?\s*quiz\b|\b(exit|quit)\b")),

    # Resume reading from wherever it was paused/stopped — deliberately NOT
    # "continue"/"carry on" (those are already READ_NEXT, advancing a
    # sentence) and deliberately NOT reusing STOP's "pause" word (STOP must
    # stay exactly as-is). The page itself (LearningPage) is what actually
    # knows "wherever it was" by keeping currentSentenceIndex untouched.
    (PLAY, re.compile(r"\b(play|resume( reading)?|unpause|keep playing)\b")),
]

# "go to X" / "open X" / "take me to X"
_NAV_RE = re.compile(
    r"\b(go|navigate|take me|open|show me|switch)\b.*?\b"
    r"(dashboard|home|quiz|quizzes|test|lesson|lessons|learning|read|reading|"
    r"upload|content|material|materials|teacher)\b"
)
_NAV_TARGETS = {
    "dashboard": "dashboard", "home": "dashboard",
    "quiz": "quiz", "quizzes": "quiz", "test": "quiz",
    "lesson": "learning", "lessons": "learning", "learning": "learning",
    "read": "learning", "reading": "learning",
    "upload": "upload",
    "content": "content", "material": "content", "materials": "content",
    "teacher": "teacher",
}

# Fixed multi-word phrases that don't fit the "<verb> ... <target>" cross
# product above. They're matched as whole phrases, deliberately NOT by
# adding their lead word ("upload", "manage", "start", "begin") to _NAV_RE's
# shared verb group — "start"/"begin" paired with EVERY existing target
# would also pair with "read"/"reading", and "start reading" is already
# READ_ALL's own phrase (_RULES below). Checked at the same priority as
# _NAV_RE, before the generic _RULES loop.
def _direct_nav_target(cleaned: str) -> Optional[str]:
    if re.search(r"\bupload (?:a |my |the )?pdf\b|\bupload file\b", cleaned):
        return "upload"
    if re.search(r"\bmanage content\b", cleaned):
        return "content"
    if re.search(r"\b(?:start|begin) (?:my |the )?(?:learning|lesson|lessons)\b", cleaned):
        return "learning"
    return None


# "make wpm 200" / "set reading speed to 250" / "change wpm to 150" / "200 wpm"
_WPM_RE = re.compile(
    r"\b(?:wpm|reading speed)\b(?:\s*(?:to|at|of))?\s*(\d{2,3})\b"
    r"|\b(\d{2,3})\s*wpm\b"
)

# "answer B" / "choose the second one" / "select option 3" / "answer true"
_ANSWER_RE = re.compile(
    r"\b(answer|choose|select|pick|option|number)\b\s*"
    r"(?:is\s+|the\s+)?(?:option\s+|number\s+)?"
    r"\b([abcd]|first|second|third|fourth|one|two|three|four|[1-4]|true|false)\b"
)
# bare "B", "option two", "true" or "false" with nothing else said
_BARE_OPTION_RE = re.compile(
    r"^\s*(?:option\s+)?([abcd]|[1-4]|first|second|third|fourth|true|false)\s*$"
)


def normalise(text: str) -> str:
    return re.sub(r"[^\w\s']", " ", (text or "").lower()).strip()


def match_rules(text: str) -> Optional[Intent]:
    """Try the rule set. Returns None when nothing matches, so the caller can
    decide whether the LLM fallback is worth a request."""
    cleaned = normalise(text)
    if not cleaned:
        return None

    # Answering a question takes priority over navigation: "take option two"
    # contains "take" but is clearly an answer.
    answer = _ANSWER_RE.search(cleaned) or _BARE_OPTION_RE.match(cleaned)
    if answer:
        word = answer.group(answer.lastindex or 1)
        if word in _OPTION_WORDS:
            return Intent(ANSWER, {"optionIndex": _OPTION_WORDS[word]}, 0.95, "rules")

    nav = _NAV_RE.search(cleaned)
    if nav:
        target = _NAV_TARGETS.get(nav.group(2))
        if target:
            return Intent(
                NAVIGATE, {"target": target, "path": ROUTES[target]}, 0.95, "rules"
            )

    direct_target = _direct_nav_target(cleaned)
    if direct_target:
        return Intent(
            NAVIGATE, {"target": direct_target, "path": ROUTES[direct_target]}, 0.95, "rules"
        )

    wpm_match = _WPM_RE.search(cleaned)
    if wpm_match:
        wpm_str = wpm_match.group(1) or wpm_match.group(2)
        try:
            wpm = int(wpm_str)
        except (TypeError, ValueError):
            wpm = None
        if wpm is not None and 50 <= wpm <= 500:
            return Intent(SET_WPM, {"wpm": wpm}, 0.95, "rules")

    for name, pattern in _RULES:
        if pattern.search(cleaned):
            return Intent(name, {}, 0.9, "rules")

    # Bare destination with no verb: "quiz", "dashboard"
    for word, target in _NAV_TARGETS.items():
        if cleaned == word:
            return Intent(NAVIGATE, {"target": target, "path": ROUTES[target]}, 0.8, "rules")

    return None


HELP_TEXT = (
    "You can say: go to my quizzes, go to my lessons, go to my dashboard, "
    "upload a pdf, or manage content. "
    "While reading, say read next, read previous, repeat, read everything, "
    "play or resume, or pause. "
    "Say make my reading speed 200 WPM to set an exact reading speed, or say "
    "faster or slower to nudge it. "
    "Say explain this if something is unclear, or what is on this page to hear a description. "
    "In a quiz, say answer A, answer B, answer C or answer D, or true or false, then say submit. "
    "Say skip this question to move on without answering, or exit quiz to leave the quiz. "
    "Say stop at any time to make me quiet."
)

LLM_SYSTEM = f"""You classify a blind student's spoken command in a learning app.

Reply with ONLY a JSON object: {{"intent": "...", "slots": {{}}}}

Valid intents: {NAVIGATE}, {READ_NEXT}, {READ_PREVIOUS}, {READ_ALL}, {REPEAT}, {STOP},
{DESCRIBE_PAGE}, {EXPLAIN}, {PROGRESS}, {HELP}, {FASTER}, {SLOWER}, {ANSWER}, {SUBMIT},
{SKIP_QUESTION}, {EXIT_QUIZ}, {PLAY}, {SET_WPM}, {UNKNOWN}

For {NAVIGATE}, slots must be {{"target": one of dashboard|quiz|learning|upload|content|teacher}}.
For {ANSWER}, slots must be {{"optionIndex": 0|1|2|3}}.
For {SET_WPM}, slots must be {{"wpm": an integer between 50 and 500}}.
All other intents take empty slots.

The input is speech-to-text output, so expect mis-recognition. If you cannot tell what
was meant, return {UNKNOWN} — do NOT guess a navigation target, because sending a blind
student to the wrong page is worse than admitting you did not understand.
"""


def classify(text: str, allow_llm: bool = True) -> Intent:
    """Rules first, LLM only if they miss and it is permitted."""
    hit = match_rules(text)
    if hit:
        return hit

    if not allow_llm:
        return Intent(UNKNOWN, {}, 0.0, "none")

    try:
        from services.llm import call_json

        raw = call_json(LLM_SYSTEM, f"Command: {text}")
        name = str(raw.get("intent", UNKNOWN)).upper()
        slots = raw.get("slots") or {}

        if name == NAVIGATE:
            target = slots.get("target")
            if target not in ROUTES:
                return Intent(UNKNOWN, {}, 0.0, "llm")
            slots = {"target": target, "path": ROUTES[target]}
        elif name == ANSWER:
            try:
                idx = int(slots.get("optionIndex", -1))
            except (TypeError, ValueError):
                return Intent(UNKNOWN, {}, 0.0, "llm")
            if not 0 <= idx <= 3:
                return Intent(UNKNOWN, {}, 0.0, "llm")
            slots = {"optionIndex": idx}
        elif name == SET_WPM:
            try:
                wpm = int(slots.get("wpm", -1))
            except (TypeError, ValueError):
                return Intent(UNKNOWN, {}, 0.0, "llm")
            if not 50 <= wpm <= 500:
                return Intent(UNKNOWN, {}, 0.0, "llm")
            slots = {"wpm": wpm}
        else:
            slots = {}

        if name == UNKNOWN:
            return Intent(UNKNOWN, {}, 0.0, "llm")
        # LLM results are trusted less than a rule hit, and the gap is visible in
        # the VOICE_Q telemetry parameter.
        return Intent(name, slots, 0.6, "llm")
    except Exception as exc:  # noqa: BLE001
        print(f"[intent] LLM fallback unavailable: {exc}")
        return Intent(UNKNOWN, {}, 0.0, "none")
