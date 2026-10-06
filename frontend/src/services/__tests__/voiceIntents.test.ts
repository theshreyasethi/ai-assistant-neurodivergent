import { describe, expect, it } from 'vitest';
import { ANSWER, HELP, matchRules, NAVIGATE, PROGRESS, REPEAT, STOP, SUBMIT, UNKNOWN } from '../voiceIntents';

describe('voiceIntents.matchRules', () => {
  it('returns null for empty input', () => {
    expect(matchRules('')).toBeNull();
    expect(matchRules('   ')).toBeNull();
  });

  it('matches STOP even inside a longer phrase, and before any other rule', () => {
    // "stop" also appears inside words that could otherwise confuse a naive
    // matcher — this is the single most safety-critical intent (a student
    // mid-utterance needs it honoured immediately), so it must win.
    expect(matchRules('stop')?.intent).toBe(STOP);
    expect(matchRules('please stop now')?.intent).toBe(STOP);
    expect(matchRules('stop reading everything')?.intent).toBe(STOP);
  });

  it('matches HELP phrasings', () => {
    expect(matchRules('help')?.intent).toBe(HELP);
    expect(matchRules('what can you say')?.intent).toBe(HELP);
    expect(matchRules('what commands are there')?.intent).toBe(HELP);
  });

  it('matches PROGRESS phrasings', () => {
    expect(matchRules('what is my progress')?.intent).toBe(PROGRESS);
    expect(matchRules('how am i doing')?.intent).toBe(PROGRESS);
    expect(matchRules('my score')?.intent).toBe(PROGRESS);
  });

  it('matches REPEAT phrasings', () => {
    expect(matchRules('repeat')?.intent).toBe(REPEAT);
    expect(matchRules('say that again')?.intent).toBe(REPEAT);
  });

  it('matches SUBMIT phrasings', () => {
    expect(matchRules('submit')?.intent).toBe(SUBMIT);
    expect(matchRules("that's my answer")?.intent).toBe(SUBMIT);
  });

  describe('ANSWER — 10+ phrasings, each resolving to the right option index', () => {
    const cases: Array<[string, number]> = [
      ['answer a', 0],
      ['answer A', 0],
      ['choose the second one', 1],
      ['option 3', 2],
      ['select d', 3],
      ['pick option four', 3],
      ['b', 1],
      ['option two', 1],
      ['answer is c', 2],
      ['number one', 0],
      ['pick the first one', 0],
    ];
    it.each(cases)('%s -> optionIndex %i', (text, expected) => {
      const result = matchRules(text);
      expect(result?.intent).toBe(ANSWER);
      expect(result?.slots.optionIndex).toBe(expected);
    });

    it('ANSWER takes priority over NAVIGATE wording overlap ("take option two")', () => {
      const result = matchRules('take option two');
      expect(result?.intent).toBe(ANSWER);
      expect(result?.slots.optionIndex).toBe(1);
    });
  });

  describe('NAVIGATE', () => {
    it('matches "go to X" phrasings and resolves the right path', () => {
      const result = matchRules('go to my quizzes');
      expect(result?.intent).toBe(NAVIGATE);
      expect(result?.slots.target).toBe('quiz');
      expect(result?.slots.path).toBe('/quiz');
    });

    it('matches "take me to the dashboard"', () => {
      const result = matchRules('take me to the dashboard');
      expect(result?.slots.target).toBe('dashboard');
      expect(result?.slots.path).toBe('/student-dashboard');
    });

    it('matches a bare destination with no verb', () => {
      const result = matchRules('dashboard');
      expect(result?.intent).toBe(NAVIGATE);
      expect(result?.slots.target).toBe('dashboard');
      // Lower confidence than a full "go to X" phrase — the rule itself
      // encodes this; just assert it is strictly below the full-phrase case.
      expect(result?.confidence).toBeLessThan(0.95);
    });
  });

  it('returns null (caller falls back to the LLM) for a phrase no rule covers', () => {
    expect(matchRules('could you tell me a fun fact')).toBeNull();
  });

  it('matches the Python backend byte-for-byte on a known quirk: bare "what" means REPEAT', () => {
    // Verified directly against backend/services/intent.py's match_rules():
    // the REPEAT pattern includes bare "what" as an alternative (meant for
    // "what?" as in "I didn't hear you"), which also fires on any phrase
    // merely CONTAINING the word "what" — a real, shared characteristic of
    // the rule set, not a porting bug. Asserting it here is what keeps the
    // two implementations provably in sync rather than silently diverging.
    expect(matchRules('what is the weather like today')?.intent).toBe(REPEAT);
  });

  it('never returns the UNKNOWN intent itself — that only comes from the LLM fallback path', () => {
    // matchRules() returns null on a miss; UNKNOWN is assigned by the
    // caller (VoiceNavigator) only after the LLM fallback also misses.
    const allPossibleOutcomes = ['hello there', 'xyz123', ''].map((t) => matchRules(t));
    expect(allPossibleOutcomes.every((r) => r === null || r.intent !== UNKNOWN)).toBe(true);
  });
});
