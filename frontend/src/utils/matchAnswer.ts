/**
 * Fair answer matching for free-text fill-blank answers (roadmap P4-11).
 *
 * A dyslexia/dysgraphia student who KNOWS "photosynthesis" but types
 * "photosynthesys" or "fotosynthesis" must not be marked wrong for a
 * spelling slip — that inflates a knowledge gap that isn't there. Exact
 * match always wins first; fuzzy (edit distance) and phonetic equivalence
 * are the fallback, recognition-first path for profiles where spelling
 * itself is the barrier being worked around.
 */

export type MatchType = 'exact' | 'fuzzy' | 'phonetic' | 'none';

export interface MatchResult {
  matched: boolean;
  matchType: MatchType;
}

function normalise(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .replace(/[.,!?;:'"]/g, '')
    .replace(/\s+/g, ' ');
}

function stripTrailingS(s: string): string {
  return s.endsWith('s') && s.length > 3 ? s.slice(0, -1) : s;
}

/** Classic Levenshtein edit distance — iterative, O(n*m), fine for the
 * short single-word/short-phrase answers this is used on. */
function editDistance(a: string, b: string): number {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;

  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const curr = [i];
    for (let j = 1; j <= n; j++) {
      curr[j] = a[i - 1] === b[j - 1]
        ? prev[j - 1]
        : 1 + Math.min(prev[j - 1], prev[j], curr[j - 1]);
    }
    prev = curr;
  }
  return prev[n];
}

/** Soundex-style phonetic code — good enough to catch "fotosynthesis" vs
 * "photosynthesis" (ph/f, same consonant skeleton) without pulling in a
 * full phonetic-matching library for one feature. */
function phoneticCode(s: string): string {
  const cleaned = s.toLowerCase().replace(/[^a-z]/g, '');
  if (!cleaned) return '';
  const first = cleaned[0];
  const mapped = cleaned
    .slice(1)
    .replace(/[bfpv]/g, '1')
    .replace(/[cgjkqsxz]/g, '2')
    .replace(/[dt]/g, '3')
    .replace(/l/g, '4')
    .replace(/[mn]/g, '5')
    .replace(/r/g, '6')
    .replace(/[aeiouhwy]/g, '');
  // Collapse adjacent duplicate codes (standard Soundex step) so
  // "ff"/"pf" etc. don't count as two distinct sounds.
  const collapsed = mapped.replace(/(.)\1+/g, '$1');
  return (first + collapsed).padEnd(4, '0').slice(0, 4);
}

/**
 * ≤1 edit for answers up to 8 letters, ≤2 for longer ones — generous enough
 * to forgive a genuine spelling slip, tight enough that an unrelated word
 * of similar length won't accidentally match.
 */
function maxEditsFor(length: number): number {
  return length > 8 ? 2 : 1;
}

export function matchAnswer(given: string, expected: string): MatchResult {
  const a = normalise(given);
  const b = normalise(expected);
  if (!a || !b) return { matched: false, matchType: 'none' };

  if (a === b) return { matched: true, matchType: 'exact' };

  // Plural/singular is still exact in spirit, not a fuzzy match.
  if (stripTrailingS(a) === stripTrailingS(b)) return { matched: true, matchType: 'exact' };

  const distance = editDistance(a, b);
  if (distance <= maxEditsFor(Math.max(a.length, b.length))) {
    return { matched: true, matchType: 'fuzzy' };
  }

  if (phoneticCode(a) === phoneticCode(b)) {
    return { matched: true, matchType: 'phonetic' };
  }

  return { matched: false, matchType: 'none' };
}
