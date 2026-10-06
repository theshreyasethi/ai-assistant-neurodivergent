/**
 * Single source of truth for "what is this page called and what can a
 * voice-first or screen-reader user do here" — used by RouteAnnouncer.tsx
 * (title + short announcement on every navigation), VoiceBootstrap.tsx
 * (the welcome script), and the DESCRIBE_PAGE voice intent ("what's on
 * this page"). Hard-coded per route is fine at this page count (roadmap
 * task P2-05 note: would need generating if the app grows much further).
 */

export interface PageInfo {
  path: string;
  title: string;
  /** Spoken/announced on arrival — kept short on purpose; a long
   * announcement fired on every navigation is actively hostile. */
  shortSummary: string;
  /** Spoken on an explicit "what's on this page" / DESCRIBE_PAGE request. */
  longSummary: string;
}

export const PAGE_REGISTRY: PageInfo[] = [
  {
    path: '/login',
    title: 'Sign in',
    shortSummary: 'Sign in page.',
    longSummary: 'You are on the sign in page. Enter your username and password, then press sign in. Say or press H for help at any time.',
  },
  {
    path: '/first-login',
    title: 'Choose a new password',
    shortSummary: 'Choose a new password.',
    longSummary: 'You must choose a new password before continuing. Enter your new password, then type it again to confirm.',
  },
  {
    path: '/account',
    title: 'Your account',
    shortSummary: 'Your account.',
    longSummary: 'Account page. Here you can change your display name, your username, and your password.',
  },
  {
    path: '/settings',
    title: 'Accessibility settings',
    shortSummary: 'Accessibility settings.',
    longSummary: 'Settings page. Change how the app looks, sounds, and responds to you — text size, contrast, voice options, and your support profile.',
  },
  {
    path: '/student-dashboard',
    title: 'Dashboard',
    shortSummary: 'Your dashboard.',
    longSummary: 'Your dashboard. Say upload a PDF, manage content, or start learning to go to those pages, or say go to my quizzes.',
  },
  {
    path: '/upload',
    title: 'Upload a lesson',
    shortSummary: 'Upload a PDF.',
    longSummary: 'Upload page. Choose a PDF file to upload — up to five megabytes and twenty pages — and it will be simplified for you.',
  },
  {
    path: '/learning',
    title: 'Reading your lesson',
    shortSummary: 'Reading page.',
    longSummary: 'Learning page. Say read next, read previous, or read everything to hear your lesson read aloud. Say explain this if something is unclear, or take the quiz when you are ready.',
  },
  {
    path: '/content',
    title: 'Your content',
    shortSummary: 'Your content.',
    longSummary: 'Content page. View and manage the lessons you have uploaded.',
  },
  {
    path: '/quiz',
    title: 'Quiz',
    shortSummary: 'Quiz.',
    longSummary: 'Quiz page. For each question, say answer A, B, C or D, then say submit to confirm. Say repeat to hear the question again.',
  },
  {
    path: '/teacher-dashboard',
    title: 'Teacher dashboard',
    shortSummary: 'Teacher dashboard.',
    longSummary: 'Teacher dashboard. View your student roster, their quiz scores, and their learning analytics.',
  },
  {
    path: '/admin-dashboard',
    title: 'Admin dashboard',
    shortSummary: 'Admin dashboard.',
    longSummary: 'Admin dashboard. Create teacher and student accounts, and manage existing ones.',
  },
];

const BY_PATH = new Map(PAGE_REGISTRY.map((p) => [p.path, p]));

const FALLBACK: PageInfo = {
  path: '',
  title: 'EduEase',
  shortSummary: 'Page.',
  longSummary: 'This page does not have a description yet.',
};

export function getPageInfo(path: string): PageInfo {
  return BY_PATH.get(path) ?? { ...FALLBACK, path };
}
