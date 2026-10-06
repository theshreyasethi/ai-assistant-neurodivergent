import { describe, expect, it } from 'vitest';
import { splitIntoSentences } from '../speech';

describe('speech.splitIntoSentences — the input to the sentence-based TTS queue', () => {
  it('returns an empty array for empty/whitespace-only input', () => {
    expect(splitIntoSentences('')).toEqual([]);
    expect(splitIntoSentences('   ')).toEqual([]);
  });

  it('splits on sentence-ending punctuation followed by whitespace', () => {
    expect(splitIntoSentences('The cat sat. The dog ran. Birds flew.')).toEqual([
      'The cat sat.',
      'The dog ran.',
      'Birds flew.',
    ]);
  });

  it('handles ! and ? as sentence boundaries too', () => {
    expect(splitIntoSentences('Watch out! Are you okay? I am fine.')).toEqual([
      'Watch out!',
      'Are you okay?',
      'I am fine.',
    ]);
  });

  it('treats a single sentence with no terminal punctuation as one queue entry', () => {
    expect(splitIntoSentences('This has no terminal punctuation')).toEqual([
      'This has no terminal punctuation',
    ]);
  });

  it('does not produce empty entries from stray whitespace between sentences', () => {
    const result = splitIntoSentences('First.    Second.\n\nThird.');
    expect(result).toEqual(['First.', 'Second.', 'Third.']);
    expect(result.every((s) => s.length > 0)).toBe(true);
  });

  it('never produces one entry per word at normal prose density (the regression this exists to prevent)', () => {
    // The original bug: LearningPage queued one SpeechSynthesisUtterance
    // PER WORD at reading speed, flooding Chrome's queue. The fix queues
    // one utterance per SENTENCE — a 50-word, 5-sentence passage must
    // produce 5 queue entries, not 50.
    const passage = Array.from({ length: 5 }, (_, i) =>
      `This is sentence number ${i + 1} and it has exactly ten words total here.`,
    ).join(' ');
    const sentences = splitIntoSentences(passage);
    expect(sentences).toHaveLength(5);
  });
});
