import { useEffect, useRef } from 'react';
import { earcon } from '../services/earcons';
import { speakOnce } from '../services/speech';

const MILESTONES = [25, 50, 75, 100];

/**
 * Announces reading progress at 25/50/75/100% milestones ("Sentence 12 of
 * 30, 40 percent") and plays a soft earcon on every sentence boundary —
 * deliberately NOT on every single sentence advance for the milestone
 * announcement, which would be actively hostile at reading speed (the
 * research doc's "where am I" problem is not solved by talking more).
 * Each milestone fires once per lesson; resets when the lesson (total)
 * changes, e.g. navigating to a new piece of content.
 */
export function useReadingProgress(
  currentIndex: number,
  total: number,
  opts: { voiceFirst: boolean },
): { announceNow: () => void } {
  const announced = useRef<Set<number>>(new Set());
  const lastIndex = useRef(-1);

  useEffect(() => {
    announced.current = new Set();
    lastIndex.current = -1;
  }, [total]);

  useEffect(() => {
    if (total <= 0 || currentIndex === lastIndex.current) return;
    lastIndex.current = currentIndex;

    if (opts.voiceFirst) earcon.content();

    const pct = Math.round(((currentIndex + 1) / total) * 100);
    const milestone = MILESTONES.find((m) => pct >= m && !announced.current.has(m));
    if (milestone !== undefined) {
      announced.current.add(milestone);
      if (opts.voiceFirst) {
        speakOnce(`Sentence ${currentIndex + 1} of ${total}, ${milestone} percent.`);
      }
    }
  }, [currentIndex, total, opts.voiceFirst]);

  const announceNow = () => {
    if (total <= 0) return;
    const pct = Math.round(((currentIndex + 1) / total) * 100);
    speakOnce(`Sentence ${currentIndex + 1} of ${total}, ${pct} percent.`);
  };

  return { announceNow };
}
