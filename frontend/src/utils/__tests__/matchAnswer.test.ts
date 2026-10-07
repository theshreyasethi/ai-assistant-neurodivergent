import { describe, expect, it } from 'vitest';
import { matchAnswer } from '../matchAnswer';

describe('matchAnswer — fair fill-blank matching (roadmap P4-11)', () => {
  it('matches an exact answer regardless of case/punctuation', () => {
    expect(matchAnswer('Paris.', 'paris')).toEqual({ matched: true, matchType: 'exact' });
  });

  it('treats a simple plural/singular difference as exact', () => {
    expect(matchAnswer('cells', 'cell').matched).toBe(true);
    expect(matchAnswer('cells', 'cell').matchType).toBe('exact');
  });

  it('accepts a one-edit spelling slip on a short word as fuzzy', () => {
    const result = matchAnswer('mitochondrea', 'mitochondria');
    expect(result.matched).toBe(true);
    expect(result.matchType).toBe('fuzzy');
  });

  it('accepts a two-edit spelling slip on a long word (photosynthesys)', () => {
    const result = matchAnswer('photosynthesys', 'photosynthesis');
    expect(result.matched).toBe(true);
  });

  it('accepts a phonetic match the edit-distance threshold would miss (mane/main)', () => {
    // 2-edit distance on a 4-letter word is outside the (length<=8 -> 1)
    // fuzzy threshold, so this only matches via the phonetic fallback.
    const result = matchAnswer('mane', 'main');
    expect(result.matched).toBe(true);
    expect(result.matchType).toBe('phonetic');
  });

  it('rejects an unrelated word of similar length', () => {
    const result = matchAnswer('elephant', 'evaporate');
    expect(result.matched).toBe(false);
    expect(result.matchType).toBe('none');
  });

  it('rejects empty input', () => {
    expect(matchAnswer('', 'photosynthesis').matched).toBe(false);
    expect(matchAnswer('photosynthesis', '').matched).toBe(false);
  });
});
