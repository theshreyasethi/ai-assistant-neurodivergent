/**
 * Profile-aware notifications — one call site, modality decided per viewer.
 * <AccessibleNotification/> (mounted once in App.tsx) listens and renders
 * the toast channel; <VisualAlert/> (also mounted once) renders the
 * borderPulse/badge channels and the persistent caption log (roadmap P4-02).
 */

import { addCaption } from './captions';

export type NotifyKind = 'info' | 'success' | 'error' | 'listening' | 'thinking';
export type NotifyChannel = 'toast' | 'borderPulse' | 'badge';

export interface NotifyOptions {
  kind?: NotifyKind;
  /** Also speak this via TTS for viewers who have it on. Defaults to the message. */
  speak?: string;
  /** Trigger a phone vibration — meaningful for deaf/hard-of-hearing viewers away
   * from the screen, meaningless everywhere else so keep it rare. */
  vibrate?: boolean;
  durationMs?: number;
  silent?: boolean;
  /** Which non-audio channels accompany this event — never audio alone.
   * Defaults to every channel except badge (badge is for persistent,
   * ongoing states like "listening", not one-off messages). */
  channels?: NotifyChannel[];
}

export interface NotifyEventDetail extends Required<Omit<NotifyOptions, 'speak' | 'channels'>> {
  id: number;
  message: string;
  speak: string;
  channels: NotifyChannel[];
}

let seq = 0;

const DEFAULT_DURATION: Record<NotifyKind, number> = {
  info: 3000,
  success: 2500,
  error: 4500,
  listening: 6000,
  thinking: 5000,
};

const VIBRATE_PATTERN: Partial<Record<NotifyKind, number[]>> = {
  error: [80, 60, 80],
  success: [40],
  listening: [30],
};

/** A distinct icon AND word per kind — never colour alone (WCAG 1.4.1).
 * Shared by the toast (AccessibleNotification) and the border-pulse/badge
 * (VisualAlert) renderers so the two channels never disagree. */
export const KIND_ICON: Record<NotifyKind, string> = {
  info: 'info',
  success: 'check_circle',
  error: 'error',
  listening: 'mic',
  thinking: 'hourglass_top',
};

export const KIND_WORD: Record<NotifyKind, string> = {
  info: 'Info',
  success: 'Success',
  error: 'Error',
  listening: 'Listening',
  thinking: 'Thinking',
};

const DEFAULT_CHANNELS: NotifyChannel[] = ['toast', 'borderPulse'];

export function notify(message: string, opts: NotifyOptions = {}): void {
  const kind = opts.kind ?? 'info';
  const detail: NotifyEventDetail = {
    id: ++seq,
    message,
    kind,
    speak: opts.speak ?? message,
    vibrate: opts.vibrate ?? kind === 'error',
    durationMs: opts.durationMs ?? DEFAULT_DURATION[kind],
    silent: opts.silent ?? false,
    channels: opts.channels ?? DEFAULT_CHANNELS,
  };

  window.dispatchEvent(new CustomEvent<NotifyEventDetail>('app:notify', { detail }));

  // Captioned regardless of whether TTS ever speaks this one (silent:true,
  // or a screen-reader user who never gets our own speech) — the caption
  // log's job is a persistent record of what HAPPENED, independent of audio.
  addCaption(`${KIND_WORD[kind]}: ${message}`);

  if (detail.vibrate && typeof navigator !== 'undefined' && navigator.vibrate) {
    navigator.vibrate(VIBRATE_PATTERN[kind] ?? [50]);
  }
}
