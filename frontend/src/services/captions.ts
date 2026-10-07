/**
 * Persistent "what was said/happened" caption log (roadmap P4-02) — every
 * spoken TTS utterance, quiz feedback message, timer/countdown announcement
 * and teacher message gets a line here, not just a toast that disappears
 * after a few seconds. For a deaf/hard-of-hearing student with sound off,
 * this is the only record of anything the app would otherwise only have spoken.
 */

export interface CaptionEntry {
  id: number;
  text: string;
  ts: number;
}

const MAX_LOG = 200;
let seq = 0;
let log: CaptionEntry[] = [];

export const CAPTION_ADDED_EVENT = 'app:caption-added';

export function addCaption(text: string): void {
  const trimmed = text.trim();
  if (!trimmed) return;
  const entry: CaptionEntry = { id: ++seq, text: trimmed, ts: Date.now() };
  log = [...log, entry].slice(-MAX_LOG);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<CaptionEntry>(CAPTION_ADDED_EVENT, { detail: entry }));
  }
}

export function getCaptions(): CaptionEntry[] {
  return log;
}

export function clearCaptions(): void {
  log = [];
}
