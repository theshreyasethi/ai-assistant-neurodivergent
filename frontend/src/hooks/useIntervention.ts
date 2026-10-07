import { useRef } from 'react';

import { notify } from '../services/notify';

export interface QuestionSignal {
  answerChanges: number;
  blurCount: number;
  timeMs: number;
  baselineMs: number | null;
}

const ROLLING_WINDOW = 3;
const HIGH_CHANGES = 2;
const HIGH_BLUR = 1;
const HIGH_LATENCY_RATIO = 2.5;

/**
 * Gentle, opt-in break suggestion (roadmap P4-14) — fires AT MOST ONCE per
 * session, from a crude rolling read of the same interaction signals HES
 * uses (answer changes, tab-blur, latency vs personal baseline), never from
 * facial data. This is a SUGGESTION: declining it does nothing, and it
 * never fires again this session regardless of what happens next —
 * "offers a break once, not repeatedly" is the whole point.
 */
export function useIntervention() {
  const recent = useRef<QuestionSignal[]>([]);
  const offered = useRef(false);

  const reportQuestionSignals = (signal: QuestionSignal) => {
    if (offered.current) return;
    recent.current = [...recent.current, signal].slice(-ROLLING_WINDOW);
    if (recent.current.length < ROLLING_WINDOW) return;

    const strained = recent.current.filter((s) => {
      const latencyRatio = s.baselineMs ? s.timeMs / s.baselineMs : 1;
      return s.answerChanges >= HIGH_CHANGES || s.blurCount >= HIGH_BLUR || latencyRatio >= HIGH_LATENCY_RATIO;
    });

    if (strained.length >= ROLLING_WINDOW - 1) {
      offered.current = true;
      notify('Want to take a short break? You can pick up right where you left off.', {
        kind: 'info',
        channels: ['toast'],
        durationMs: 8000,
      });
    }
  };

  return { reportQuestionSignals };
}
