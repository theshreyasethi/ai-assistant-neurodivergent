/**
 * Thin convenience wrapper around services/speech.ts, for call sites that
 * just want "speak this text" without the full sentence-queue API
 * (speakSentences' onSentenceStart/onWordBoundary callbacks). Every
 * speechSynthesis call in this app still ultimately goes through
 * speech.ts's shared token, so stopSpeaking()/Escape still wins over
 * anything spoken via this module too.
 */

import { isSpeaking, speakOnce, speakSentences, splitIntoSentences, stopSpeaking } from './speech';

export function speak(text: string, rate = 1, lang?: string): void {
  speakOnce(text, { rate, lang });
}

/** Splits `text` into sentences and queues them — for a longer passage
 * where per-word granularity (LearningPage's own highlight sync) isn't
 * needed. Returns a stop() function. */
export function speakLong(text: string, rate = 1, lang?: string): () => void {
  return speakSentences(splitIntoSentences(text), { rate, lang });
}

export { isSpeaking, stopSpeaking };
