// Shapes frozen in DATA_CONTRACT.md v1 (master). Do not change field names unilaterally.

export type Disability =
  | 'dyslexia'
  | 'adhd'
  | 'autism'
  | 'blind'
  | 'low_vision'
  | 'deaf'
  | 'hard_of_hearing'
  | 'dyscalculia'
  | 'dysgraphia'
  | 'anxiety'
  | 'intellectual'
  | 'motor';

export const DISABILITY_LABELS: Record<Disability, string> = {
  dyslexia: 'Dyslexia (reading)',
  adhd: 'ADHD (attention)',
  autism: 'Autism',
  blind: 'Blind',
  low_vision: 'Low vision',
  deaf: 'Deaf',
  hard_of_hearing: 'Hard of hearing',
  dyscalculia: 'Dyscalculia (maths)',
  dysgraphia: 'Dysgraphia (writing)',
  anxiety: 'Anxiety',
  intellectual: 'Intellectual disability',
  motor: 'Motor / mobility',
};

export type Severity = 'mild' | 'moderate' | 'significant';

export interface Prefs {
  fontScale: number;
  highContrast: boolean;
  dyslexiaFont: boolean;
  reduceMotion: boolean;
  ttsEnabled: boolean;
  ttsRate: number;
  voiceNav: boolean;
  captionsAlways: boolean;
  webcamAttention: boolean;
  describeImages: boolean;
  /** Opt-in, device-remembered (localStorage "eduease.voiceFirst") as well
   * as stored here once signed in — VoiceBootstrap.tsx sets both. Drives
   * the spoken welcome on entry and auto-starting TTS on the reading page. */
  voiceFirst: boolean;
  /** "app": our own speechSynthesis announces things (RouteAnnouncer,
   * VoiceNavigator read-backs, earcons). "screenReader": the student runs
   * their own AT (NVDA/JAWS/VoiceOver) — the app must never also speak,
   * only expose aria-live text, or the two voices talk over each other. */
  voiceEngine: 'app' | 'screenReader';
  /** BCP-47 tag (e.g. "en-US", "hi-IN") used for both speechSynthesis and
   * SpeechRecognition — kept separate from the UI's i18n language since a
   * student may read the UI in one language and want speech in another. */
  speechLang: string;
  /** Anxiety support (roadmap P4-12): neutral palette (no red for errors),
   * larger spacing, zero motion, no running score/countdown visible during
   * a quiz — applied via the `data-calm` attribute on <html>. */
  calmMode: boolean;
  /** No clocks, no timedOut telemetry — PROCESSING_DELAY derives from ratio
   * only. Independent of calmMode: a student can want one without the other. */
  untimed: boolean;
}

export interface Profile {
  disabilities: Disability[];
  primary: Disability | null;
  severity: Severity | null;
  prefs: Prefs;
}

export interface Consent {
  dataCollection: boolean;
  webcam: boolean;
  disabilityDisclosure: boolean;
  version: number;
}

export const CONSENT_VERSION = 1;

export const DEFAULT_PREFS: Prefs = {
  fontScale: 1,
  highContrast: false,
  dyslexiaFont: false,
  reduceMotion: false,
  ttsEnabled: false,
  ttsRate: 1,
  voiceNav: false,
  captionsAlways: false,
  webcamAttention: false,
  describeImages: false,
  voiceFirst: false,
  voiceEngine: 'app',
  speechLang: 'en-US',
  calmMode: false,
  untimed: false,
};

export const DEFAULT_PROFILE: Profile = {
  disabilities: [],
  primary: null,
  severity: null,
  prefs: DEFAULT_PREFS,
};

/** Which DASE/simplify/quiz disability profile to score & write content against. */
export function scoringProfile(profile: Profile): string {
  return profile.primary ?? profile.disabilities[0] ?? 'default';
}

/** Webcam must be off for blind/low-vision users regardless of what's stored —
 * the camera is simply useless to them. Also off for autism: a face-presence
 * signal is a poor proxy for attention here (atypical eye contact is a
 * feature of autism, not a sign of disengagement), so the same exclusion
 * applies even though the camera itself would work fine. Mirrored on the
 * backend by autism never declaring ATT_SPAN or scorable PACE_STAB in
 * dase_profiles.json, so no stray data could feed this profile's score
 * even if this check were somehow bypassed. */
export function webcamAllowed(profile: Profile): boolean {
  if (profile.disabilities.some((d) => d === 'blind' || d === 'low_vision' || d === 'autism')) return false;
  return profile.prefs.webcamAttention;
}

/** The actual gate <Eye/> must be mounted behind (roadmap task P2-09):
 * webcamAllowed() alone is not enough — a profile with webcamAttention=true
 * but no recorded webcam consent must still never start the camera.
 * `consent` is null while it hasn't loaded yet, which this treats as "not
 * granted", never as "allowed by default". */
export function canUseWebcam(profile: Profile, consent: Consent | null): boolean {
  return webcamAllowed(profile) && !!consent?.webcam;
}

/** Applies visual prefs to the document root. Cheap, idempotent, no dependency. */
export function applyPrefs(prefs: Prefs): void {
  const root = document.documentElement;
  root.style.setProperty('--font-scale', String(prefs.fontScale));
  root.classList.toggle('high-contrast', prefs.highContrast);
  root.classList.toggle('dyslexia-font', prefs.dyslexiaFont);
  root.classList.toggle('reduce-motion', prefs.reduceMotion);
  if (prefs.calmMode) root.setAttribute('data-calm', 'true');
  else root.removeAttribute('data-calm');
}
