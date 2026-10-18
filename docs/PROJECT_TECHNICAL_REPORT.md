# EduEase: A Multi-Disability Adaptive Learning Platform with Automated Telemetry, DASE Scoring, and Scored Dossier Generation

**A Technical Report on System Design, Implementation, and Verification**

---

## Abstract

Neurodivergent and disabled learners — students who are blind or have low vision,
are Deaf or hard of hearing, or who present with dyslexia, ADHD, autism,
dyscalculia, dysgraphia, anxiety, an intellectual disability, or a motor
impairment — are routinely assessed with instruments designed for a
normatively-sighted, normatively-attentive, normatively-literate learner. A
single accuracy percentage conflates "did not know the material" with "could
not physically operate the input device," "lost focus for four seconds," or
"the question's wording, not its content, was the barrier." This conflation is
not a measurement inconvenience; it actively misinforms the teacher trying to
help the student.

This report documents EduEase, an integrated, multi-layered adaptive learning
platform engineered to address this problem end to end: ingesting a source
document, rewriting it on two independent axes (reading grade level and
disability-specific presentation), generating an adapted quiz, instrumenting
every interaction a student has with that quiz or lesson, classifying *why*
each wrong answer was wrong, and combining the resulting telemetry into a
**Disability-Adaptive Scoring Engine (DASE)** score — a composite that is
re-weighted per declared disability, excludes parameters a condition would
mechanically depress regardless of learning, and reports its own measurement
coverage rather than presenting every score with uniform confidence.

The system comprises a FastAPI backend (Python) and a React/TypeScript
frontend, backed by Firebase Authentication and Cloud Firestore, with Google
Gemini and Groq large language models providing text simplification, quiz
generation, conversational tutoring, and image description, each with a
deterministic or lower-cost fallback when the model is unreachable. The
codebase includes twenty-two dedicated backend test modules totaling 253
passing automated tests (verified by direct execution and independently by
test collection) and four frontend test modules totaling 62 passing tests, a
clean production build, and a dedicated tool — the claim-support dossier
generator — that mechanically re-verifies, against the live repository, that
every claimed engineering contribution still has a corresponding, passing,
executable test and an importable, inspectable code symbol behind it.

---

## 1. Introduction

### 1.1 Problem Statement

Assistive educational technology has historically treated accessibility as a
single axis — a screen reader here, a font toggle there — layered onto a
platform whose core measurement logic (accuracy, time-on-task) remains
disability-blind. This produces two concrete failures: first, a score that
penalizes a student for the very condition the platform claims to
accommodate (for example, scoring a blind student on time-to-answer when
screen-reader navigation is inherently slower, or scoring an ADHD student's
raw accuracy when attention lapses, not comprehension failures, are the
actual proximate cause of most of their wrong answers); second, a generic
"wrong answer" signal that gives a teacher no actionable information about
*why* the student was wrong, and therefore no basis for choosing an
intervention.

### 1.2 Design Response

EduEase's response is structural, not cosmetic: every disability profile
carries its own *weighting* of a shared set of measured behavioral
parameters, certain parameters are marked as diagnostic-only (reported, but
withheld from the composite score, for any profile where a worse case of that
condition would mechanically lower the parameter independent of what the
student has learned), and every wrong answer is run through a deterministic
classifier that distinguishes a knowledge gap from an attention lapse, a
processing delay, or a question whose *wording* — not its content — was the
obstacle. All of this machinery is covered by an automated test suite and
further corroborated by a tool that re-executes the cited tests against the
live repository rather than trusting that a citation is still valid.

---

## 2. System Architecture and Technology Stack

### 2.1 Architectural Overview

```
 ┌─────────────────────────────┐          ┌──────────────────────────────┐
 │ Frontend                    │  REST    │ Backend                      │
 │ React 18 + TypeScript + Vite│ (axios,  │ FastAPI (Python)             │
 │ Tailwind CSS (Material-3    │ Firebase │ app.py (legacy routes) +     │
 │ token palette), React       │ ID token │ routers/ (admin, overrides,  │
 │ Router, react-firebase-     │ on every │ evaluation, telemetry,       │
 │ hooks, i18next (EN/HI/TA)   │ request) │ voice_intent, writing, math, │
 │                              │─────────▶│ visual, nlp, glossary, me,   │
 │                              │          │ auth_flow)                  │
 └──────────────┬───────────────┘          └───────────────┬──────────────┘
                │                                           │
                │                           ┌───────────────┴───────────────┐
                │                           │                               │
                ▼                           ▼                               ▼
     ┌────────────────────┐      ┌────────────────────┐      ┌─────────────────────────┐
     │ Firebase            │      │ Cloud Firestore     │      │ Google Gemini / Groq     │
     │ Authentication       │      │ users, sessions,     │      │ simplification, quiz     │
     │ (ID-token issuance)  │      │ sessions/*/events,   │      │ generation, chat,         │
     │                      │      │ evaluations,         │      │ recommendations, image    │
     │                      │      │ dase_overrides,       │      │ description, sentiment,   │
     │                      │      │ audit_log, content,   │      │ visual-summary synthesis  │
     │                      │      │ student_baselines     │      │                           │
     └────────────────────┘      └────────────────────┘      └─────────────────────────┘
```

### 2.2 Technology Stack

| Layer | Technology | Role |
|---|---|---|
| Frontend framework | React 18, TypeScript, Vite | Component tree, type-checked client logic, build tooling |
| Styling | Tailwind CSS (Material-3-style design tokens) | Theming, high-contrast and dyslexia-font variants |
| Client state / data | `react-firebase-hooks`, a single `hooks/useProfile.ts` hook | Single source of truth for the signed-in student's accessibility preferences and disability profile |
| Client HTTP | `axios`, one shared client (`services/api.ts`) | Attaches the signed-in user's Firebase ID token to every request via an interceptor |
| Speech | Web Speech API (`SpeechSynthesis`, `SpeechRecognition`) | Text-to-speech playback and voice-command capture; no third-party STT/TTS service |
| Computer vision | `@mediapipe/tasks-vision` (`FaceLandmarker`) | Client-side, on-device face-presence detection for the optional focus tracker |
| Diagramming | Mermaid.js | Renders LLM-synthesized flowchart/mindmap visual summaries |
| Backend framework | FastAPI (Python), Uvicorn | REST API, dependency-injected authentication/authorization |
| Authentication | Firebase Authentication | Issues ID tokens; verified server-side against Google's public signing keys, independent of the Firestore service-account credential |
| Database | Cloud Firestore | Document store for accounts, telemetry sessions/events, DASE evaluations, overrides, and audit log |
| Vector store | FAISS (`faiss-cpu`), persisted to `backend/data/faiss_index/` | Retrieval index for the chatbot's document grounding |
| LLM orchestration | `langchain`, `langchain-google-genai`, `langchain-community` | Prompt orchestration, retrieval chains, text splitting |
| Primary LLM | Google Gemini (`gemini-2.5-flash` default; a smaller/faster Gemini instance for sentiment scoring) | Simplification, quiz generation, chat, recommendations, image description, visual-summary synthesis |
| Fallback LLM | Groq (`openai/gpt-oss-120b` default) | Automatic text/JSON fallback when Gemini fails or its quota is exhausted |
| PDF parsing | `PyPDF2` (actively imported in `app.py`); `pypdf` also present as a dependency | Text extraction from uploaded lesson PDFs |
| NLP (non-LLM) | spaCy (`en_core_web_sm`) | Deterministic quiz-generation fallback and part-of-speech tagging |
| Testing | `pytest` (backend), `vitest` (frontend) | 253 and 62 passing automated tests respectively (§7) |

### 2.3 Architectural and Design Patterns

- **Separation of concerns.** `backend/app.py` retains the system's original content-pipeline routes (upload, simplify, quiz generation, chatbot); every subsequently added subsystem (account administration, DASE scoring, telemetry ingestion, voice-intent classification, writing assessment, verified mathematics, visual summaries, sign-language glossary, experimental part-of-speech tagging, self-service profile editing) lives in its own `backend/routers/*.py` module, each delegating to a stateless `backend/services/*.py` module that contains no FastAPI dependency and is independently unit-testable.
- **Atomic, server-authoritative writes.** Every multi-document Firestore write that must succeed or fail as a unit (account creation plus its enrollment record plus its audit-log entry; a DASE weight override plus its audit-log entry) is issued as a single Firestore batch, never as sequential individual writes that could partially fail.
- **Server-enforced identity, never client-asserted identity.** Every endpoint that writes telemetry, starts a session, or triggers scoring derives the acting student's identity from the verified ID token (`_user.get("uid")`), not from a `studentId` field the client could have sent. Analogous ownership checks (`assert_session_access`, `require_self_or_mapped_teacher`, `require_teacher_of`) gate every read or write of session data so that a teacher can reach only the students mapped to them, and a student can reach only their own sessions.
- **Honest degradation over silent failure.** Every LLM-backed service (simplification, quiz generation, chat, visual summaries, dictation structuring, image description) defines an explicit non-LLM or weaker-LLM fallback and marks its output `degraded: true` when that fallback was used, so that degraded content can be — and is — excluded from scored analysis rather than silently blended in with full-quality data.
- **Configuration over code for scoring.** The entire DASE weighting scheme — thirteen disability profiles, each with its own parameter weights, a diagnostic-only exclusion list, and a one-line rationale — lives in a single JSON configuration file (`backend/data/dase_profiles.json`), not in Python conditionals, so that the weighting can be audited, versioned by its own SHA-256 hash, and overridden per student without a code change.

---

## 3. Authentication, Security, and Account Provisioning

### 3.1 Closure of Public Self-Registration

The sign-in form (`frontend/src/components/AuthForm.tsx`) is deliberately
sign-in-only; there is no client-side registration path, and the component's
own in-code comment records why: a public registration endpoint that lets
the browser choose its own role is treated as a disqualifying security gap
for a platform that handles disability disclosure. Every account is instead
admin-provisioned.

### 3.2 Token Verification and Role-Based Access Control

`backend/auth.py` is the single point through which every protected route is
authorized, via two composed FastAPI dependencies:

- **`verify_user`** extracts the `Authorization: Bearer <token>` header and
  verifies it against Google's public signing keys
  (`firebase_config.verify_firebase_token`) — independent of the
  service-account credential Firestore access uses, so a mismatch between
  the two fails loudly as an authentication error rather than silently
  authenticating against the wrong Firebase project. A missing, malformed,
  or invalid token yields `401`.
- **`require_active_user`** builds on `verify_user` by reading the caller's
  `users/{uid}` Firestore document (cached for 15 seconds in a
  `cachetools.TTLCache`, invalidated immediately on any write that changes
  the cached fields) and enforcing three account-state gates before the
  request is allowed to proceed: the account must exist (`403
  PROFILE_MISSING` otherwise — a now-removed hardcoded demo-account
  allow-list used to substitute for this check), must not be disabled
  (`403 ACCOUNT_DISABLED`), and must not still owe a forced first-login
  password change (`403 PASSWORD_CHANGE_REQUIRED`) — the one exempted route
  being the password-change endpoint itself.
- **`verify_role(required_role)`** is a dependency factory built on top of
  `require_active_user`, so every role-gated route (`Depends(verify_role("admin"))`,
  `Depends(verify_role("teacher"))`) automatically inherits the disabled-account
  and forced-password-change checks as well, rather than re-implementing them.

A client-side convenience gate (`frontend/src/components/RoleGate.tsx`) reads
the same Firestore document to redirect a signed-in user to the dashboard
matching their role, and to pre-empt the server's 403 by redirecting directly
to the forced password-change screen when `mustChangePassword` is set — but
this is advisory only; the authoritative enforcement is entirely server-side.

### 3.3 Atomic Account Provisioning

`backend/services/accounts.py` is the sole path by which a `users/{uid}`
document can come into existence through the HTTP API, exposed via
`POST /api/admin/users` (single account) and `POST /api/admin/users/bulk`
(CSV import), both gated behind `verify_role("admin")`. Each creation:

1. Generates a twelve-character temporary password from a thirty-character
   alphabet that deliberately excludes visually ambiguous characters
   (`0`/`O`, `1`/`l`/`I`) so a hand-written or read-aloud credential hand-off
   sheet cannot be misread, formatted as `XXXX-XXXX-XXXX`, drawn via
   `secrets.choice` (cryptographically random, never chosen by the
   administrator).
2. Creates the Firebase Authentication user with that password.
3. Writes the `users/{uid}` document, an `enrollments/` record (for a
   student, linking them to their assigned teacher), and an `audit_log`
   entry, in one Firestore batch. If the batch fails after the Authentication
   user already exists, the Authentication user is deleted again rather than
   left as an orphaned, roleless login, and the underlying exception is now
   logged server-side before being re-raised, so a persistence failure is
   never silently invisible to the operator.
4. Marks the new account `status: "pending_first_login"` and
   `mustChangePassword: true`.

A student account additionally requires a `teacherId` that resolves to an
*active* teacher account; this is validated server-side regardless of what
the client enforces. No HTTP endpoint — intentionally — can create an account
with `role: "admin"`; `services/accounts.py`'s `create_user` rejects any role
other than `"student"`/`"teacher"` at both the type-alias and the runtime
level. The sole path to an administrator account is a local, interactive
command-line script (`backend/scripts/create_admin.py`) that prompts for the
password via a non-echoing terminal read and never accepts it as a command-line
argument, so the credential never transits HTTP, a log line, or shell
history.

### 3.4 Forced First-Login Password Change

`POST /api/auth/first-login-password` (`backend/routers/auth_flow.py`) is the
only route that may clear an account's `mustChangePassword` flag, and it
performs the password change itself via the Firebase Admin SDK rather than
trusting a client-reported success. The new password is subject to a
ten-to-128-character length bound and a denylist rejecting common weak
choices, sequential character runs, and passwords with two or fewer distinct
characters. On success, every existing session for that account is revoked
(`revoke_refresh_tokens`) so that whoever the temporary credential was
exposed to loses access immediately rather than at natural token expiry.

### 3.5 Account Lifecycle Management

Beyond initial provisioning, `services/accounts.py` exposes disable/enable,
an administrator-initiated password reset (re-issuing a fresh temporary
password and re-arming the forced first-login flow), and teacher
reassignment for a student — each writing its own `audit_log` entry
(`actor`, `action`, `target`, `details`, server timestamp) and each reachable
only through `routers/admin.py`'s `verify_role("admin")`-gated endpoints.

### 3.6 Self-Service Profile Updates

`GET`/`PATCH /api/me` (`backend/routers/me.py`) lets any signed-in user —
student, teacher, or administrator — change their own display name or
username after an administrator has created the account, closing a gap in
which no account, of any role, had any self-service identity control at all.
A voluntary password change (as opposed to the forced first-login case) is
handled entirely client-side via Firebase's own
`reauthenticateWithCredential` + `updatePassword`, the SDK's own idiomatic
mechanism for gating a password change on a recent sign-in, and needs no
dedicated backend route.

---

## 4. Multi-Disability Accessible Interface and Navigation Subsystem

Twelve disability categories are modeled explicitly in the data contract
(`Disability` type: dyslexia, ADHD, autism, blind, low vision, Deaf, hard of
hearing, dyscalculia, dysgraphia, anxiety, intellectual disability, motor),
and `disabilities` is stored as a list, not a single value, because
comorbidity (most visibly ADHD with dyslexia) is treated as the expected
case rather than an edge case. The sections below describe the mechanisms
specific to each population; accommodations that generalize (grade-level
simplification, font scaling, high contrast, reduced motion) are covered in
§6.

### 4.1 Blind and Low-Vision Support

- **Global voice navigation.** A single component (`VoiceNavigator.tsx`),
  mounted once above the router rather than per-page, listens for a
  push-to-talk shortcut (Ctrl+Shift+V) and routes the resulting transcript
  through a rules-first, LLM-fallback intent classifier that exists in two
  mirrored implementations — `frontend/src/services/voiceIntents.ts`
  (client-side) and `backend/services/intent.py` (server-side, reached via
  `POST /api/voice/intent` only when the client-side rule set misses). The
  core rule table (`_RULES`/`RULES`) holds fifteen ordered regular-expression
  rules; three further intents (navigation, answer selection, and an
  explicit words-per-minute command) are matched by dedicated patterns
  checked ahead of that table, for eighteen distinct intents in total
  (navigation to a named page, answer selection by letter/ordinal/`true`/`false`,
  submit, skip, exit, repeat, read next/previous/all, play/pause/resume,
  an explicit words-per-minute reading-speed command, faster/slower, explain,
  progress, help, stop); a match returns in well under the latency of a
  network round trip and is assigned a high fixed confidence, while an
  unmatched utterance falls back to an LLM call that is instructed to return
  an explicit "unknown" rather than guess a destination — sending a blind
  student to the wrong page is treated as strictly worse than admitting the
  system did not understand. `STOP` is matched before every other rule,
  reflecting that silencing in-progress speech is the single most
  time-critical command for a student with no other way to interrupt output.
- **Sentence-level, cancelable speech.** All `speechSynthesis` use is
  centralized in one module (`services/speech.ts`); text is queued one
  sentence at a time (not one word at a time, which previously flooded the
  browser's speech queue and desynchronized from an on-screen highlight), a
  monotonically increasing token ensures a new "stop" or a new read request
  always pre-empts whatever was mid-utterance, and every spoken sentence is
  simultaneously appended to a persistent, in-memory caption log for a
  student with sound off or a companion reading over their shoulder.
- **Spatial, non-verbal audio cues.** `services/earcons.ts` synthesizes short
  (under 300 ms) tones directly via Web Audio API oscillators — no audio
  files — for page-heading changes, content boundaries, a new quiz question,
  microphone-open, and "command not understood," each using
  exponential-ramp gain envelopes to avoid an audible click.
- **Strict webcam exclusion.** `webcamAllowed()` (`frontend/src/types/profile.ts`)
  unconditionally returns `false` for a profile carrying `blind`,
  `low_vision`, or `autism`, overriding any stored preference; the
  webcam-based focus tracker (`<Eye/>`, §4.5) is consequently never
  mounted, never requests camera permission, and the corresponding
  Settings toggle to enable it is not even rendered for these profiles.
  Autism is excluded for a different reason than blind/low-vision: the
  camera itself works fine, but a face-presence signal is a poor proxy for
  attention here — atypical eye contact is a feature of autism, not a sign
  of disengagement — so `ATT_SPAN` is never declared for this profile in
  `dase_profiles.json` either, and the downstream `ATTENTION_LAPSE`
  classification branch (§5.3), which requires trustworthy focus data to
  ever fire, is consequently unreachable for this profile by construction
  rather than by a special-cased exception.

### 4.2 Deaf and Hard-of-Hearing Support

- **On-demand visual summarization.** A single Gemini/Groq call converts a
  lesson into a Mermaid.js diagram (a flowchart or mindmap, capped at ten
  nodes, plain-language node labels) plus three to six short "concept cards"
  (title, one-sentence explanation, an illustrative emoji), cached on the
  exact `(text, profile)` pair so a given lesson is ever synthesized once
  regardless of how many students subsequently view it. The feature fires
  only on an explicit "Show visual summary" click, never automatically, and
  a text-only "View as text" rendering of the same content is always present
  alongside the diagram, never only the diagram. Model-returned diagram
  syntax is rejected outright — not sanitized in place — if it does not
  begin with a recognized Mermaid directive, exceeds a plausible line count,
  or contains any of a fixed set of disallowed tokens (`click`, `href`,
  `javascript:`, raw `<`, inline event-handler attributes), since Mermaid's
  own syntax supports interactive callbacks and raw HTML in labels that would
  otherwise be a prompt-injection-reachable cross-site-scripting surface; the
  renderer additionally runs with Mermaid's `securityLevel: "strict"` as a
  second line of defense.
- **Non-audio alert channel and a persistent caption log.** A global
  component (`VisualAlert.tsx`) listens for a shared notification event and
  renders a brief, WCAG-compliant (at most three flashes, respecting
  `prefers-reduced-motion`) border pulse and/or a labeled badge, independent
  of whatever toast or spoken announcement accompanies it. Every such
  notification — regardless of whether anything was actually spoken aloud —
  is also appended to the same caption log §4.1 describes, and the same
  component exposes a collapsible drawer showing the last fifty entries,
  giving a Deaf or hard-of-hearing student (or anyone with sound muted) a
  persistent, reviewable record of what happened, not only a transient one.
- **Teacher-curated sign-language glossary.** A per-word lookup
  (`SignGloss.tsx` against `GET /api/glossary/{term}`) opens a captioned
  video of a sign-language rendering of that word, sourced from a
  Firestore document (`sign_glossary/{term}_{lang}`) that stores only a
  Firebase-Storage URL and captions a teacher has uploaded — the clip's
  bytes never transit the backend, and only a teacher may write a new
  glossary entry, a deliberate, licence-safe design rather than a generative
  or third-party-video-embedding approach.
- **Experimental part-of-speech coloring.** `PosText.tsx` colors and
  underline-styles each word by its coarse part of speech (color plus a
  distinct visual treatment together, never color alone, per WCAG 1.4.1),
  computed server-side with spaCy. Both the client and server label this
  feature "experimental" in its own user-facing copy and code comments: no
  evidence in the project's research basis establishes that this presentation
  improves comprehension for this population, and the feature exists to let
  that hypothesis be tested, not because it is already supported.

### 4.3 Dyscalculia Support

- **Interactive, keyboard-operable manipulatives.** `ManipulativePanel.tsx`
  mounts one of four manipulative types (a number line, a ten-frame, a
  fraction bar, or base-ten blocks) alongside — never in place of — the
  normal answer controls for a numeric fill-in-the-blank item, letting a
  student use the manipulative or ignore it.
- **AST-verified micro-step solutions.** For a problem a student answered
  incorrectly, `StepPlayer.tsx` requests a step-by-step numeric breakdown
  (`POST /api/math/steps`), where "AST-verified" is literal rather than a
  feature name: the backend (`backend/services/math_steps.py`) parses each
  proposed step's arithmetic expression with Python's own `ast` module into
  a syntax tree, and evaluates that tree with a hand-written, restricted
  evaluator supporting only addition, subtraction, multiplication, and
  division over exact `Fraction` values — never Python's `eval()`, never a
  symbolic-math library on untrusted model output. A step whose claimed
  result does not match the restricted evaluator's own computation is
  silently dropped rather than shown to the student; a shorter, verified
  explanation is treated as strictly better than a complete but possibly
  wrong one. Each verified step is read aloud via text-to-speech while a
  base-ten-block visualization simultaneously updates to the running result,
  giving the student a synchronized auditory and visual channel.
- **Deterministic error typing.** Independent of the above, a wrong numeric
  answer is classified into one of five mechanistic categories — place-value
  slip, operation confusion, carry/borrow error, sequencing (wrong operator
  precedence), or a residual fact-recall gap — using only exact fractional
  arithmetic and digit comparisons; no language model participates in this
  decision, though one may later be asked only to *explain* the determined
  category in plain language.
- **Content-aware quiz reinforcement.** The quiz-generation prompt
  (`backend/services/quiz_gen.py`) detects, via a regular expression over
  digits combined with arithmetic operators or calculation verbs ("sum,"
  "total," "how many," …), whether the source passage actually contains
  arithmetic; when it does, the dyscalculia-profile prompt is dynamically
  strengthened to require at least one fill-in-the-blank item whose answer
  is a bare number, which is precisely the condition the frontend checks to
  decide whether to surface the manipulative panel and step player for that
  item.

### 4.4 Dysgraphia Support

- **Voice-to-structured-essay dictation.** `VoiceEssay.tsx` lets a student
  dictate an answer in repeated short bursts (the browser's
  `SpeechRecognition` API is one-shot by design, so continuous dictation is
  simulated as a loop of one-shot captures appended to an editable
  transcript) and then requests that the raw dictation be organized into an
  outline and paragraphs (`POST /api/writing/structure`). The organizing
  model is constrained to use the student's own words and ideas, never to
  introduce a fact, number, name, or date absent from the dictation; every
  number appearing in the organized output is checked against the numbers
  that actually appeared in the dictation, with any mismatch surfaced as an
  explicit warning rather than hidden. When the organizing model is
  unreachable, or returns a response that is not a well-formed object, or is
  missing usable paragraphs, the backend falls back to presenting the raw,
  unorganized dictation with a clearly worded notice — the frontend renders
  this specific case with neutral, informational styling rather than the
  stronger red alert styling it reserves for a genuine content-accuracy
  warning (the number-mismatch case), so that a model outage is never
  visually indistinguishable from the system having actually failed the
  student.
- **Split knowledge/mechanics scoring.** A written answer is scored on two
  independent axes (`backend/services/writing_score.py`): concept coverage
  (`KNOW`), which is evidentiary rather than a holistic LLM judgment — the
  scoring model must cite a verbatim quote from the student's own answer for
  each concept it claims is covered, and that quote is then deterministically
  checked for literal substring membership in the student's actual answer
  before the concept is credited — and written-expression quality (`EXPR`),
  a rubric blend of organization (weight 0.4), completeness (0.3), and
  mechanics (0.3), scored by the model but combined deterministically.
  `EXPR` is explicitly excluded from the disability-weighted composite score
  under the dysgraphia profile (§5), since a more severe case of dysgraphia
  would mechanically depress writing mechanics independent of how much the
  student has actually learned.

### 4.5 Anxiety and Attention-Deficit/Hyperactivity Disorder Support

- **Calm-mode presentation.** A `calmMode` preference removes a running
  score display, time pressure, and red error coloring from the quiz
  experience, and — specific to anxiety support — introduces a fixed
  four-question "micro-block" pause: every fourth question, the quiz stops
  and explicitly offers to continue, take a short break, or stop for now,
  with stopping early recorded as a *completed* block rather than an
  abandoned session, since the design goal is that choosing to stop must
  never read, to the system or to the student, as a failure.
- **Attention-lapse-forgiving scoring.** The ADHD disability profile
  discounts, rather than penalizes, a wrong answer the error classifier
  attributes to an attention lapse (§5), and weights effort and persistence
  signals more heavily than raw accuracy.
- **Auto-pacing suggestion, never an automatic change.** A per-student
  exponential moving average of observed words-per-minute reading speed
  (blended 70% previous estimate / 30% newly observed, with an additional
  slowdown applied when a student frequently replays sentences) is computed
  server-side and exposed to the reading page, which uses it only to ask
  "Shall I read a little slower?" — the preference itself is changed only if
  the student affirmatively agrees; nothing in the pacing pipeline ever
  silently adjusts a reading rate on its own, and the system is explicit
  that it will suggest slowing down but will never suggest speeding up a
  profile for which a slower, accommodated pace is itself the point.
- **Explicit words-per-minute control.** A dedicated reading-speed slider
  (100–300 WPM) on the reading page, and an equivalent voice command ("set
  reading speed to 200," "make WPM 250"), both write directly to the same
  stored preference that drives actual text-to-speech playback rate,
  keeping the visible control, the voice command, and the Settings page's
  own rate slider mutually consistent.

### 4.6 Consent-Gated Webcam Attention Tracking

A face-presence focus tracker (`<Eye/>`, using on-device MediaPipe face
landmarks, never a server-side video stream) is mounted only when *both* an
explicit `webcamAttention` preference and a separate, revocable
`consent.webcam` flag are true, and only for a profile that is not blind or
low-vision (§4.1). When mounted, it samples face presence roughly fifteen
times per second, debounces a sustained four-second absence into an
on-screen "you looked away" banner (offered as something that can itself be
read aloud or dismissed, never forced), and separately reports a raw,
undebounced presence sample on every tick to the telemetry layer so that the
`ATT_SPAN` DASE parameter (§5) is computed from an honest per-tick ratio
rather than from the UI's own debounced state. The system is explicit,
throughout its documentation and in the teacher dashboard's own copy, that
this measures *face presence*, not gaze or attention in any stronger sense,
and the parameter is never surfaced to a teacher under a stronger label than
that.

---

## 5. The Disability-Adaptive Scoring Engine (DASE)

### 5.1 Design Philosophy

DASE (`backend/services/dase_engine.py`) converts a student's interaction
telemetry into eighteen independently computed, zero-to-one parameters,
combines a disability-appropriate subset of them into a single composite
score, and reports, alongside that score, exactly what fraction of the
intended measurement was actually available. A parameter for which no data
exists in a given session is *absent* from the result rather than defaulted
to zero, since a missing measurement must never silently read as a failing
one.

### 5.2 Telemetry Data Model

Every student interaction is captured as one of four typed event shapes
(`backend/models/schemas.py`) attached to a `sessions/{sessionId}` document:
a `QuestionEvent` (selected answer, correctness, response time, time to
first interaction, answer changes, revisits, whether the stem was re-read,
focus ratio and sample count, and — once computed — an error
classification), a `ReadingEvent` (words read, elapsed time, replay count,
focus ratio), a `VoiceEvent` (transcript, speech-to-text confidence,
classified intent, whether it was understood, time to complete the
resulting action), and a `VisualEvent` (dwell time on a visual-summary
concept card, whether it was expanded or replayed). Every event batch
(`POST /api/events`, capped at one hundred events per call) is validated
against its typed schema and, per event, checked against the submitting
user's actual session ownership before being written; a malformed or
not-owned event is skipped and reported rather than failing the whole batch.
Critically, a wrong answer's error classification is *re-derived
server-side at ingest* whenever the stored classification is missing or was
computed by an earlier version of the classifier, so the client's own
claimed label is never the system of record and a classifier formula change
automatically relabels previously ingested data without a separate
migration.

### 5.3 Cause-Based Error Classification

`classify_error()` is invoked only for a wrong answer and distinguishes four
causes, each requiring a distinct timing and attentional signature relative
to the student's own rolling-median response time over their prior answers
*this session* (never a cohort average, and never a cross-student
statistic):

| Label | Trigger condition | Representative confidence behavior |
|---|---|---|
| `PROCESSING_DELAY` | Explicitly timed out, or response time ≥ 2× the student's own session baseline | Timeout fixes confidence at 0.90; otherwise confidence starts at 0.50 and increases with how far past 2× the response time was, with a bonus if the student changed their answer (evidence of real effort), scaled by how many prior answers exist to trust the baseline |
| `ATTENTION_LAPSE` | Response time ≤ 0.5× baseline **and** face-presence ratio below 0.6, with at least five trustworthy focus samples | Confidence scales with how far below 0.5× the timing is and how far below 0.6 the focus ratio is, capped by how much focus data exists |
| `COMPREHENSION_BARRIER` | Response time ≤ 0.33× baseline, face-presence ratio ≥ 0.6, and the question stem was never re-read | Confidence scales with timing extremity and focus-data trust |
| `KNOWLEDGE_GAP` | The honest residual: normal timing and focus, **or** a fast-but-wrong answer for which no trustworthy focus data exists at all | A fixed, deliberately low confidence (0.30) when focus data is simply unavailable — the classifier explicitly refuses to guess between an attention lapse and a comprehension barrier from nothing — rising with how many prior answers exist and whether the stem was re-read in the ordinary residual case |

When focus data is unavailable, a response pattern consistent with having
visibly hesitated before answering (more than 60% of the total response time
elapsing before the first interaction) narrows the reported alternative
labels toward `ATTENTION_LAPSE` rather than leaving every alternative open,
on the basis that a hesitate-then-guess pattern reads more as disengagement
than as a stable knowledge gap — but the primary returned label in this
branch remains the conservative `KNOWLEDGE_GAP`.

A companion decision, `should_represent()`, determines whether a wrong
answer should trigger re-presentation of a pre-generated, easier variant of
the same question: only when the classified label is
`COMPREHENSION_BARRIER` and its confidence meets or exceeds a configured
threshold (0.45). A knowledge gap is deliberately never re-presented in
easier words, since doing so would simply show the student a question they
still cannot answer.

Every timing ratio above is computed against an item-length-normalized
response time, not the raw millisecond figure: an estimated reading-time
floor (the item's stem-plus-options word count multiplied by a 300ms/word
literature-informed estimate) is subtracted from the raw response time
before any ratio-against-baseline comparison. A long question stem simply
takes longer to read regardless of hesitation or attention, and without
this adjustment a sufficiently long item could be misclassified as a
processing delay, an attention lapse, or a comprehension barrier for that
reason alone.

### 5.4 Parameter Computation

Each of the eighteen parameters is computed only when its minimum data
requirement is met; the table reports the live formula and gating condition
for each.

| Parameter | Measures | Formula (summarized) | Minimum data |
|---|---|---|---|
| `ACC` | Raw accuracy | correct ÷ answered | any answered item |
| `ADJ_ACC` | Accuracy after forgiving classified attention lapses | correct answers count 1.0; an attention-lapse-classified wrong answer counts 0.75 × its classification confidence; all divided by total answered | a perfect session, or ≥80% of wrong answers already classified |
| `COMP` | Accuracy on harder items | correct ÷ answered, restricted to items of difficulty ≥ 3 | ≥3 such items |
| `TIME_EFF` | Response efficiency vs. the student's own cross-session baseline | mean of min(personal baseline ms ÷ response ms, 1.0) over *correct* answers | ≥3 correct, timed answers, and an existing cross-session baseline |
| `ATT_SPAN` | Mean face presence | mean of per-answer focus ratios with ≥5 trustworthy samples each | ≥1 qualifying answer with webcam consent; never computed at all for the autism profile, which excludes the focus tracker entirely (§4.1, §4.6) |
| `PACE_STAB` | Pace (response-time) stability | 1 − coefficient of variation of correct-answer timing | ≥4 timed correct answers |
| `ACC_STAB` | Cross-session accuracy stability | 1 − normalized variance of per-session accuracy | ≥3 prior sessions |
| `EFFORT` | Engagement | per-item score: +0.3 if the answer was changed, +0.2 if re-read, +0.2 if revisited, +0.3 if ≥50% of the session's median response time was spent, averaged | any answered item |
| `LRN_VEL` | Improvement within the session | 0.5 + (second-half accuracy − first-half accuracy) ÷ 2, with a fixed 0.9 for sustained near-perfect performance in both halves | ≥6 answered items |
| `TASK_COMP` | Session completion | completed sessions ÷ recent sessions (last 20) | any session history |
| `READ_FL` | Reading fluency vs. a 200 wpm reference | mean observed words-per-minute ÷ 200, capped at 1.0 | ≥20 words read in a single reading event with >1 s elapsed |
| `VOICE_Q` | Voice-interface recognition quality | 0.6 × first-try-understood rate + 0.4 × mean speech-recognition confidence − 0.2 × a repeat-rate penalty | ≥3 voice command events |
| `NAV_EFF` | Voice-navigation efficiency | mean of min(4000 ms ÷ action time, 1.0) over understood commands, scaled by the understood rate | ≥3 voice events with at least one completed action |
| `PATTERN` | Sequencing/categorization/matching accuracy | correct ÷ answered, restricted to items tagged as that item kind | ≥3 such items |
| `RESIL` | Resilience (1 − hesitation) | 1 − the hesitation index (§5.6) | at least one of the hesitation index's four input signals |
| `VIS_ENG` | Engagement with visual-summary content | mean of 0.5×(dwell ≥3 s) + 0.3×(card expanded) + 0.2×(diagram replayed) across visual events | ≥3 visual events |
| `KNOW` | Concept coverage in a written answer | mean of per-item concept-coverage scores, each evidentiary-verified (§4.4) | ≥1 scored written item |
| `EXPR` | Written-expression quality | mean of per-item rubric scores (organization/completeness/mechanics) | ≥1 scored written item |

All question events flagged `degraded` (produced by the deterministic
fallback generator when every language model was unreachable) are excluded
from every parameter computation, since they were not generated under the
disability- and grade-adapted format the scoring scheme assumes.

**Confidence intervals.** A nine-item quiz session is a small sample to be
reporting a parameter to two decimal places from. `POST /api/evaluate`
additionally computes, for every parameter that is literally a
successes-over-n proportion (`ACC`, `COMP`, `PATTERN`, `TASK_COMP`), a 95%
**Wilson score interval** — the standard correction for the plain
normal-approximation interval's known failure at small n or at a
proportion near 0 or 1. For the composite score itself, which is not a
simple proportion, a 95% **bootstrap** interval is computed instead: the
session's own question events are resampled with replacement (500
resamples by default) and the full parameter set and composite score are
recomputed for each resample, with the interval taken as the 2.5th and
97.5th percentile of the resulting scores — a direct, non-parametric
estimate of how much the score would plausibly vary across hypothetical
repeats of the same small session, rather than a formula-based
approximation. Both intervals are persisted alongside the evaluation and
surfaced on the teacher dashboard next to the point values they qualify,
rather than only in the API response.

### 5.5 Disability-Weighted Composite Scoring

Thirteen disability profiles (the twelve declared disability categories plus
a `default` profile for an undisclosed disability) are configured in
`backend/data/dase_profiles.json`, each with its own weight for a subset of
the eighteen parameters, each weight accompanied by a one-sentence
rationale, and each profile's declared weights summing to exactly 1.0. Two
representative profiles:

- **ADHD**: `ACC 0.1364, ADJ_ACC 0.2544, ATT_SPAN 0.1364 (diagnostic-only),
  EFFORT 0.2000, TASK_COMP 0.0909, LRN_VEL 0.0909, PACE_STAB 0.0228
  (diagnostic-only), ACC_STAB 0.0227, RESIL 0.0455`. The forgiving accuracy
  measure `ADJ_ACC`, not raw `ACC`, carries the single largest weight, and
  effort/persistence are weighted more heavily than for the default
  profile. `PACE_STAB` is diagnostic-only here for the same reason as
  `ATT_SPAN`: inconsistent response-time pacing is itself a symptom of
  ADHD, not a measure of unreliable performance; `ACC_STAB` stays scorable,
  since being reliably *accurate* from session to session is not itself a
  symptom of the condition.
- **Dyslexia**: `ACC 0.0909, COMP 0.2908, READ_FL 0.1364 (diagnostic-only),
  EFFORT 0.1636, LRN_VEL 0.1364, TIME_EFF 0.0909 (diagnostic-only),
  PACE_STAB 0.0228, ACC_STAB 0.0227, RESIL 0.0455`. Comprehension on harder
  items, not raw accuracy (which is disproportionately depressed by
  decoding errors rather than misunderstanding), is the dominant term.

The autism profile applies the same `PACE_STAB`-only exclusion as ADHD
(`PACE_STAB 0.10` diagnostic-only, `ACC_STAB 0.10` scorable) for the same
underlying reason — variable processing pace is a feature of autism, not a
measure of unreliable performance — and never declares `ATT_SPAN` at all,
since the webcam focus tracker is excluded from this profile entirely
(§4.1, §4.6): a face-presence signal is a poor proxy for attention when
atypical eye contact is itself a feature of the condition.

A parameter is marked diagnostic-only for a given profile when a more
severe case of that same disability would mechanically lower the parameter
regardless of how much the student has actually learned — the governing
example, surfaced by the project's own internal ablation testing, is
`ATT_SPAN` under the ADHD profile: attention span is itself the condition
being accommodated, so scoring it directly would penalize a student for
having ADHD. A diagnostic-only parameter is still computed and reported
(visible to the teacher, for instance on a parameter radar chart) but is
unconditionally excluded from the weighted score, and — significant for the
override mechanism below — this exclusion is a property of the *profile*,
never of a teacher's chosen weights.

The composite score (`compute_dase()`) is a weighted *average*, not a
weighted sum, over only the parameters that are both declared for the
profile, not diagnostic-only, and actually present in this session's
computed parameters:

```
scorable      = { parameter : weight | weight declared for the profile and not diagnostic-only }
usable        = { parameter : weight ∈ scorable | parameter actually computed this session, weight > 0 }

score    = Σ (parameterValue[p] × weight[p])  for p in usable
            ───────────────────────────────
                  Σ weight[p]  for p in usable

coverage = Σ weight[p] for p in usable  ÷  Σ weight[p] for p in scorable
```

`coverage` is therefore distinct from the renormalization itself: it reports
what fraction of the profile's *intended, scorable* weight mass was actually
measurable this session, independent of the fact that the score itself is
always renormalized to behave as a proper weighted average over whatever was
measured. This is the mechanism by which a 40%-coverage score and a
95%-coverage score are never presented with the same implied confidence — the
teacher dashboard shows coverage next to every score, never the score alone.

**Worked example.** Consider a student scored under the ADHD profile with
measured parameters `ACC = 0.55`, `ADJ_ACC = 0.82`, `EFFORT = 0.60`,
`TASK_COMP = 0.60`, `LRN_VEL = 0.55`, `ACC_STAB = 0.30`, and no measurable
`RESIL` this session (no chatbot use and no response-time baseline yet
established). `ATT_SPAN` and `PACE_STAB` are both excluded as
diagnostic-only regardless of whether either was measured. The scorable
weight mass (every ADHD weight except `ATT_SPAN` and `PACE_STAB`) is
`0.1364 + 0.2544 + 0.2000 + 0.0909 + 0.0909 + 0.0227 + 0.0455 = 0.8408`;
with `RESIL` additionally unmeasured, the usable weight mass is
`0.8408 − 0.0455 = 0.7953`, giving `coverage = 0.7953 ÷ 0.8408 ≈ 0.946`
(94.6%). The composite score is:

```
(0.55 × 0.1364 + 0.82 × 0.2544 + 0.60 × 0.2000 + 0.60 × 0.0909 + 0.55 × 0.0909 + 0.30 × 0.0227) ÷ 0.7953
   = 0.5150 ÷ 0.7953
   ≈ 0.648
```

The same measured attention-lapse-discounted accuracy would be weighted at
0.30 rather than 0.2544 under the `default` profile and would carry no
`ADJ_ACC` term at all — the deliberate point being that the identical
underlying measurements are read through a materially different lens
depending on the declared disability, rather than being blended into one
disability-blind percentage.

### 5.6 The Hesitation and Resilience Index

`backend/services/hesitation.py`'s `hesitation_index()` blends up to four
interaction-only signals — explicitly never a facial or physiological
inference, and never a clinical judgment — each contributing its fixed
weight only when it is actually available, renormalized over whichever
signals are present: mean response-time ratio against the student's own
baseline (weight 0.30), mean number of answer changes per question
(weight 0.25), mean tab-blur (focus-loss) count per question (weight 0.20),
and the session's mean chatbot frustration score (weight 0.25, itself
produced by a dedicated sentiment-classification model call per chat turn,
§6.7, and reset to empty whenever a new session begins so a prior session's
frustration can never bleed into the current one's index). `RESIL`, the DASE
parameter, is `1 − hesitation_index`, a rename from an earlier formulation
whose name described the quantity to be minimized while its weight was
signed as though higher were better.

### 5.7 Teacher-Initiated Weight Overrides and Audit Logging

A teacher mapped to a given student may override that student's DASE
weights via `PUT /api/teachers/students/{id}/dase-weights`
(`backend/routers/overrides.py`), subject to server-side validation that a
non-empty reason of at least three characters is supplied, every named
parameter is a real, known DASE parameter, and every weight is non-negative.
The supplied weights wholesale replace the profile's declared weights for
scoring purposes — but the diagnostic-only exclusion set is still always
drawn from the student's underlying disability profile, never from the
override, by design: which parameters a more severe form of a condition
would mechanically depress is a fact about the disability, not a preference
a teacher's override should be able to switch off. Every override write, and
every override clearance, is logged to `audit_log` with the acting
teacher's identity, the full weight dictionary, and the stated reason, and a
teacher can retrieve their own override history via
`GET /api/teachers/audit-log`.

### 5.8 Stated Limitations

The project's own documentation is explicit, and this report repeats the
same caveats rather than overstating what has been built: the disability
profile weights are literature-informed but not yet empirically validated
against real learner outcomes; the face-presence signal measures whether a
face was visible, not gaze or attention in a stronger sense; any result
produced by a degraded (non-LLM fallback) content generator is excluded from
scored analysis; and a DASE score is only as strong a claim as its reported
coverage.

### 5.9 Teacher-Facing Aggregates and the Measurement-Invariance Warning

`backend/routers/analytics.py` layers class-wide aggregates on top of the
per-student score above, scoped to only the calling teacher's own roster.
A pooled class-average score is still computed and shown — a single
"classroom at a glance" figure remains useful — but DASE scores are each
profile's own disability-weighted composite, not a shared, profile-agnostic
scale: a blind student's score and an ADHD student's score are two
differently-measured constructs that happen to share a 0–1 range, not two
readings on the same ruler. Pooling them without qualification is a
measurement-invariance violation. Accordingly, the class-aggregates
response carries a non-null `measurementInvarianceWarning` string whenever
the scored students span more than one distinct disability profile, and is
`null` when the class has no scored students or all scored students share
one profile. The teacher dashboard surfaces this warning directly next to
the pooled figure and alongside the pre-existing per-profile average
breakdown, which the warning explicitly recommends as the safer comparison.

---

## 6. Content Processing and Generation Pipelines

### 6.1 PDF Ingestion and Retrieval-Augmented Generation

`POST /upload-pdf/` extracts text from an uploaded PDF via `PyPDF2`, capped
at 5 MB and twenty pages so a single upload cannot exhaust a day's language-model
quota, and optionally — only when a student opts in — describes embedded
images via a Gemini multimodal call, falling back to an honest placeholder
description (rather than silently omitting the image) when that call is
unreachable. Extracted text is ingested into a retrieval index
(`backend/ingestion.py`) built on a `ParentDocumentRetriever`: documents are
split into small child chunks (600 characters, 60-character overlap) for
retrieval precision and larger parent chunks (3,200 characters, 200-character
overlap) for answer context, embedded via a Gemini embedding model, and
persisted to a FAISS index on disk (`backend/data/faiss_index/`). The
chatbot (§6.7) retrieves against this same index.

### 6.2 Disability- and Grade-Aware Text Simplification

`POST /simplify-text/` rewrites a passage on two independent axes
(`backend/services/nlp_simplify.py`): a grade-level axis (first through
eighth grade) that sets a hard per-sentence word-count ceiling and
vocabulary target, and a disability-profile axis (thirteen profiles, each
with its own sentence-structure, figurative-language, and pronoun-use rules
— for instance, the Deaf profile forbids idioms and passive voice, and the
dyslexia profile forbids subordinate clauses and prefers repeating a noun
over substituting a pronoun). Where the two axes imply different
sentence-length ceilings, the tighter of the two always wins. Readability
before and after rewriting is measured identically (a standard Flesch–Kincaid
computation over words-per-sentence and syllables-per-word) so that the
degree of simplification achieved is demonstrable from the text itself
rather than merely asserted.

### 6.3 Adaptive Quiz Generation

`backend/services/quiz_gen.py` generates exactly nine questions per quiz —
three multiple-choice, three true/false, three fill-in-the-blank — in one
language-model call, composing the same grade-level and disability-profile
axes used for simplification with an additional, per-item-type format
contract (a true/false item's options must be exactly `{"True", "False"}`;
a multiple-choice or fill-in-the-blank item must have exactly four
non-duplicate options; every item's answer must exactly match one of its own
options, the single most damaging possible defect if missed, since a
student could then never answer correctly regardless of their own
knowledge). Every returned item is independently validated against this
contract before being served, and the model is additionally asked to produce
a disability-appropriate *simpler variant* of each item, served only when
the error classifier (§5.3) reports a confident comprehension barrier.
When every configured language-model provider is unreachable, a
deterministic spaCy-based generator produces a weaker, non-adapted quiz from
the source text's own vocabulary, and every item from that fallback is
marked `degraded` and excluded from DASE analysis.

### 6.4 Verified Mathematics Micro-Steps

Described in full in §4.3; summarized here as a content-generation
pipeline: a language model proposes a step-by-step arithmetic decomposition
of a problem, and every step is independently re-verified against a
restricted, non-generative expression evaluator before being shown, with an
unverifiable step silently dropped rather than displayed. A parallel,
fully deterministic classifier types a wrong numeric answer's probable
mechanistic cause without any model involvement in that decision.

### 6.5 Dictation-to-Essay Structuring and Writing Assessment

Described in full in §4.4; summarized here: a student's dictated or typed
answer may be organized into an outline and paragraphs under a strict
"no new facts" constraint, with every number in the organized output
checked against the source dictation, and is independently scored for
concept coverage (evidentiary, verbatim-quote-verified) and written
expression (rubric-based, and excluded from the DASE composite for a
profile — dysgraphia — whose more severe presentations would mechanically
depress it).

### 6.6 Visual Summary Generation for Deaf and Hard-of-Hearing Learners

Described in full in §4.2; summarized here as a generation pipeline: one
language-model call per unique lesson produces a sanitized Mermaid diagram
and a small set of concept cards, cached so that the cost of the feature
never scales with the number of students viewing a given lesson, with
generated diagram syntax rejected rather than repaired if it fails a
structural or token-level safety check.

### 6.7 Conversational Assistant and Frustration Detection

`POST /chatbot/` answers a student's question against the retrieval index
of §6.1 through a `ConversationChain` with per-session memory, applying
prompt-injection detection, personally identifiable information redaction
on both the input and the output, and output-toxicity interception before a
response is ever returned. Independent of generating the reply itself, a
second, smaller and faster Gemini call (capped at 256 output tokens, a
ten-second timeout) scores the turn for frustration on a 0.0–1.0 scale using
a fixed rubric (a score above 0.7 is forced to recommend offering a break; a
score above 0.4 is forced to recommend simplification), and any failure of
that second call — a timeout, malformed output, or quota exhaustion — causes
the turn to default to a calm, "continue" reading rather than propagating an
error, since a conversational turn must never visibly break because
sentiment scoring failed. The resulting score is never persisted on its own
and never directly affects the DASE composite; it feeds only the in-session
nudge UI and, via a session-scoped running mean, the `chat_frustration` input
to the hesitation index of §5.6.

---

## 7. Verification, Testing, and Claim-Support Dossier Generation

### 7.1 Backend Test Suite

The backend carries twenty-two dedicated test modules under `backend/tests/`,
totaling **253 automated tests**, confirmed both by direct execution
(`pytest tests/`, exit status reporting 253 passed) and independently by
test collection (`pytest tests/ --collect-only`, reporting 253 tests
collected; the larger figure relative to 229 distinct test function
definitions in source is accounted for by parametrized test functions being
expanded into multiple collected cases). Coverage spans, among other areas:
a full truth table for the error classifier of §5.3 across every
timing/focus-signal combination including its abstention paths and the
item-length normalization of §5.3; golden-vector tests for every DASE
parameter formula and the composite-scoring invariants of §5.5, each
tracing to a specific defect found and fixed during the project's own
internal review (a vanishing `ADJ_ACC`, a combined pace/accuracy-stability
formula that had rewarded uniformly poor performance as "consistent," a
degenerate `LRN_VEL` case), plus a deterministic cross-profile comparison
showing `ADJ_ACC` raising the ADHD-scored result for an identical
attention-lapse-heavy session while leaving the `default`-scored result
unchanged; the Wilson and bootstrap confidence-interval functions of §5.4;
server-side re-classification at telemetry ingest; teacher weight-override
validation and audit logging; the measurement-invariance warning of §5.9;
session- and student-ownership enforcement (a teacher may read or act on
only the students explicitly mapped to them; a student may read or act on
only their own sessions); the account-provisioning and lifecycle flows of
§3; and an explicit "contract" test that feeds the backend a payload shaped
exactly like the frontend's own real telemetry submission, so that a field
rename
on either side of that boundary breaks a test immediately rather than
surfacing as a silent runtime mismatch.

### 7.2 Frontend Test Suite

The frontend carries four `vitest` test modules totaling **62 automated
tests**: sentence-boundary splitting for the text-to-speech queue; the
webcam-consent gating logic of §4.6 across every combination of disability,
preference, and consent state; fuzzy/phonetic fill-in-the-blank answer
matching for profiles where a spelling slip should not read as a knowledge
gap; and the full voice-intent rule set of §4.1, including the priority
ordering between competing intents and byte-for-byte parity checks against
the backend's independent Python implementation of the same rules.

### 7.3 Build Integrity

A production frontend build (`vite build`) completes without error against
the current source tree, and both automated test suites report a clean
(zero-failure) result as of this report.

### 7.4 The Patent Claim-Support Dossier Generator

Beyond conventional testing, the repository includes a purpose-built
verification tool, `backend/scripts/build_dossier.py`, that treats a set of
formally stated technical claims as data to be mechanically re-checked
against the live repository rather than as prose to be taken on faith. A
human-authored claim map (`docs/claims/claim_map.yaml`) currently tracks six
claims, each decomposed into two to four elements, spanning: disability-profile-weighted
scoring with diagnostic-only exclusion, renormalization, and reported
coverage (§5.5); personal-baseline, confidence-scored, abstention-capable
error classification (§5.3); confidence-gated re-presentation of a simpler
item variant (§5.3); a renormalizing, interaction-only hesitation index
(§5.6); independently re-verified, non-generative multi-step arithmetic
with deterministic error typing (§4.3); and dual-axis written-response
scoring with evidentiary concept-coverage verification (§4.4).

For every element, the generator resolves two independent citations: a code
citation, verified for a Python symbol by actually importing the module and
retrieving the named symbol via `getattr` — not merely confirming the name
appears as text in the file — and, for a test citation, by *executing* the
cited test as a subprocess (`pytest <file> -k <test name>`) and requiring an
explicit "passed" result, rather than merely confirming a function of that
name exists. The generator additionally embeds a SHA-256 hash of the live
DASE configuration file as machine-checkable evidence that a claim resting on
a specific weighting scheme is tied to the configuration actually shipped,
not a configuration described only in prose. The tool writes a structured
JSON artifact and a human-readable Markdown rendering to
`docs/claims/patent_dossier.json` and `docs/claims/patent_dossier.md`
respectively, and exits with a non-zero status if any citation fails to
resolve — the companion, administrator-gated `GET /api/admin/dossier`
endpoint serves only this pre-built artifact and never regenerates it inside
a live request, since doing so would mean re-running the entire test suite
on every dashboard load.

The generator has been run against this working copy: all 17 elements
across all 6 tracked claims (C1–C6) resolved — every cited code symbol
imported and inspected successfully, and every cited test actually ran and
passed. The build is also now wired into the ordinary backend test suite
itself (`backend/tests/test_dossier_build.py`), which invokes
`scripts/build_dossier.py` as a subprocess and fails if its exit status is
non-zero — a future rename of a cited symbol, or a regression in a cited
test, surfaces as an ordinary `pytest` failure rather than silently going
unnoticed until someone remembers to run the dossier script by hand before
a submission.

---

## 8. Conclusion

EduEase demonstrates that a disability-adaptive scoring philosophy can be
carried through an entire system rather than bolted on as a presentation
layer: the same measured behavioral signals are deliberately read through a
different, config-driven lens per declared disability; a wrong answer is
never left as an undifferentiated failure when a deterministic,
confidence-scored cause is available instead; and every one of these
claims is backed by an automated test, with a dedicated tool able to prove,
mechanically and on demand, that the citation between a claim and its
supporting code and test still holds against the repository as it actually
stands today. The 253 backend and 62 frontend tests, the clean production
build, and the claim-support dossier generator together constitute the
verification basis for the engineering contributions described in this
report.
