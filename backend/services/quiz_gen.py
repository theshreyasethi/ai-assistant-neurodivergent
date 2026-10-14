"""LLM quiz generation, merging two things each branch built separately:

  - `main` built THREE question types (mcq / true_false / fill_blank) in a
    fixed 3/3/3 distribution, with per-type schema validation.
  - `master` built disability-adapted item FORMATS (no spatial items for
    blind, minimal reading load for deaf, etc.), topic/conceptId tagging, and
    a simpler variant of every item for the Phase-2-style comprehension-
    barrier closed loop.

These are not in conflict — a deaf student still benefits from a mix of
question types, just phrased and formatted for them. Both compose into one
generation call.
"""

import random
import re
from typing import Dict, List, Optional

from services.cache import get_or_compute, make_key
from services.llm import LLMUnavailable, call_json

QUESTION_TYPES = ("mcq", "true_false", "fill_blank")
# Autism/PATTERN (roadmap P3-07): items the LLM tags as testing sequencing,
# categorisation or matching rather than plain recall — a relative strength
# the DASE engine surfaces separately instead of folding into ACC.
ITEM_KINDS = ("sequence", "category", "matching", "recall")

BASE_RULES = """You write questions that test whether a student understood a lesson.

RULES:
1. Every question must be answerable from the given text alone.
2. Generate EXACTLY 9 questions: 3 "mcq", 3 "true_false", 3 "fill_blank". Shuffle the
   array — do not group by type.
3. Per-type format:
   - mcq: "options" has exactly 4 choices, one correct. Distractors are the same KIND
     of thing as the answer and similar in length. Never make the correct option the
     longest.
   - true_false: "options" is exactly ["True", "False"]. "answer" is "True" or "False".
   - fill_blank: "question" contains "______" for the blank. "options" has exactly 4
     choices (the answer plus 3 plausible distractors).
4. Test understanding, not word-matching. Do not just copy a sentence and blank a word.
5. `topic` is a 2-5 word standardized academic category (e.g. "Cell Biology",
   "Gravity & Motion") — never quote raw words from the passage.
6. `conceptId` is a short snake_case id, reused across questions testing the same concept.
7. `difficulty` is 1 (recall) to 5 (applies the idea to a new situation).
8. Provide a SIMPLER VARIANT of each question: same concept, easier wording, shorter
   sentences, more obviously-wrong distractors, SAME question_type as the original.
   It is shown to a student who did not understand the original phrasing.
9. The simpler variant must obey the STUDENT PROFILE rules below at least as strictly
   as the main question — it is read by the SAME student, already struggling. Never
   introduce abbreviations, symbols, or compressed notation in the simpler variant.
10. Tag `itemKind`: "sequence" if answering requires ordering events/steps, "category"
    if it requires grouping/classifying something, "matching" if it pairs related
    items, otherwise "recall". Be honest — most items are "recall".
"""

FORMATS: Dict[str, str] = {
    "default": "Use clear, standard phrasing.",
    "blind": """This student is blind and will HEAR the question read aloud.
- Never reference diagrams, images, colours, positions or layout.
- No spatial or geometric reasoning items.
- Spell out symbols in words ("percent", not "%").
- Keep each option under 12 words and easy to tell apart by ear.""",
    "deaf": """This student is Deaf and reads at a lower grade level than their age.
- Keep the question stem under 15 words. Use common concrete words only.
- No idioms, metaphors or figurative language anywhere.
- Prefer questions about relationships, sequences, matching and categories.
- Keep every option under 8 words.""",
    "dyslexia": """This student has dyslexia.
- Question stem under 15 words, short simple sentences. Options under 8 words each.
- Options must not look alike — avoid near-identical spellings.
- No double negatives and no "which is NOT" phrasing.""",
    "adhd": """This student has ADHD.
- One-step questions only. Stem under 15 words, key term easy to spot.
- No "all of the above" or "none of the above".""",
    "autism": """This student is autistic.
- Completely literal and unambiguous. No figurative language.
- Exactly one defensibly correct answer — never "which is the BEST answer".
- Use the same term for a concept as the lesson used.""",
    "dyscalculia": """This student has dyscalculia.
- Break any calculation into a single step per question.
- State what each number counts. Use words instead of notation.
- If the passage contains ANY arithmetic, a word problem, or a quantity that
  can be computed (a total, a difference, a count, a measurement), AT LEAST
  ONE "fill_blank" question MUST test that calculation directly, and its
  `answer` MUST be a bare number only (e.g. "42", never "42 apples" or
  "forty-two") so on-screen math tools can recognise and assist with it.""",
    "intellectual": """This student has an intellectual disability.
- Stem under 10 words. Only the most common everyday words.
- Test one concrete fact directly stated in the lesson.""",
    "anxiety": """This student finds tests stressful.
- Neutral, encouraging phrasing. No trick questions, no negative framing.
- Never use "NOT", "EXCEPT" or double negatives.""",
    "hard_of_hearing": """This student is hard of hearing and reads somewhat
below grade level for reasons unrelated to subject understanding.
- Keep the question stem under 16 words. Avoid idioms and figurative language.
- Prefer questions about relationships, sequences, matching and categories.""",
    "low_vision": """This student has low vision and reads with magnification.
- Keep each option short (under 10 words) and easy to tell apart without
  needing to compare fine visual detail.
- Never reference colour, position or layout ("the diagram above").""",
    "dysgraphia": """This student has dysgraphia — a writing-output difficulty,
not a comprehension one.
- Prefer mcq/true_false over fill_blank; when fill_blank is used it MUST have
  a usable options array (never rely on free-text recall of spelling).
- Never penalise answer phrasing — options should be unambiguous single words
  or short phrases, not near-synonyms the student would need to compose.""",
    "motor": """This student has a motor/mobility difficulty — selecting
options is slow/effortful, not understanding them.
- Prefer single-select mcq/true_false. If fill_blank is used, options MUST be
  provided (never a type-the-answer-only item).
- Keep the number of options at exactly 4 — no more targets to aim at than
  necessary.""",
}

SCHEMA_HINT = """Return ONLY a JSON array of 9 objects, each exactly:
{
  "question": "string",
  "options": ["string", ...],
  "answer": "string (must be character-for-character one of the options)",
  "question_type": "mcq" | "true_false" | "fill_blank",
  "topic": "string",
  "conceptId": "snake_case_string",
  "difficulty": 1,
  "explanation": "one sentence saying why the answer is right",
  "itemKind": "sequence" | "category" | "matching" | "recall",
  "simplerQuestion": "string",
  "simplerOptions": ["string", ...],
  "simplerAnswer": "string (must be one of simplerOptions)"
}"""


# Arithmetic word-problem detector for the dyscalculia prompt-reinforcement
# below: digits plus either an operator symbol or a common calculation verb
# ("how many", "total", "sum", ...) anywhere in the passage. Deliberately
# permissive — a false positive just adds a sentence the LLM was going to
# follow anyway; a false negative is the bug this exists to avoid.
_ARITHMETIC_RE = re.compile(
    r"\d+\s*[-+*/x×÷]\s*\d+"
    r"|\b(sum|total|difference|product|quotient|how many|how much|calculate|"
    r"add(?:s|ed|ing)?|subtract(?:s|ed|ing)?|multiply|multiplied|divide[sd]?|"
    r"altogether|remain(?:s|ing)?|left over)\b",
    re.IGNORECASE,
)


def _has_arithmetic_content(text: str) -> bool:
    return bool(re.search(r"\d", text)) and bool(_ARITHMETIC_RE.search(text))


def _type_options_valid(qtype: str, options: List[str]) -> bool:
    if qtype == "true_false":
        return {o.strip() for o in options} == {"True", "False"}
    if qtype == "mcq":
        return len(options) == 4
    if qtype == "fill_blank":
        return len(options) == 4
    return False


def _valid(item: dict) -> bool:
    """Reject malformed items rather than serving a broken question. The most
    damaging failure is an `answer` not among `options` — the student cannot
    possibly get it right, and would be scored on a generator bug."""
    try:
        qtype = str(item.get("question_type", "")).strip()
        if qtype not in QUESTION_TYPES:
            return False

        options = item["options"]
        if not isinstance(options, list) or not _type_options_valid(qtype, options):
            return False
        if len({str(o).strip().lower() for o in options}) != len(options):
            return False  # duplicate options
        if str(item["answer"]).strip() not in [str(o).strip() for o in options]:
            return False
        if not str(item.get("question", "")).strip():
            return False
        if qtype == "fill_blank" and "______" not in str(item["question"]):
            return False

        simpler = item.get("simplerOptions")
        if isinstance(simpler, list) and simpler:
            if not _type_options_valid(qtype, simpler):
                return False
            if str(item.get("simplerAnswer", "")).strip() not in [str(o).strip() for o in simpler]:
                return False
        return True
    except (KeyError, TypeError):
        return False


def _normalise(item: dict, index: int) -> dict:
    qtype = str(item["question_type"]).strip()
    options = [str(o).strip() for o in item["options"]]
    answer = str(item["answer"]).strip()

    # Shuffle so the correct answer isn't positionally predictable — but never
    # shuffle true/false, where option order is a fixed convention.
    if qtype != "true_false":
        random.shuffle(options)

    simpler_options = [str(o).strip() for o in item.get("simplerOptions") or []]
    if simpler_options and qtype != "true_false":
        random.shuffle(simpler_options)

    difficulty = item.get("difficulty", 3)
    try:
        difficulty = max(1, min(5, int(difficulty)))
    except (TypeError, ValueError):
        difficulty = 3

    item_kind = str(item.get("itemKind") or "").strip()
    if item_kind not in ITEM_KINDS:
        item_kind = "recall"

    return {
        "questionId": f"q{index}",
        "question": str(item["question"]).strip(),
        "options": options,
        "answer": answer,
        "question_type": qtype,
        "topic": str(item.get("topic") or "").strip() or None,
        "conceptId": str(item.get("conceptId") or "").strip() or None,
        "difficulty": difficulty,
        "itemKind": item_kind,
        "explanation": str(item.get("explanation") or "").strip() or None,
        "simplerQuestion": str(item.get("simplerQuestion") or "").strip() or None,
        "simplerOptions": simpler_options or None,
        "simplerAnswer": str(item.get("simplerAnswer") or "").strip() or None,
    }


# ─────────────── fallback (LLM unreachable) ───────────────

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def _fallback_quiz(text: str, count: int) -> List[dict]:
    """spaCy generator producing all three question types round-robin, same as
    main's fallback. Marked `degraded` by the caller so results are excluded
    from any DASE analysis — a poor quiz beats a broken page, but its data
    should not be trusted."""
    import spacy

    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        return []

    doc = nlp(text)
    pool = [t.text for t in doc if t.pos_ in ("NOUN", "VERB", "ADJ")]
    eligible = [s for s in doc.sents if len(s.text.split()) > 5]
    items: List[dict] = []

    for i, sent in enumerate(eligible):
        if len(items) >= count:
            break
        blanks = [t.text for t in sent if t.pos_ in ("NOUN", "VERB", "ADJ")]
        if not blanks:
            continue
        blank = random.choice(blanks)
        chunks = [c.text.title() for c in sent.as_doc().noun_chunks if len(c.text.split()) >= 2]
        topic = chunks[0] if chunks else "General Knowledge"

        qtype = QUESTION_TYPES[i % 3]
        if qtype == "fill_blank":
            distractors = [w for w in dict.fromkeys(pool) if w.lower() != blank.lower()]
            random.shuffle(distractors)
            options = [blank] + distractors[:3]
            if len(options) < 4:
                continue
            random.shuffle(options)
            items.append({
                "questionId": f"q{len(items)}",
                "question": sent.text.replace(blank, "______", 1),
                "options": options, "answer": blank, "question_type": "fill_blank",
                "topic": topic, "conceptId": None, "difficulty": 3, "explanation": None,
                "simplerQuestion": None, "simplerOptions": None, "simplerAnswer": None,
            })
        elif qtype == "true_false":
            items.append({
                "questionId": f"q{len(items)}",
                "question": f"True or False: {sent.text.strip()}",
                "options": ["True", "False"], "answer": "True", "question_type": "true_false",
                "topic": topic, "conceptId": None, "difficulty": 2, "explanation": None,
                "simplerQuestion": None, "simplerOptions": None, "simplerAnswer": None,
            })
        else:
            nouns = [t.text for t in sent if t.pos_ == "NOUN" and len(t.text) > 2]
            target = nouns[0] if nouns else blank
            distractors = [w for w in pool if w != target and len(w) > 2]
            random.shuffle(distractors)
            options = [target] + distractors[:3]
            if len(options) < 4:
                continue
            random.shuffle(options)
            items.append({
                "questionId": f"q{len(items)}",
                "question": f'Which term relates to: "{sent.text.strip()[:60]}"?',
                "options": options, "answer": target, "question_type": "mcq",
                "topic": topic, "conceptId": None, "difficulty": 3, "explanation": None,
                "simplerQuestion": None, "simplerOptions": None, "simplerAnswer": None,
            })
    return items


# ─────────────── entry point ───────────────


def generate_quiz(
    text: str,
    profile: str = "default",
    count: int = 9,
    grade_level: Optional[str] = None,
) -> dict:
    text = (text or "").strip()
    if not text:
        return {"questions": [], "profile": profile, "degraded": False}

    if profile not in FORMATS:
        profile = "default"

    def compute() -> List[dict]:
        system = f"{BASE_RULES}\nSTUDENT PROFILE:\n{FORMATS[profile]}\n\n{SCHEMA_HINT}"
        if grade_level:
            system += f"\n\nThis student reads at grade level {grade_level}. Keep vocabulary appropriate."
        # Reinforced, not just stated once in FORMATS["dyscalculia"] — this
        # passage demonstrably has arithmetic in it, so skipping a numeric
        # fill_blank item here would be the generator ignoring content that's
        # actually there, not a passage that simply had nothing to calculate.
        if profile == "dyscalculia" and _has_arithmetic_content(text):
            system += (
                "\n\nThis passage contains arithmetic. At least one \"fill_blank\" "
                "question MUST be a calculation based on numbers in the passage, "
                "with a bare numeric `answer` (digits only, no units or words)."
            )
        # retries=2: the merged schema (9 questions x full disability-format
        # fields x a per-item simpler-variant) is large enough that Gemini
        # occasionally emits a malformed field even when otherwise on-topic;
        # one repair attempt wasn't enough headroom before falling back to spaCy.
        raw = call_json(system, f"Passage:\n\n{text[:8000]}", retries=2)
        if not isinstance(raw, list):
            raw = raw.get("questions", []) if isinstance(raw, dict) else []
        return [_normalise(it, i) for i, it in enumerate(q for q in raw if _valid(q))]

    key = make_key(text, profile, str(count), str(grade_level or ""))
    try:
        questions = get_or_compute("quiz_cache", key, compute)
        degraded = False
    except LLMUnavailable as exc:
        print(f"[quiz_gen] LLM unavailable, falling back to spaCy: {exc}")
        questions, degraded = _fallback_quiz(text, count), True

    if not questions:
        questions, degraded = _fallback_quiz(text, count), True

    return {"questions": questions[: max(count, 9)], "profile": profile, "degraded": degraded}
