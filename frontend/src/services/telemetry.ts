/**
 * Telemetry client — buffers learning events and flushes them to the backend.
 * Event shapes are frozen in DATA_CONTRACT.md v1 (§3).
 *
 * Design rule: telemetry must NEVER break the lesson. Every failure path here is
 * swallowed and logged. A student losing their quiz because an analytics POST
 * 500'd is strictly worse than losing the analytics.
 *
 * Uses the shared `api` axios client (not raw fetch, unlike master's original)
 * so every call carries the Firebase ID token the merged backend's
 * Depends(verify_user) now requires on every /api/* route.
 */

import { auth } from './firebase';
import api from './api';

/** Error-cause label from POST /api/classify — mirrors
 * backend/models/schemas.py's Classification (roadmap P3-03). */
export interface Classification {
  label: 'KNOWLEDGE_GAP' | 'ATTENTION_LAPSE' | 'PROCESSING_DELAY' | 'COMPREHENSION_BARRIER';
  confidence: number;
  alternatives: string[];
  signals: Record<string, unknown>;
}

export interface QuestionEvent {
  type: 'question';
  sessionId: string;
  studentId: string;
  ts: number;
  questionId: string;
  conceptId: string | null;
  topic: string | null;
  difficulty: number;
  questionType: string;
  /** Autism/PATTERN (roadmap P3-07): sequence/category/matching tag from
   * the quiz generator. null for older or spaCy-fallback items. */
  itemKind: string | null;
  selected: string | null;
  correct: boolean;
  timeMs: number;
  timeToFirstInteractionMs: number | null;
  attempts: number;
  answerChanges: number;
  hintsUsed: number;
  revisits: number;
  reRead: boolean;
  focusRatio: number | null;
  focusSamples: number;
  isRepresentation: boolean;
  originalQuestionId: string | null;
  /** Set by the closed loop (POST /api/classify) on a wrong answer only —
   * roadmap P3-03. The server re-stamps this on ingest if it's missing or
   * stale, so a client never has the final say over its own label. */
  classification: Classification | null;
  classifierVersion: string | null;
  /** spaCy-fallback item (LLM unreachable): never reviewed for quality,
   * excluded from DASE scoring entirely (roadmap P3-11). */
  degraded: boolean;
  /** PHASE 4 (P4-10) — short_answer items only, from services/writing_score.py. */
  know: number | null;
  expr: number | null;
  /** PHASE 4 (P4-14) — tab-blur count while this question was on screen, one
   * of HES's interaction-only inputs. Never facial/webcam data. */
  blurCount: number;
}

export interface ReadingEvent {
  type: 'reading';
  sessionId: string;
  studentId: string;
  ts: number;
  contentId: string | null;
  wordsRead: number;
  wpmSetting: number;
  elapsedMs: number;
  replays: number;
  ttsUsed: boolean;
  pauseCount: number;
  focusRatio: number | null;
  focusSamples: number;
  simplifyProfile: string;
}

/** PHASE 3 — feeds VOICE_Q and NAV_EFF. Emitted by VoiceNavigator.tsx into
 * whichever session is currently registered via setCurrentSession(). */
export interface VoiceEvent {
  type: 'voice';
  sessionId: string;
  studentId: string;
  ts: number;
  transcript: string;
  sttConfidence: number;
  intent: string;
  intentSource: string;
  intentConfidence: number;
  understood: boolean;
  repeats: number;
  actionMs: number | null;
  route: string | null;
}

/** PHASE 4 (P4-01) — feeds VIS_ENG. Emitted by VisualSummary.tsx into
 * whichever session is currently registered via setCurrentSession(). */
export interface VisualEvent {
  type: 'visual';
  sessionId: string;
  studentId: string;
  ts: number;
  contentId: string | null;
  conceptTitle: string | null;
  dwellMs: number;
  expanded: boolean;
  replayed: boolean;
}

export type LearningEvent = QuestionEvent | ReadingEvent | VoiceEvent | VisualEvent;

const FLUSH_SIZE = 10;
const FLUSH_MS = 5000;

let buffer: LearningEvent[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;

// The session VoiceEvent telemetry is attributed to — VoiceNavigator.tsx is
// mounted once, globally, and has no page-local session ref of its own, so
// whichever page currently owns a learning session (QuizPage, LearningPage)
// registers it here. A voice command on a page with no active session
// (the dashboard, say) simply has nowhere to attribute telemetry to, which
// track() already handles by dropping events with no sessionId.
let currentSessionId: string | null = null;
// Chatbot sentiment scores for the CURRENT session (roadmap P4-14) — one of
// HES's interaction-only inputs. Reset whenever the active session changes,
// since a frustration score from a PREVIOUS quiz session must never bleed
// into this one's hesitation index.
let chatFrustrationScores: number[] = [];

export function setCurrentSession(sessionId: string | null): void {
  if (sessionId !== currentSessionId) chatFrustrationScores = [];
  currentSessionId = sessionId;
}

export function getCurrentSession(): string | null {
  return currentSessionId;
}

/** Chatbot.tsx calls this with each turn's frustration_score. */
export function recordChatFrustration(score: number): void {
  chatFrustrationScores.push(Math.max(0, Math.min(1, score)));
}

/** Read at quiz-end time and sent as SessionSummary.meanChatFrustration —
 * null when the chatbot was never opened this session, never 0 (0 would
 * read as "calm", which is a claim this has no basis to make). */
export function getMeanChatFrustration(): number | null {
  if (!chatFrustrationScores.length) return null;
  return chatFrustrationScores.reduce((a, b) => a + b, 0) / chatFrustrationScores.length;
}

export async function startSession(
  studentId: string,
  kind: 'quiz' | 'reading',
  contentId: string | null = null,
): Promise<string | null> {
  try {
    const { data } = await api.post('/api/sessions', { studentId, kind, contentId });
    return data.sessionId;
  } catch (err) {
    console.warn('[telemetry] startSession failed; running un-instrumented', err);
    return null;
  }
}

export function track(event: LearningEvent): void {
  if (!event.sessionId) return; // session never started — drop silently
  buffer.push(event);
  if (buffer.length >= FLUSH_SIZE) {
    void flush();
  } else if (!timer) {
    timer = setTimeout(() => void flush(), FLUSH_MS);
  }
}

export async function flush(): Promise<void> {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  if (!buffer.length) return;

  const batch = buffer;
  buffer = [];
  try {
    await api.post('/api/events', { events: batch });
  } catch (err) {
    console.warn('[telemetry] flush failed, re-queueing', err);
    // Put them back at the front so ordering survives a transient failure,
    // but cap the buffer so an offline session can't grow without bound.
    buffer = [...batch, ...buffer].slice(-100);
  }
}

export async function endSession(
  sessionId: string | null,
  summary: {
    totalQuestions: number;
    correct: number;
    totalTimeMs: number;
    completed: boolean;
    meanFocusRatio: number | null;
    meanChatFrustration?: number | null;
  },
): Promise<void> {
  await flush();
  if (currentSessionId === sessionId) currentSessionId = null;
  if (!sessionId) return;
  try {
    await api.patch(`/api/sessions/${sessionId}`, { summary });
  } catch (err) {
    console.warn('[telemetry] endSession failed', err);
  }
}

/**
 * Computes and persists this session's DASE score.
 *
 * The evaluate endpoint (backend/routers/evaluation.py) exists but nothing
 * calls it unless a page does so explicitly — sessions can end, telemetry
 * gets recorded, and no evaluation document is ever written, leaving the
 * teacher dashboard's roster/student endpoints with nothing to read.
 *
 * Called AFTER endSession, since evaluate reads the session's events from
 * Firestore and a session ended mid-write would be scored on a partial summary.
 * Best-effort: a failed evaluation must not block the student from seeing their
 * quiz results.
 */
export async function triggerEvaluation(
  sessionId: string | null,
  studentId: string,
  profile: string,
): Promise<void> {
  if (!sessionId || !studentId) return;
  try {
    await api.post('/api/evaluate', { sessionId, studentId, profile, persist: true });
  } catch (err) {
    console.warn('[telemetry] evaluate failed', err);
  }
}

/**
 * Authenticated best-effort flush when the tab is hidden or closing
 * (roadmap P3-06). Every /api/* route requires a Bearer token, and
 * navigator.sendBeacon cannot carry an Authorization header at all — the
 * previous sendBeacon-based flush was a guaranteed no-op against this
 * backend, not a fallback. fetch(..., {keepalive: true}) can carry headers
 * and survives the page unloading, which is exactly what's needed here.
 */
async function _flushWithKeepalive(events: LearningEvent[]): Promise<void> {
  try {
    const token = await auth.currentUser?.getIdToken();
    if (!token) return; // not signed in; nothing we can authenticate as
    const apiUrl = (api.defaults.baseURL as string) ?? '';
    await fetch(`${apiUrl}/api/events`, {
      method: 'POST',
      keepalive: true,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ events }),
    });
  } catch {
    // Best-effort: losing this flush is strictly better than throwing while
    // the tab is unloading.
  }
}

function _flushOnHide(): void {
  if (!buffer.length) return;
  const batch = buffer;
  buffer = [];
  void _flushWithKeepalive(batch);
}

if (typeof window !== 'undefined') {
  // visibilitychange fires on every tab switch/minimize, not only on close —
  // flushing there just means telemetry isn't lost if the student never
  // comes back. pagehide is the more reliable close/navigate-away signal in
  // browsers that don't fire visibilitychange on unload consistently.
  window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') _flushOnHide();
  });
  window.addEventListener('pagehide', _flushOnHide);
}

/** Must match backend/services/dase_engine.py's MIN_FOCUS_SAMPLES exactly —
 * below this many samples the webcam signal is not trustworthy (contract §3.1). */
const MIN_FOCUS_SAMPLES = 5;

/**
 * Counts raw per-tick face-presence samples from <Eye>'s onSample callback
 * (roadmap P3-02) and reports the fraction that were on-screen.
 *
 * Previously this time-weighted the gaps between <Eye>'s DEBOUNCED
 * onFocusChange transitions, which fired rarely (only when the 4-second
 * FOCUS_LOST_MS threshold was crossed) — meaning most quiz questions never
 * accumulated the 5 samples needed to report a ratio at all. Counting every
 * 500ms tick directly is simpler and matches what the backend's own
 * MIN_FOCUS_SAMPLES threshold assumes: ticks, not transitions.
 *
 * NOTE: this is FACE PRESENCE (or MediaPipe gaze-on-screen in this merged
 * codebase's Eye.tsx), not a guarantee of attention. Never surface it to
 * teachers as more than a supportive signal.
 */
export class FocusMeter {
  private on = 0;
  private total = 0;

  sample(onScreen: boolean): void {
    this.total += 1;
    if (onScreen) this.on += 1;
  }

  /** Returns null when there is too little data to be meaningful (contract §3.1). */
  read(): { focusRatio: number | null; focusSamples: number } {
    if (this.total < MIN_FOCUS_SAMPLES) return { focusRatio: null, focusSamples: this.total };
    return { focusRatio: +(this.on / this.total).toFixed(3), focusSamples: this.total };
  }

  reset(): void {
    this.on = 0;
    this.total = 0;
  }
}
