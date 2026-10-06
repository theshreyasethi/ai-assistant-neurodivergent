"""Contract test — roadmap P3-09.

Audit finding S03: the frontend was measuring and sending real telemetry
signals (answerChanges, timeToFirstInteractionMs, classification, ...) but
nothing proved the backend actually accepted and used them. A schema change
on either side could silently drop a field — Pydantic ignores unknown keys
by default — and neither side would know until a teacher's dashboard quietly
stopped showing a parameter.

question_event_from_quizpage.json is a fixture shaped exactly like the
object frontend/src/pages/QuizPage.tsx's `track()` call constructs after the
P3-01/P3-03 changes (every field name and nesting matches the TypeScript
QuestionEvent interface in frontend/src/services/telemetry.ts field-for-
field). This test is the tripwire: if a future change renames a field on
either side, this is where it breaks.
"""

import json
from pathlib import Path

from models.schemas import QuestionEvent
from services import dase_engine as d

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "question_event_from_quizpage.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_frontend_shaped_event_carries_measured_signals():
    """Would have caught the hard-coded telemetry (S03): before P3-01, the
    frontend sent `answerChanges: 0` and `timeToFirstInteractionMs: null`
    literally for every question, which validates just as happily as the
    real fixture and would have passed this test for the wrong reason — the
    assertions here specifically check the MEASURED values are non-trivial,
    not merely present."""
    raw = load_fixture()
    assert raw["answerChanges"] == 2
    assert raw["timeToFirstInteractionMs"] == 612
    assert raw["reRead"] is True
    assert raw["revisits"] == 1


def test_frontend_shaped_event_parses_as_a_question_event():
    raw = load_fixture()
    event = QuestionEvent(**raw)
    assert event.questionId == "q3"
    assert event.correct is False
    assert event.classification is not None
    assert event.classification.label == "KNOWLEDGE_GAP"


def test_frontend_shaped_event_reaches_the_engine_and_is_classified():
    """The full round trip: parse into the Pydantic model, dump back to a
    plain dict (the exact transform routers/telemetry.py applies before
    writing to Firestore), and feed it to compute_parameters/error_breakdown —
    the classification the client attached must survive every hop."""
    raw = load_fixture()
    event = QuestionEvent(**raw).model_dump()

    params = d.compute_parameters([event])
    assert "ACC" in params  # one answered event, even though it's wrong

    breakdown = d.error_breakdown([event])
    assert breakdown["counts"]["KNOWLEDGE_GAP"] == 1
    assert breakdown["unclassified"] == 0


def test_additive_fields_are_optional_so_an_older_client_still_validates():
    """classification/classifierVersion/itemKind/degraded must be additive —
    an event from a client that predates these fields (or simply a correct
    answer, which never gets classified) has to keep validating, per the
    frozen-contract rule in DATA_CONTRACT.md."""
    raw = load_fixture()
    minimal = {k: v for k, v in raw.items() if k not in ("classification", "classifierVersion", "itemKind")}
    event = QuestionEvent(**minimal)
    assert event.classification is None
    assert event.itemKind is None
    assert event.degraded is False
