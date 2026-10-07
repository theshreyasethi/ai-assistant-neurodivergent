# Roadmap — scope decisions and current status

Merges what were three overlapping documents (`upgrade_implementation_plan.md`,
`IMPLEMENTATION_ROADMAP.md`, `docs/future-work.md`) into one. The original
research-to-plan draft and its since-superseded DASE formula draft are
dropped entirely — the corrected, actually-implemented formulas are in
[PROJECT_EXPLANATION.md §4.6](PROJECT_EXPLANATION.md#46-dase--the-disability-adaptive-scoring-engine).
What actually happened phase-by-phase, with bugs and fixes, is in
[PHASE_LEARNINGS.md](PHASE_LEARNINGS.md). This doc keeps only what's still
useful going forward: the scope triage and current per-disability status.

## Scope triage (original v2.0 planning)

The original plan spanned ~10–13 weeks across 5 phases and ~25 new files.
What was judged worth building, in order:

| Phase | Item | Why |
|---|---|---|
| P0 | Disability profile + telemetry persistence + backend consolidation | Everything else is blocked on this |
| P1 | LLM quiz generation + LLM simplification profiles | Fixes garbage-in for DASE |
| P2 | DASE v1 (measured params only) + error classifier + closed loop | The core novelty |
| P3 | Blind: voice navigation + voice-first chatbot + image descriptions | Biggest inclusivity gap |
| P4 | Teacher dashboard on real data: radar, error breakdown, LLM recommendations | Turns telemetry into something a teacher can act on |
| P5 | Deaf: deaf simplification profile + visual alerts | |
| P6 | UI pass: icons/images on every action | |

**Promoted to in-scope, each roughly a day once P1's prompt-profile
mechanism existed:** dyscalculia mode, anxiety mode (without webcam-based
anxiety detection), dysgraphia voice-to-text, an Easy-Read profile for
intellectual disability.

**Deliberately cut, and why:**

| Cut | Reason |
|---|---|
| Bidirectional sign-language recognition (MediaPipe → GNN) | Multi-year research problem, not buildable in this scope |
| Sign language dictionary popup | No free, licensable ASL/ISL video API with usable coverage |
| Webcam anxiety detection (blink rate, lip pressing) | Not measurable with face-landmark tracking; inferring a clinical state from it is unsupportable and an ethics liability. Interaction-pattern signals (answer changes, long pauses) are kept and called *hesitation*, never *anxiety* |
| `pacing_engine.py` as a separate service | It's one number — the student's own median response time — folded into DASE's `TIME_EFF` baseline instead |
| POS colour-coded text | No evidence it helps deaf readers specifically |
| Proactive accessibility analyzer | Alt-text generation via image description already covers the adjacent need |

## Current implementation status by disability

**Updated post patent-readiness remediation (P1-P5 — see "Patent-readiness
remediation" section below; a separate, later numbering track from the
phase log in PHASE_LEARNINGS.md).** DASE can score all 13 profiles
declared in `dase_profiles.json`, and content generation now covers all
13 — P4-05 closed the remaining 4:

| Disability | Simplify + quiz content profile | DASE scoring profile |
|---|---|---|
| dyslexia, deaf, autism, adhd, blind, dyscalculia, intellectual, anxiety, low_vision, hard_of_hearing, dysgraphia, motor | ✅ dedicated | ✅ dedicated |

## Known gaps, not yet built

Several items this section used to list are now built — see
"Patent-readiness remediation" below for what changed and when:

- ~~DASE closed-loop UI~~ — built (P3-03). `QuizPage.tsx` calls
  `/api/classify` on every wrong answer and re-presents the simpler variant
  in place on a confident `COMPREHENSION_BARRIER`.
- ~~Voice navigation UI~~ — built (Phase 2 of the remediation track).
  `VoiceNavigator.tsx` + `VoiceBootstrap.tsx` are mounted globally; a
  student can navigate, answer, and control playback by voice.
- ~~`FRUST` DASE parameter~~ — renamed `RESIL` and given a real data
  source: `RESIL = 1 - HES`, an interaction-only hesitation index (latency
  vs personal baseline, answer changes, tab-blur count, mean chatbot
  frustration_score — `services/hesitation.py`, P4-14).
- ~~`VIS_ENG`~~ — real data source as of P4-01: `VisualSummary.tsx` emits
  dwell/expansion/replay events, loaded into `/api/evaluate`. Not yet
  exercised by real student usage, so treat the *formula* as implemented
  and the *parameter's validity* as unproven, same caveat as every DASE
  parameter.
- ~~`WRIT_EXP`~~ — removed. Replaced by `KNOW` (scored) and `EXPR`
  (diagnosticOnly) for dysgraphia, per P4-10 — see
  `services/writing_score.py`.

Genuinely still open:

- `PATTERN` (autism) has a real computation (`services/dase_engine.py`'s
  `_pattern()`, reading `itemKind` from `services/quiz_gen.py`) but has
  never been validated against real items at scale.
- The classifier (`classify_error`) has never been validated against
  human judgement on real session data — still "a classifier with a
  stated confidence model," not "an accurate classifier."
- No screen reader (NVDA/JAWS/VoiceOver) has been run against the voice
  layer or the broader accessibility baseline.
- `docs/claims/claim_map.yaml` / `backend/scripts/build_dossier.py`
  (P5-08) only verify that referenced code and tests exist and pass —
  they are not legal advice and do not establish novelty or validity.
  See `docs/PRE_FILING_CHECKLIST.md`.

## Patent-readiness remediation (P1-P5)

A separate, later engagement — a structured audit (`patent_readiness_plan.html`)
against this codebase, followed by five remediation phases (task IDs
`P1-01`...`P5-09`). Summarized, not logged turn-by-turn the way
PHASE_LEARNINGS.md's Phase 0-6 are: Phase 1 closed critical auth/
provisioning/ownership findings; Phase 2 built the voice-first layer
described above; Phase 3 fixed five wrong DASE formulas (`ADJ_ACC`,
`CONSIST`, `TIME_EFF`, `TASK_COMP`, `LRN_VEL`) and added `PATTERN`/`RESIL`,
teacher weight overrides, and a real backend test suite + ablation script;
Phase 4 built DHH visual summaries, sign glossary, math manipulatives, the
dysgraphia writing pipeline, calm mode, auto-pacing and the completed
hesitation index; Phase 5 rebuilt the teacher dashboard onto the scoped
analytics API and produced the claim-support dossier tooling referenced
above. Every phase's commits are tagged with their task IDs in the commit
message; `git log --grep "P[1-5]-"` finds them.
