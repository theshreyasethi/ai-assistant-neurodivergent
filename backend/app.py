from config import CORS_ORIGINS, GOOGLE_API_KEY, GEMINI_MODEL

from fastapi import FastAPI, File, UploadFile, Form, Body, Depends, HTTPException
from PyPDF2 import PdfReader
import io
import json
import re
import traceback
from firebase_config import db
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from cachetools import TTLCache
import threading
from starlette.concurrency import run_in_threadpool
from ingestion import ingest, retrieve
from datetime import datetime, timezone
from models.schemas import TurnSentiment, ChatbotResponse, QuizResultLog, SessionTelemetryLog, CreateUserRequest

# Extracted to auth.py during the master/main integration so the new DASE/
# telemetry/voice routers can require the same real token verification
# without importing back into this file.
from auth import require_active_user, require_teacher_of, verify_role
from services import accounts, image_describer, nlp_simplify, quiz_gen

app = FastAPI()

# Hard-coded ADMIN_EMAIL/ADMIN_PASSWORD constants and an automatic
# _seed_demo_data() call used to live here, run on every process start, in
# every deployment (patent-readiness audit finding A04). Removed. To get a
# first admin account, run `python scripts/create_admin.py` out-of-band; to
# seed a local development roster of demo teachers/students, run
# `python scripts/seed_demo.py` explicitly (it refuses to run at all unless
# ENV != production, and reads its passwords from environment variables —
# never from a literal in source). Every other account is created through
# POST /api/admin/users (routers/admin.py / services/accounts.py), which
# validates the assigned teacher server-side and generates its own
# temporary password rather than accepting one from the caller.

SAFE_FALLBACK = (
    "Let's focus on our reading material together! "
    "What else would you like to explore in the text?"
)

_INJECTION_PATTERNS = re.compile(
    r"(?i)"
    r"(?:ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions)"
    r"|(?:disregard\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|rules|prompts))"
    r"|(?:you\s+are\s+now\s+(?:a|an|in)\b)"
    r"|(?:act\s+as\s+(?:a|an)\b)"
    r"|(?:pretend\s+(?:you(?:'re|\s+are)\s+))"
    r"|(?:bypass\s+(?:safety|content|filter|guardrail))"
    r"|(?:jailbreak)"
    r"|(?:do\s+anything\s+now)"
    r"|(?:system\s*:\s)"
    r"|(?:\bDAN\b)"
)

_PII_EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}")
_PII_PHONE = re.compile(
    r"(?<!\d)"
    r"(?:\+?\d{1,3}[\s.-]?)?"
    r"(?:\(?\d{3}\)?[\s.-]?)"
    r"\d{3}[\s.-]?\d{4}"
    r"(?!\d)"
)
_PII_ZIP = re.compile(r"\b\d{5}(?:-\d{4})?\b")

_TOXIC_PHRASES = re.compile(
    r"(?i)"
    r"(?:kill\s+(?:yourself|your\s*self|him|her|them))"
    r"|(?:you\s+(?:are|'re)\s+(?:stupid|dumb|worthless|an?\s+idiot))"
    r"|(?:self[- ]?harm)"
    r"|(?:suicide\s+(?:method|how\s+to))"
    r"|(?:nobody\s+(?:loves|cares\s+about)\s+you)"
    r"|(?:you\s+deserve\s+to\s+(?:die|suffer))"
    r"|(?:shut\s+up\s+(?:you\s+)?(?:idiot|moron|stupid))"
)


def _sanitize_pii(text: str) -> str:
    text = _PII_EMAIL.sub("[EMAIL]", text)
    text = _PII_PHONE.sub("[PHONE]", text)
    text = _PII_ZIP.sub("[ZIP]", text)
    return text


def _validate_input(text: str) -> tuple[bool, str]:
    if _INJECTION_PATTERNS.search(text):
        return False, text
    sanitized = _sanitize_pii(text)
    return True, sanitized


def _validate_output(text: str) -> bool:
    return not _TOXIC_PHRASES.search(text)


llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    google_api_key=GOOGLE_API_KEY,
    max_tokens=2048,
    timeout=30,
    max_retries=3,
)

_sentiment_llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    google_api_key=GOOGLE_API_KEY,
    max_tokens=256,
    timeout=10,
    max_retries=1,
)

_SENTIMENT_PROMPT = (
    "You are a child-psychology tone classifier. Given a student's message and the assistant's reply, "
    "output ONLY a JSON object with exactly two keys:\n"
    '  "frustration_score": a float from 0.0 (calm) to 1.0 (very frustrated),\n'
    '  "suggested_action": one of "continue", "simplify", or "offer_break".\n'
    "Rules:\n"
    '- If frustration_score > 0.7, suggested_action MUST be "offer_break".\n'
    '- If frustration_score > 0.4, suggested_action SHOULD be "simplify".\n'
    '- Otherwise use "continue".\n'
    "Output raw JSON only. No markdown, no explanation."
)

_DEFAULT_SENTIMENT = TurnSentiment(frustration_score=0.0, suggested_action="continue")


def _score_sentiment(user_text: str, bot_reply: str) -> TurnSentiment:
    try:
        prompt = (
            f"{_SENTIMENT_PROMPT}\n\n"
            f"Student message: {user_text[:500]}\n"
            f"Assistant reply: {bot_reply[:500]}"
        )
        result = _sentiment_llm.invoke([HumanMessage(content=prompt)])
        raw = result.content.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
        return TurnSentiment(**parsed)
    except Exception:
        return _DEFAULT_SENTIMENT


_chat_history: TTLCache[str, list] = TTLCache(maxsize=256, ttl=3600)
_history_lock = threading.Lock()

_CHATBOT_SYSTEM = (
    "You are EduEase Assistant, a friendly and knowledgeable AI tutor for students. "
    "You help students understand their reading material AND answer any question they ask — "
    "including general knowledge topics such as geography, science, history, mathematics, "
    "literature, and more. Always be encouraging, accurate, and give clear, concise answers "
    "that are easy for students to understand."
)

@app.get("/")
def read_root():
    return {"message": "Welcome to the AI-Powered Easy-Learning Application"}

MAX_PDF_SIZE = 5 * 1024 * 1024
MAX_PDF_PAGES = 20


@app.post("/upload-pdf/")
async def upload_pdf(
    file: UploadFile = File(...),
    describeImages: bool = Form(False),
    _user: dict = Depends(require_active_user),
):
    pdf_data = await file.read()
    if len(pdf_data) > MAX_PDF_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 5 MB size limit")
    try:
        pdf_reader = PdfReader(io.BytesIO(pdf_data))
    except Exception:
        raise HTTPException(status_code=400, detail="File is not a valid PDF")
    if len(pdf_reader.pages) > MAX_PDF_PAGES:
        raise HTTPException(status_code=400, detail="PDF exceeds 20-page limit")
    text = ""
    for page in pdf_reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text
    if text.strip():
        chunks = await run_in_threadpool(ingest, text, file.filename or "pdf")
    else:
        chunks = 0

    # Opt-in — costs one Gemini Vision call per substantial image, only blind
    # and low-vision students need it. PdfReader is already open above, so
    # re-reading it here costs nothing extra.
    images: list[dict] = []
    if describeImages:
        images = await run_in_threadpool(image_describer.describe_pdf_images, pdf_reader)

    # totalPages lets the frontend approximate WHERE in the reading queue an
    # image's description belongs (image.page / totalPages -> a position in
    # the sentence array) — the extracted `text` itself carries no
    # page-boundary markers, so this is the only page information the
    # client has at all. See LearningPage.tsx's image-queue placement.
    return {"text": text, "chunks_ingested": chunks, "images": images, "totalPages": len(pdf_reader.pages)}

@app.post("/simplify-text/")
async def simplify_text(
    text: str = Body(...),
    profile: str = Body("default"),
    grade_level: str | None = Body(None),
    reading_difficulty: str | None = Body(None),
    _user: dict = Depends(require_active_user),
):
    """Merges two axes built separately by the two source branches: grade
    level + reading difficulty (main) and disability profile (master) — see
    services/nlp_simplify.py for how they compose into one prompt."""
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Text body is empty")
    result = await run_in_threadpool(
        nlp_simplify.simplify_text, text, profile, grade_level, reading_difficulty,
    )
    return {
        # Legacy key the current frontend reads. Keep until every caller uses `simplified`.
        "simplified_text": result["simplified"],
        **result,
    }


@app.get("/simplify-profiles/")
async def simplify_profiles(_user: dict = Depends(require_active_user)):
    return {"profiles": nlp_simplify.available_profiles()}

@app.post("/add-content/")
async def add_content(text: str = Form(...), _user: dict = Depends(require_active_user)):
    uid = _user.get("uid", "")
    try:
        doc_ref = db.collection("content").add({"text": text, "uid": uid})
        chunks = await run_in_threadpool(ingest, text, "manual")
        return {"id": doc_ref.id, "chunks_ingested": chunks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get-content/")
async def get_content(_user: dict = Depends(require_active_user)):
    uid = _user.get("uid", "")
    try:
        content = []
        docs = db.collection("content").where("uid", "==", uid).stream()
        for doc in docs:
            content.append({"id": doc.id, "text": doc.to_dict()["text"]})
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-quiz/")
async def generate_quiz(
    text: str = Body(..., embed=True),
    profile: str = Body("default", embed=True),
    grade_level: str | None = Body(None, embed=True),
    count: int = Body(9, embed=True),
    _user: dict = Depends(require_active_user),
):
    """Merges main's 3-question-type distribution (mcq/true_false/fill_blank)
    with master's disability-adapted item formats and simpler-variant
    generation — see services/quiz_gen.py."""
    return await run_in_threadpool(
        quiz_gen.generate_quiz, text, profile, max(9, min(count, 20)), grade_level,
    )

# One-line style hints folded into the RAG prompt, not a full rewrite of the
# chatbot pipeline — the disability-profile system built for simplify/quiz
# (services/nlp_simplify.py PROFILES) is a full rewrite ruleset, too heavy to
# repeat on every chat turn. This is a lighter touch: nudge the SAME
# RAG-grounded, safety-checked, sentiment-scored answer toward the right style.
_CHAT_PROFILE_HINTS: dict[str, str] = {
    "dyslexia": "Answer in short sentences, one idea each. Avoid nested clauses.",
    "deaf": "Answer in short, literal sentences. No idioms or figurative language.",
    "autism": "Be literal and direct. No sarcasm, idioms, or rhetorical questions.",
    "adhd": "Lead with the answer in the first sentence, then explain briefly.",
    "blind": "Never reference visual layout. Spell out symbols in words.",
    "dyscalculia": "Describe any numbers in concrete, countable terms.",
    "intellectual": "Use very short sentences and the simplest common words.",
    "anxiety": "Use a calm, encouraging tone. No urgency language.",
}


@app.post("/chatbot/", response_model=ChatbotResponse)
async def chatbot(
    text: str = Body(...),
    session_id: str = Body(...),
    grade_level: str | None = Body(None),
    reading_difficulty: str | None = Body(None),
    profile: str | None = Body(None),
    _user: dict = Depends(require_active_user),
):
    input_safe, sanitized_text = _validate_input(text)
    if not input_safe:
        return ChatbotResponse(
            response=SAFE_FALLBACK,
            sentiment=_DEFAULT_SENTIMENT,
        )

    try:
        context_docs = await run_in_threadpool(
            retrieve, sanitized_text, 4, grade_level, reading_difficulty,
        )
    except Exception:
        context_docs = []

    context = "\n\n".join(doc.page_content for doc in context_docs) if context_docs else ""
    style_hint = _CHAT_PROFILE_HINTS.get(profile or "", "")
    prompt_parts = []
    if context:
        prompt_parts.append(f"Context:\n{context}")
    if style_hint:
        prompt_parts.append(f"Style guidance: {style_hint}")
    prompt_parts.append(f"Question: {sanitized_text}")
    prompt = "\n\n".join(prompt_parts)

    # Build message list: system prompt + rolling conversation history + new turn
    with _history_lock:
        prior = list(_chat_history.get(session_id, []))

    messages: list = [SystemMessage(content=_CHATBOT_SYSTEM)]
    for turn in prior[-6:]:  # keep last 3 exchanges for context
        messages.append(HumanMessage(content=turn["human"]))
        messages.append(AIMessage(content=turn["ai"]))
    messages.append(HumanMessage(content=prompt))

    try:
        result = await run_in_threadpool(llm.invoke, messages)
        llm_response = result.content

        # Persist this exchange in session history
        with _history_lock:
            updated = list(_chat_history.get(session_id, []))
            updated.append({"human": sanitized_text, "ai": llm_response})
            _chat_history[session_id] = updated

    except Exception as chat_err:
        err_str = str(chat_err)
        is_rate_limit = (
            "429" in err_str
            or "resource_exhausted" in err_str.lower()
            or "quota" in err_str.lower()
        )
        if is_rate_limit:
            print("--- [CHATBOT] GEMINI API RATE LIMIT TRIGGERED ---")
            print(f"[CHATBOT QUOTA] {err_str[:200]}")
            print("-------------------------------------------------")
            return ChatbotResponse(
                response=(
                    "The assistant is temporarily at maximum capacity under Google's free-tier quota. "
                    "Please wait 60 seconds and try again — your reading session is still active."
                ),
                sentiment=_DEFAULT_SENTIMENT,
            )
        print("--- CHATBOT CRITICAL ERROR TRACEBACK ---")
        traceback.print_exc()
        print(f"[CHATBOT ERROR] llm.invoke failed: {err_str[:300]}")
        print("----------------------------------------")
        return ChatbotResponse(response=SAFE_FALLBACK, sentiment=_DEFAULT_SENTIMENT)

    if not isinstance(llm_response, str) or not llm_response.strip():
        return ChatbotResponse(
            response=SAFE_FALLBACK,
            sentiment=_DEFAULT_SENTIMENT,
        )

    if not _validate_output(llm_response):
        return ChatbotResponse(
            response=SAFE_FALLBACK,
            sentiment=_DEFAULT_SENTIMENT,
        )

    clean_response = _sanitize_pii(llm_response)
    sentiment = await run_in_threadpool(_score_sentiment, sanitized_text, clean_response)
    return ChatbotResponse(response=clean_response, sentiment=sentiment)


def _get_teacher_id(student_uid: str) -> str | None:
    try:
        snap = db.collection("users").document(student_uid).get()
        if snap.exists:
            return snap.to_dict().get("teacher_id")
    except Exception:
        pass
    return None


@app.post("/analytics/log-quiz/")
async def log_quiz(payload: QuizResultLog, _user: dict = Depends(require_active_user)):
    uid = _user.get("uid", "")
    teacher_id = await run_in_threadpool(_get_teacher_id, uid)
    try:
        entry: dict = {
            "student_id": uid,
            "score": payload.score,
            "total_questions": payload.total_questions,
            "wrong_topics": payload.wrong_topics,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if teacher_id:
            entry["teacher_id"] = teacher_id
        db.collection("quiz_results").add(entry)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "logged"}


@app.post("/analytics/log-session/")
async def log_session(payload: SessionTelemetryLog, _user: dict = Depends(require_active_user)):
    uid = _user.get("uid", "")
    teacher_id = await run_in_threadpool(_get_teacher_id, uid)
    try:
        entry: dict = {
            "student_id": uid,
            "session_id": payload.session_id,
            "average_focus_score": payload.average_focus_score,
            "frustration_triggers": payload.frustration_triggers,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if teacher_id:
            entry["teacher_id"] = teacher_id
        db.collection("telemetry_sessions").add(entry)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "logged"}


@app.post("/admin/create-user")
async def admin_create_user(payload: CreateUserRequest, _user: dict = Depends(verify_role("admin"))):
    """DEPRECATED — kept as a thin, backward-compatible alias for the
    pre-P1-04 admin UI (AdminDashboardPage.tsx), which still POSTs
    {email, password, role, grade_level, teacher_id}. The real, hardened
    endpoint is POST /api/admin/users (routers/admin.py): server-side
    teacher validation, a generated temporary password, an enrollment
    record, and an audit_log entry — all of which this alias now gets too,
    by delegating to the same services.accounts.create_user().

    `payload.password` is accepted for wire compatibility with the old form
    but is IGNORED: an account always gets a freshly generated temporary
    password now (see services/accounts.py — the whole point of this
    hardening was that the *admin* choosing the new account's password is
    exactly the weak/reused/default-password path that created finding
    A04). Remove this alias once the admin UI is rebuilt against the v2 API
    (roadmap task P1-09).
    """
    username = re.sub(r"[^a-z0-9._-]", "", payload.email.split("@")[0].lower())[:32] or "user"
    try:
        result = accounts.create_user(
            role=payload.role,
            display_name=username,
            username=username,
            grade_level=payload.grade_level,
            teacher_id=payload.teacher_id,
            email=payload.email,
            created_by=_user.get("uid", ""),
        )
    except accounts.AccountError as exc:
        status = 422 if isinstance(exc, (accounts.TeacherInvalid, accounts.ValidationError)) else (
            409 if isinstance(exc, accounts.UsernameTaken) else 500
        )
        raise HTTPException(status_code=status, detail=str(exc))
    return {
        "uid": result["uid"],
        "email": result["loginId"],
        "role": result["role"],
        "temporaryPassword": result["temporaryPassword"],
        "status": result["status"],
    }


@app.get("/admin/users")
async def admin_list_users(_user: dict = Depends(verify_role("admin"))):
    try:
        docs = db.collection("users").stream()
        users = []
        for d in docs:
            data = d.to_dict()
            # v2-schema accounts (services/accounts.py) write camelCase
            # gradeLevel/teacherId; pre-v2 accounts wrote snake_case
            # grade_level/teacher_id. Read both until roadmap task P1-06
            # migrates every writer to camelCase-only.
            users.append({
                "uid": d.id,
                "email": data.get("email", ""),
                "role": data.get("role", ""),
                "grade_level": data.get("grade_level") or data.get("gradeLevel"),
                "teacher_id": data.get("teacher_id") or data.get("teacherId"),
                "status": data.get("status"),
            })
        return {"users": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/teacher/students")
async def get_students(_user: dict = Depends(verify_role("teacher"))):
    teacher_uid = _user.get("uid", "")
    try:
        docs = (
            db.collection("users")
            .where("role", "==", "student")
            .where("teacher_id", "==", teacher_uid)
            .stream()
        )
        students = []
        for d in docs:
            data = d.to_dict()
            students.append({
                "uid": d.id,
                "email": data.get("email", ""),
                "grade_level": data.get("grade_level"),
            })
        return {"students": students}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/teacher/analytics/{student_id}")
async def get_student_analytics(student_id: str, _user: dict = Depends(require_teacher_of)):
    import traceback
    try:
        quiz_docs = (
            db.collection("quiz_results")
            .where("student_id", "==", student_id)
            .stream()
        )
        quizzes = []
        all_wrong: list[str] = []
        for d in quiz_docs:
            data = d.to_dict()
            score = data.get("score", 0)
            total = data.get("total_questions", 0)
            wrong = data.get("wrong_topics") or []
            ts = data.get("timestamp", "")
            if not isinstance(score, (int, float)):
                score = 0
            if not isinstance(total, (int, float)):
                total = 0
            quizzes.append({
                "score": int(score),
                "total_questions": int(total),
                "wrong_topics": wrong if isinstance(wrong, list) else [],
                "timestamp": str(ts),
            })
            if isinstance(wrong, list):
                all_wrong.extend(wrong)
        quizzes.sort(key=lambda q: q["timestamp"])

        session_docs = (
            db.collection("telemetry_sessions")
            .where("student_id", "==", student_id)
            .stream()
        )
        sessions = []
        total_frustration = 0
        for d in session_docs:
            data = d.to_dict()
            focus = data.get("average_focus_score", 0.0)
            triggers = data.get("frustration_triggers", 0)
            ts = data.get("timestamp", "")
            if not isinstance(focus, (int, float)):
                focus = 0.0
            if not isinstance(triggers, (int, float)):
                triggers = 0
            sessions.append({
                "session_id": str(data.get("session_id", "")),
                "average_focus_score": float(focus),
                "frustration_triggers": int(triggers),
                "timestamp": str(ts),
            })
            total_frustration += int(triggers)
        sessions.sort(key=lambda s: s["timestamp"])

        topic_counts: dict[str, int] = {}
        for t in all_wrong:
            if isinstance(t, str) and t:
                topic_counts[t] = topic_counts.get(t, 0) + 1

        return {
            "student_id": student_id,
            "quizzes": quizzes,
            "sessions": sessions,
            "weak_topics": topic_counts,
            "total_frustration_triggers": total_frustration,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# New from the master branch (disability-adaptive scoring): DASE evaluation,
# granular per-question telemetry (feeds DASE — distinct from this file's own
# /analytics/log-quiz and log-session, which are coarser summaries the
# original teacher dashboard still reads), voice navigation, and the
# teacher-roster-scoped DASE analytics that replaces the old
# /teacher/analytics/{id} for the new dashboard. All auth-gated, same pattern
# as every endpoint above.
from routers import analytics as dase_analytics
from routers import admin as admin_v2
from routers import auth_flow
from routers import me as me_router
from routers import evaluation, glossary, math as math_router, nlp, overrides, telemetry, visual, voice_intent, writing

app.include_router(evaluation.router, prefix="/api")
app.include_router(telemetry.router, prefix="/api")
app.include_router(voice_intent.router, prefix="/api")
app.include_router(dase_analytics.router, prefix="/api")
app.include_router(admin_v2.router, prefix="/api")
app.include_router(auth_flow.router, prefix="/api")
app.include_router(me_router.router, prefix="/api")
app.include_router(overrides.router, prefix="/api")
app.include_router(visual.router, prefix="/api")
app.include_router(nlp.router, prefix="/api")
app.include_router(glossary.router, prefix="/api")
app.include_router(math_router.router, prefix="/api")
app.include_router(writing.router, prefix="/api")

from starlette.middleware.cors import CORSMiddleware

# Bound dynamically from config.CORS_ORIGINS (env CORS_ORIGINS, comma-
# separated) rather than hard-coded here — patent-readiness audit finding
# A12. A deployment that needs a different origin set (a staging URL, a
# different Vercel project) no longer requires editing source.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
