# Demo Walkthrough

A chronological script for demonstrating EduEase end-to-end to a project
teacher/guide. Every button label, field name, and route below was
verified against the current code — not the README's stale demo-account
table (Phase 1 of the patent-readiness remediation deliberately removed
hardcoded demo credentials; see `docs/ROADMAP.md`). Follow this script
verbatim rather than paraphrasing from memory the night before.

**Structure:** one admin, one teacher, and one student account. The
student's disability profile is changed live via Settings between
sections 2-4 (self-service, not something an admin sets at creation) —
you are not creating four separate students.

---

## Before you start (do this the night before, not live)

- [ ] Both servers running: `cd backend && python -m uvicorn app:app --reload --port 8000` and `cd frontend && npm run dev`.
- [ ] **No admin account exists by default.** Create one now, out-of-band:
  ```bash
  cd backend && python scripts/create_admin.py --email your.name@yourschool.org
  ```
  It prompts for a password (10+ characters) and prints the account once. Write it down — this is your login for Section 1.
- [ ] Have a short PDF or text passage ready to upload (a one-page science or history excerpt works well — needs enough content for a lesson + 9-question quiz).
- [ ] Open the app at `http://localhost:5173` in a browser window large enough to show the dashboard comfortably; close other tabs that might trigger notification sounds.
- [ ] If you want voice recognition to work, use **Chrome or Edge** — `SpeechRecognition` is not implemented in Firefox/Safari, and the app will say so honestly rather than silently failing.

---

## 1. Admin & Account Setup Flow

**Goal:** show that no one can self-register, every account is provisioned deliberately, credentials are shown exactly once, and a forced password change is actually enforced server-side — not just a frontend nag.

- Go to `http://localhost:5173/login`.
- **Say:** "There's no public sign-up — every account is provisioned by an admin. Let me log in as the school admin."
- Log in with the admin credentials from the setup step (fields are labeled **"Email Address"** and **"Password"**, button **"Sign In"**).
- You land on the Admin Dashboard.

### Create a teacher
- Find the **"Create New User"** card. Click the **"Teacher"** role button.
- Fill **Display Name** (e.g. "Maria Chen") and **Username** (e.g. "maria.chen" — lowercase, dots/hyphens/underscores only, 3-32 chars).
- Click **"Create Account"**.
- **A "Account credentials" modal pops up** — this is the key moment. **Say:** "This is shown exactly once. If I close it without copying, it's gone — there's no way to retrieve a temporary password later, only to issue a new one."
- Point out the subtitle: *"Shown once. Hand this to {name} directly — it is not saved anywhere you can come back to later."*
- Click **"Copy"**. **Check:** a toast appears ("Credentials copied to clipboard"), and — if your profile has voice-first or screen-reader settings off — a brief border-pulse flashes around the viewport edge. Mention this is the same non-audio alert channel you'll demo properly in Section 3.
- Click **"Done"**. Paste the copied credentials into a scratch note — you'll need them in a moment.

### Create a student, mapped to that teacher at creation time
- Click the **"Student"** role button. Fill Display Name/Username.
- **Say:** "Notice the extra fields that only appear for a student." Point out **"Grade Level"** and **"Assign Teacher"**.
- **Check:** try clicking "Create Account" with no teacher selected — it's disabled with the message *"Students must be assigned to an active teacher."* **Say:** "A student can never exist without an active teacher — that was one of the findings from the original audit, where this wasn't enforced at all."
- Select the teacher you just created, click **"Create Account"**.
- Copy the student's credentials the same way.

### Prove the first-login password change is server-enforced
- Log out. Log in as the **student**, using the temporary password.
- You're redirected to `/first-login` — **Say:** "The backend itself refuses every other request until this happens. This isn't a frontend redirect I could skip by typing a different URL."
- Enter a new password twice (field labels: **"New password"**, **"Type it again to confirm"**; 10+ characters). Click **"Save new password"**.
- **Check:** you're signed out automatically and sent back to `/login` with a toast reading *"Password changed. Please sign in again with your new password."*
- Log in again with the **new** password — this is the account you'll use for the rest of the demo.

---

## 2. Student Accessibility Profiles — Blind / BVI Flow

**Goal:** show voice-first navigation and quiz-answering, and that the webcam is never even requested for this profile — not hidden, never mounted.

### Set the profile
- Go to **Settings** → **"Your support profile"** section.
- Check **"Blind"**. (It saves immediately — no Save button.)
- **Check:** scroll to the webcam-related toggle ("Camera focus check") — **it's not there at all** for this profile. **Say:** "This isn't disabled, it's not offered — the option to turn on a camera doesn't exist for a blind or low-vision profile, regardless of any stored preference."

### Upload a lesson (needed for the quiz step)
- Go to Upload, pick your prepared PDF/passage, let it simplify and generate a lesson.

### Voice navigation
- **Say:** "Push-to-talk is Control+Shift+V — nothing is ever listening by default."
- Press **Ctrl+Shift+V**. **Check:** the floating mic button turns red and pulses, `aria-label` changes to "Listening for your command" — point out this is also audible as an earcon tone for a student who can't see the button.
- Say **"go to dashboard"** (or similar) — confirm it navigates.
- Press **Ctrl+Shift+V** again, say **"help"** — confirm it lists available commands aloud.

### Answer a quiz entirely by voice
- Navigate to the quiz for your uploaded lesson.
- Press **Ctrl+Shift+V**, say **"answer B"** (or whichever letter). **Check:** you hear a read-back — *"Selected B. [answer text]. Say submit to confirm."* **Say:** "This read-back matters because speech recognition can mis-hear — the student gets to catch that before it becomes a wrong answer, which is something a sighted UI doesn't need."
- Press **Ctrl+Shift+V**, say **"submit"**. **Check:** it advances to the next question.
- Repeat for 2-3 more questions, then let the quiz finish normally — **this quiz needs to actually complete**, because it's the DASE evaluation you'll show the teacher in Section 5.
- Press **Escape** at any point mid-speech to show it stops instantly.

---

## 3. Student Accessibility Profiles — Deaf / DHH Flow

**Goal:** show the visual-summary generator and the non-audio alert/caption-log system.

### Switch profiles
- Settings → uncheck "Blind", check **"Deaf"** (or "Hard of hearing").

### Visual summary
- Go back to **Learning** with the same lesson open (or re-open it from Content/Dashboard).
- **Say:** "This only generates on request — it's a real LLM call, so it never fires automatically on page load."
- Click **"Show visual summary"**.
- **Check:** a Mermaid.js diagram appears (if the lesson has a clear sequence/structure) plus 3-6 concept cards with an emoji and one-sentence explanation each. Expand a card — **Check:** expanding and a few seconds of dwell time are both silently tracked as engagement telemetry (`VIS_ENG`, shown later in the DASE radar if it populates).
- Point out the **"View as text"** `<details>` toggle below it — **Say:** "The diagram and cards are never the only representation — there's always a plain-text fallback."
- Also visible on this page for this profile: the **sign-glossary** word popovers (tap any underlined word) and the **experimental POS color-tagging** panel — mention both are explicitly labeled experimental.

### Non-audio alert + caption log
- Go to **Account** (top nav). Change your display name slightly, click **Save**.
- **Check:** a toast reads "Account details saved," a brief **border-pulse** flashes around the viewport edge, and — click the **"Captions"** button (bottom-left of the screen) — **Check:** the same message appears in the persistent caption log, timestamped.
- **Say:** "Every one of these events — toasts, quiz feedback, system messages — gets a line in this log independent of whether sound was ever on. That's the point: a deaf or hard-of-hearing student with sound off still has a full record of what happened."

---

## 4. Specialized Disability Pipelines — Dyscalculia & Dysgraphia

### Dyscalculia: math manipulatives + verified step-by-step
- Settings → uncheck "Deaf", check **"Dyscalculia (maths)"**.
- Take (or retake) the quiz until you land on a **fill-in-the-blank question with a numeric answer** (not every question qualifies — this is deliberate, it's not offered for non-numeric items).
- **Check:** beside the question, a **"Try it with blocks"** panel appears (a keyboard-operable number line — try arrow keys, not just clicking) alongside a **"Show step by step"** button.
- Click **"Show step by step"**. **Say:** "Every step here was independently re-verified by a restricted math evaluator before being shown — the model never gets to just assert a number is right." Click **"Play"** — it speaks each step while the block display updates to match.

### Dysgraphia: voice-to-essay with split scoring
- Settings → uncheck "Dyscalculia", check **"Dysgraphia (writing)"**.
- Go to the **Dashboard** — **Check:** a new card appears: **"Practice writing by voice."** (It only appears for this profile.)
- Click it. In the modal, click **"Start dictating"** and speak a few sentences about anything you learned recently (or type into the box if you'd rather not rely on mic pickup for the demo). Click **"Stop dictating"**.
- Click **"Organize into an essay"** — **Check:** an outline plus organized paragraphs appear, using your own words.
- Click **"Check my answer"** — **Check:** it reports "Concepts covered: X%" with the note: *"Writing mechanics are shown separately and never affect how much credit you get for what you know."*
- **Say:** "That's the core idea for this profile — a spelling or grammar slip should never look like a knowledge gap. Two answers with the same content and different spelling get the same knowledge score."

---

## 5. Teacher Analytics & DASE Dashboard

**Goal:** show the scoped roster, the per-student charts with their accessible table twins, and a teacher-adjustable weight override with a mandatory audit reason.

- Log out, log in as the **teacher** account from Section 1.
- You land on **"Classroom Overview."**
- **Check:** the roster shows only this teacher's own student(s) — **Say:** "This is scoped server-side. A teacher can't see a student who isn't theirs by guessing a different ID — that was one of the critical findings in the original audit, and it's enforced on every request, not just hidden in the UI."
- Point out the disclaimer box above the roster: focus/attention figures measure face presence, not actual attention — **Say:** "That distinction is stated explicitly, not buried in a tooltip, because it qualifies every number below it."
- Click the student's row (button reads **"View Analytics"**, becomes **"Selected"**).
- **Check:** if the quiz from Section 2 completed, you should now see:
  - A **DASE radar chart** — point out any dashed axis (a "reported, not scored" diagnostic-only parameter) and the **"View as table"** toggle beneath it. **Say:** "Every chart on this page has a table twin — a screen-reader user gets the same information a sighted user gets from the chart, not less."
  - An **error-cause donut** (knowledge gap / attention lapse / processing delay / comprehension barrier), with an explicit "unclassified" slice if any answers couldn't be confidently classified.
  - The **"DASE score · coverage"** figure in the roster row itself — **Say:** "Coverage is shown next to every score on purpose — a score computed from 40% of the intended signals is a weaker claim than one from 90%, and this never lets a teacher forget that."
- Click **"Get teaching suggestions"** — an LLM-generated, data-grounded note appears.

### Weight override with mandatory audit reason
- Scroll to **"DASE weight override."**
- Check one or two parameter boxes, adjust the number inputs.
- **Check:** try clicking **"Save override"** with the reason field empty — **it's disabled.** Type a reason (e.g. "Student shows more test anxiety than attention-related distraction based on classroom observation"), and the button enables.
- Click **"Save override."** **Check:** the panel now reads *"An override is active for this student. Reason on file: ..."*
- Click **"View weight-override history"** (top of the page) → `/audit-log`. **Check:** your override appears with the exact reason you typed, timestamped.
- **Say:** "Every one of these is logged server-side with the reason, not just applied silently — that's the audit trail a teacher override needs to be defensible."

---

## If something doesn't go as planned

- **No DASE chart appears in Section 5:** the student's quiz from Section 2 must actually reach the completion screen (not be abandoned partway) for an evaluation to exist. Have a backup: complete one short quiz live, right before switching to the teacher login.
- **Voice recognition doesn't pick up speech:** confirm you're in Chrome/Edge, confirm the browser's mic permission prompt was accepted on first use, and have a keyboard-only fallback path memorized (the voice steps are a bonus, not the only way to answer).
- **Visual summary returns "could not build a visual summary":** this calls a real LLM (Gemini, with a Groq fallback) — if both are rate-limited or down, say so plainly rather than retrying live on stage; it's a known, documented dependency, not a bug.
- **Mermaid diagram doesn't render for your passage:** this is expected and correct behavior for a passage with no clear sequence/structure — the generator deliberately returns `diagram: null` rather than inventing false connections, and the concept cards + text fallback still work. Pick a passage with an obvious process (a cycle, a sequence of causes) if you want the diagram specifically.
