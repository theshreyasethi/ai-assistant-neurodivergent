import { useEffect, useRef } from 'react';

export interface QuestionTelemetrySnapshot {
  timeMs: number;
  timeToFirstInteractionMs: number | null;
  answerChanges: number;
  reRead: boolean;
  revisits: number;
}

/**
 * Measures the interaction signals QuizPage used to hard-code
 * (timeToFirstInteractionMs: null, answerChanges: 0, reRead: false — roadmap
 * P3-01 / patent-readiness finding S03). One instance per question: callers
 * re-key it on `questionId` so a new question resets every counter.
 */
export function useQuestionTelemetry(questionId: string) {
  const t0 = useRef(performance.now());
  const first = useRef<number | null>(null);
  const changes = useRef(0);
  const replays = useRef(0);
  const revisits = useRef(0);
  const last = useRef<string | null>(null);

  useEffect(() => {
    t0.current = performance.now();
    first.current = null;
    changes.current = 0;
    replays.current = 0;
    revisits.current = 0;
    last.current = null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questionId]);

  return {
    /** First pointer/key/voice event after the question rendered. */
    onInteract: () => {
      if (first.current === null) first.current = performance.now() - t0.current;
    },
    /** A selection that differs from the previous one — a real answer change,
     * not every keystroke in a free-text box. */
    onSelect: (value: string) => {
      if (last.current !== null && last.current !== value) changes.current += 1;
      last.current = value;
    },
    /** TTS replay or the voice "repeat" command. */
    onReplayQuestion: () => {
      replays.current += 1;
    },
    /** Focus returned to the question stem after the student had already
     * touched an option — re-checking the question itself, not just the
     * answer choices. */
    onStemRefocus: () => {
      revisits.current += 1;
    },
    snapshot: (): QuestionTelemetrySnapshot => ({
      timeMs: Math.round(performance.now() - t0.current),
      timeToFirstInteractionMs: first.current === null ? null : Math.round(first.current),
      answerChanges: changes.current,
      reRead: replays.current > 0,
      revisits: revisits.current,
    }),
  };
}
