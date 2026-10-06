/**
 * Short, quiet, non-speech Web Audio cues — additive to speech, never a
 * replacement for it (research doc: blind students need structural cues,
 * not just more words). Reuses the one AudioContext services/speech.ts
 * unlocks on the first user gesture; every cue here is a silent no-op
 * before that unlock has happened, rather than throwing — the browser
 * would block the audio anyway, so failing loudly here would just be
 * console noise with no user-visible difference.
 */

import { getAudioContext } from './speech';

type Cue = [freq: number, atOffset: number, duration?: number, type?: OscillatorType, volume?: number];

function tone(ctx: AudioContext, freq: number, atOffset: number, duration = 0.12, type: OscillatorType = 'sine', volume = 0.12): void {
  const t0 = ctx.currentTime + atOffset;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  // Exponential ramps (never a hard on/off) avoid the audible click a step
  // change produces, and 0.0001 (not 0) is required — exponentialRampToValueAtTime
  // cannot target exactly zero.
  gain.gain.setValueAtTime(0.0001, t0);
  gain.gain.exponentialRampToValueAtTime(volume, t0 + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(t0);
  osc.stop(t0 + duration + 0.02);
}

function play(cues: Cue[]): void {
  const ctx = getAudioContext();
  if (!ctx) return;
  cues.forEach(([freq, at, dur, type, vol]) => tone(ctx, freq, at, dur, type, vol));
}

/** Each cue is < 300ms total and quiet by default — meant to be heard
 * alongside speech, not over it. */
export const earcon = {
  /** Rising two-tone — a new heading / page section. */
  heading: () => play([[523, 0, 0.1, 'triangle'], [784, 0.11, 0.14, 'triangle']]),
  /** A single soft tick — a paragraph/content boundary during reading. */
  content: () => play([[392, 0, 0.05, 'sine', 0.06]]),
  /** Three-note rising motif — a quiz question has appeared. */
  question: () => play([[440, 0, 0.09, 'square', 0.05], [554, 0.1, 0.09, 'square', 0.05], [659, 0.2, 0.12, 'square', 0.05]]),
  /** Rising two-tone, lower and faster than `heading` — the mic just opened. */
  micOpen: () => play([[440, 0, 0.08], [660, 0.09, 0.1]]),
  /** Falling two-tone — a voice command was not understood. */
  notUnderstood: () => play([[660, 0, 0.08], [330, 0.09, 0.14]]),
};
