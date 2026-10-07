/**
 * Owns every use of window.speechSynthesis in this app. No other file may
 * construct a SpeechSynthesisUtterance directly — before this existed,
 * LearningPage, Eye and AccessibleNotification each called speechSynthesis
 * independently, with no shared priority: LearningPage spoke one utterance
 * PER WORD at reading speed (flooding Chrome's queue and drifting out of
 * sync with the highlight), and nothing let "stop" actually win over
 * whatever was mid-sentence, since a later caller's cancel() only affects
 * the queue, not a sibling's independent utterance objects already playing.
 *
 * Centralising it fixes both: speakSentences() queues one utterance per
 * SENTENCE (not per word — Chrome's long-utterance cutoff and prosody both
 * suffer per-word), using onboundary callbacks to report word-level timing
 * for a highlight to follow; and every speak call shares one monotonic
 * `token`, so stopSpeaking() (or simply calling speakSentences() again)
 * always wins over anything still in flight, which is what STOP/Escape
 * needs to mean for a blind user mid-utterance.
 */

import { addCaption } from './captions';

let token = 0;
let audioCtx: AudioContext | null = null;

/** Call inside a user-gesture handler (keydown/pointerdown). Browsers block
 * both speechSynthesis and AudioContext until a real gesture has occurred;
 * this is the one place that unlock happens, shared by speech and earcons. */
export function unlockAudio(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const Ctor = window.AudioContext || (window as any).webkitAudioContext;
  if (!Ctor) return null;
  if (!audioCtx) audioCtx = new Ctor();
  if (audioCtx.state === 'suspended') void audioCtx.resume();
  return audioCtx;
}

/** Used by services/earcons.ts — returns null (never throws) before
 * unlockAudio() has run once, so an earcon call before the first user
 * gesture is a silent no-op rather than an error. */
export function getAudioContext(): AudioContext | null {
  return audioCtx;
}

/** Pure, DOM-free — the actual input to the sentence queue below, and the
 * one piece of this module worth unit-testing without a real browser. */
export function splitIntoSentences(text: string): string[] {
  const trimmed = (text || '').trim();
  if (!trimmed) return [];
  return trimmed
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** STOP/Escape always wins: bumps the token so every in-flight
 * speakSentences() call's continuation sees a mismatch and stops queueing
 * further utterances, then cancels whatever the browser is currently
 * speaking. */
export function stopSpeaking(): void {
  token += 1;
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
}

export function isSpeaking(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window && window.speechSynthesis.speaking;
}

export interface SpeakOptions {
  rate?: number;
  lang?: string;
  onSentenceStart?: (sentenceIndex: number) => void;
  onWordBoundary?: (sentenceIndex: number, charIndex: number, word: string) => void;
  onDone?: () => void;
}

/**
 * Speaks an array of sentences, one SpeechSynthesisUtterance per sentence.
 * Returns a stop() function. Calling it — or calling stopSpeaking(), or
 * calling speakSentences() again from anywhere else — always takes
 * priority over whatever this call queued next, by design: there is
 * exactly one shared token, and every continuation checks it before
 * speaking another sentence.
 */
export function speakSentences(sentences: string[], opts: SpeakOptions = {}): () => void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window) || sentences.length === 0) {
    opts.onDone?.();
    return () => {};
  }

  window.speechSynthesis.cancel();
  const mine = ++token;
  let i = 0;

  const next = () => {
    if (mine !== token) return;
    if (i >= sentences.length) {
      opts.onDone?.();
      return;
    }
    const sentence = sentences[i];
    const sentenceIndex = i;
    opts.onSentenceStart?.(sentenceIndex);
    // Every spoken utterance is captioned (roadmap P4-02) — a persistent
    // record for a viewer who has sound off, not just the toast that
    // triggered it (which may have a shorter `speak` than `message`, or no
    // visible toast at all for a silent announcement).
    addCaption(sentence);

    const u = new SpeechSynthesisUtterance(sentence);
    u.rate = opts.rate ?? 1;
    u.lang = opts.lang ?? (typeof document !== 'undefined' ? document.documentElement.lang : '') || 'en-US';
    u.onboundary = (e) => {
      if (mine !== token || e.name !== 'word') return;
      const word = sentence.slice(e.charIndex).split(/\s/)[0] ?? '';
      opts.onWordBoundary?.(sentenceIndex, e.charIndex, word);
    };
    const advance = () => {
      i += 1;
      next();
    };
    u.onend = advance;
    u.onerror = advance; // one bad utterance must not silently stop the whole lesson
    window.speechSynthesis.speak(u);
  };

  next();
  return () => {
    token += 1;
    window.speechSynthesis.cancel();
  };
}

/** One-off utterance (e.g. a voice-command read-back: "Selected B."). Still
 * cancels anything in-flight — the most recent thing asked to speak wins. */
export function speakOnce(text: string, opts: Omit<SpeakOptions, 'onSentenceStart' | 'onWordBoundary'> = {}): void {
  speakSentences([text], opts);
}
