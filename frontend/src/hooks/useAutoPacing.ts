import { useEffect, useState } from 'react';

import api from '../services/api';

// Matches backend/services/pacing.py's DEFAULT_WPM — the reference point a
// ttsRate of 1.0 is assumed to mean.
const BASELINE_WPM = 170;
const SUGGEST_THRESHOLD_RATIO = 0.85; // only suggest when meaningfully slower than the current rate

/**
 * Reads this student's personal suggested reading pace (roadmap P4-13,
 * backend/services/pacing.py's EMA over past sessions) and tells the caller
 * whether it's worth OFFERING a rate change — never applies it
 * automatically. The caller (LearningPage.tsx) renders its own "Shall I
 * read slower?" prompt and only calls savePrefs({ttsRate}) if the student
 * says yes; nothing here ever changes a preference on its own.
 */
export function useAutoPacing(currentTtsRate: number) {
  const [suggestedWpm, setSuggestedWpm] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get('/api/pacing')
      .then(({ data }) => {
        if (!cancelled) setSuggestedWpm(data.wpm ?? null);
      })
      .catch(() => {
        /* best-effort — no suggestion this session is a safe no-op */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const suggestedRate = suggestedWpm !== null ? suggestedWpm / BASELINE_WPM : null;
  const shouldSuggestSlower = suggestedRate !== null && suggestedRate < currentTtsRate * SUGGEST_THRESHOLD_RATIO;

  return { suggestedWpm, suggestedRate, shouldSuggestSlower };
}
