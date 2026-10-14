/**
 * Voice command intent matching — rule-first, LLM fallback (POST
 * /api/voice/intent). Mirrors backend/services/intent.py's rule set
 * exactly: same intent names, same STOP-first ordering, same ROUTES /
 * nav-target / option-word tables — so a command resolves identically
 * whether this client-side pass catches it or the backend's LLM fallback
 * does.
 *
 * This is a deliberate exception to "one implementation, always": a
 * network round trip before "stop" is honoured is worse for a student with
 * no other input method than keeping two rule sets in sync by hand (see
 * docs/PHASE_LEARNINGS.md Learning #18, written for the Python side — the
 * same reasoning applies here). Any change to the rules below must be
 * mirrored in backend/services/intent.py, and vice versa.
 */

export const NAVIGATE = 'NAVIGATE';
export const READ_NEXT = 'READ_NEXT';
export const READ_PREVIOUS = 'READ_PREVIOUS';
export const READ_ALL = 'READ_ALL';
export const REPEAT = 'REPEAT';
export const STOP = 'STOP';
export const DESCRIBE_PAGE = 'DESCRIBE_PAGE';
export const EXPLAIN = 'EXPLAIN';
export const PROGRESS = 'PROGRESS';
export const HELP = 'HELP';
export const FASTER = 'FASTER';
export const SLOWER = 'SLOWER';
export const ANSWER = 'ANSWER';
export const SUBMIT = 'SUBMIT';
export const SKIP_QUESTION = 'SKIP_QUESTION';
export const EXIT_QUIZ = 'EXIT_QUIZ';
export const UNKNOWN = 'UNKNOWN';

export const ROUTES: Record<string, string> = {
  dashboard: '/student-dashboard',
  quiz: '/quiz',
  learning: '/learning',
  upload: '/upload',
  content: '/content',
  teacher: '/teacher-dashboard',
};

// "true"/"false" map onto the same 0/1 slots as a/first and b/second since
// backend/services/quiz_gen.py always renders true_false questions as
// options=["True", "False"] in that order.
const OPTION_WORDS: Record<string, number> = {
  a: 0, first: 0, one: 0, '1': 0, true: 0,
  b: 1, second: 1, two: 1, '2': 1, false: 1,
  c: 2, third: 2, three: 2, '3': 2,
  d: 3, fourth: 3, four: 3, '4': 3,
};

export interface Intent {
  intent: string;
  slots: Record<string, unknown>;
  confidence: number;
  source: 'rules' | 'llm' | 'none';
}

// Order matters, same as the Python side: STOP must come before everything.
const RULES: Array<[string, RegExp]> = [
  [STOP, /\b(stop|quiet|silence|shut up|be quiet|pause|cancel|nevermind|never mind)\b/],
  [HELP, /\b(help|what can (i|you) (say|do)|commands|options available)\b/],
  [PROGRESS, /\b(my )?(progress|score|how (am i|i am) doing|how did i do|results?|marks)\b/],
  [DESCRIBE_PAGE, /\b(what('s| is) (on |in )?(this |the )?(page|screen)|where am i|describe( the)?( page| screen)?|what can i do here)\b/],
  [EXPLAIN, /\b(explain|what does (this|that) mean|i don'?t understand|simpler|say (that )?(again )?(in )?(simpler|easier)|break (it|this) down)\b/],
  [READ_NEXT, /\b(read (the )?next|next (paragraph|sentence|part|section|bit)|continue|carry on|go on|keep reading)\b/],
  [READ_PREVIOUS, /\b(read (the )?(previous|last)|previous (paragraph|sentence|part|section)|go back|back up)\b/],
  [REPEAT, /\b(repeat|say (that|it) again|again|once more|pardon|what)\b/],
  [READ_ALL, /\b(read (it |this |the )?(all|everything|whole|page|aloud)|start reading|read to me)\b/],
  [FASTER, /\b(faster|speed up|quicker|too slow)\b/],
  [SLOWER, /\b(slower|slow down|too fast)\b/],
  [SUBMIT, /\b(submit|confirm|next question|done|that'?s my answer|lock it in)\b/],
  // Blind/voice-first students have no "Skip" or "Exit" button to click —
  // these are the only route to either action (same reasoning as ANSWER).
  [SKIP_QUESTION, /\bskip\b(\s+(this|that|the)\s+question)?|\bpass\b\s+(this|on this)\s+question\b/],
  [EXIT_QUIZ, /\b(exit|quit|leave)\b(\s+(this|the))?\s*quiz\b|\b(exit|quit)\b/],
];

// "go to X" / "open X" / "take me to X"
const NAV_RE = /\b(go|navigate|take me|open|show me|switch)\b.*?\b(dashboard|home|quiz|quizzes|test|lesson|lessons|learning|read|reading|upload|content|material|materials|teacher)\b/;
const NAV_TARGETS: Record<string, string> = {
  dashboard: 'dashboard', home: 'dashboard',
  quiz: 'quiz', quizzes: 'quiz', test: 'quiz',
  lesson: 'learning', lessons: 'learning', learning: 'learning',
  read: 'learning', reading: 'learning',
  upload: 'upload',
  content: 'content', material: 'content', materials: 'content',
  teacher: 'teacher',
};

// "answer B" / "choose the second one" / "select option 3" / "answer true"
const ANSWER_RE = /\b(answer|choose|select|pick|option|number)\b\s*(?:is\s+|the\s+)?(?:option\s+|number\s+)?\b([abcd]|first|second|third|fourth|one|two|three|four|[1-4]|true|false)\b/;
// bare "B", "option two", "true" or "false" with nothing else said
const BARE_OPTION_RE = /^\s*(?:option\s+)?([abcd]|[1-4]|first|second|third|fourth|true|false)\s*$/;

export function normalise(text: string): string {
  return (text || '').toLowerCase().replace(/[^\w\s']/g, ' ').trim();
}

/** Try the rule set. Returns null when nothing matches, so the caller can
 * decide whether the LLM fallback is worth a request. */
export function matchRules(text: string): Intent | null {
  const cleaned = normalise(text);
  if (!cleaned) return null;

  // Answering takes priority over navigation: "take option two" contains
  // "take" but is clearly an answer.
  const answerMatch = cleaned.match(ANSWER_RE) || cleaned.match(BARE_OPTION_RE);
  if (answerMatch) {
    const word = (answerMatch[2] ?? answerMatch[1] ?? '').toLowerCase();
    if (word in OPTION_WORDS) {
      return { intent: ANSWER, slots: { optionIndex: OPTION_WORDS[word] }, confidence: 0.95, source: 'rules' };
    }
  }

  const nav = cleaned.match(NAV_RE);
  if (nav) {
    const target = NAV_TARGETS[nav[2]];
    if (target) {
      return { intent: NAVIGATE, slots: { target, path: ROUTES[target] }, confidence: 0.95, source: 'rules' };
    }
  }

  for (const [name, pattern] of RULES) {
    if (pattern.test(cleaned)) return { intent: name, slots: {}, confidence: 0.9, source: 'rules' };
  }

  // Bare destination with no verb: "quiz", "dashboard"
  if (cleaned in NAV_TARGETS) {
    const target = NAV_TARGETS[cleaned];
    return { intent: NAVIGATE, slots: { target, path: ROUTES[target] }, confidence: 0.8, source: 'rules' };
  }

  return null;
}

export const HELP_TEXT =
  'You can say: go to my quizzes, go to my lessons, or go to my dashboard. ' +
  'While reading, say read next, read previous, repeat, or read everything. ' +
  "Say explain this if something is unclear, or what is on this page to hear a description. " +
  'In a quiz, say answer A, answer B, answer C or answer D, or true or false, then say submit. ' +
  'Say skip this question to move on without answering, or exit quiz to leave the quiz. ' +
  'Say faster or slower to change the reading speed. ' +
  'Say stop at any time to make me quiet.';
