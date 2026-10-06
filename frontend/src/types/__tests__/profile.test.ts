import { describe, expect, it } from 'vitest';
import { canUseWebcam, DEFAULT_PREFS, type Consent, type Profile, webcamAllowed } from '../profile';

function makeProfile(overrides: Partial<Profile> = {}): Profile {
  return {
    disabilities: [],
    primary: null,
    severity: null,
    prefs: { ...DEFAULT_PREFS },
    ...overrides,
  };
}

const CONSENT_GRANTED: Consent = { dataCollection: true, webcam: true, disabilityDisclosure: true, version: 1 };
const CONSENT_DENIED: Consent = { dataCollection: true, webcam: false, disabilityDisclosure: true, version: 1 };

describe('webcamAllowed — disability-based exclusion only', () => {
  it('is false for a blind profile regardless of the webcamAttention preference', () => {
    const profile = makeProfile({ disabilities: ['blind'], prefs: { ...DEFAULT_PREFS, webcamAttention: true } });
    expect(webcamAllowed(profile)).toBe(false);
  });

  it('is false for a low_vision profile regardless of the webcamAttention preference', () => {
    const profile = makeProfile({ disabilities: ['low_vision'], prefs: { ...DEFAULT_PREFS, webcamAttention: true } });
    expect(webcamAllowed(profile)).toBe(false);
  });

  it('is false when webcamAttention is off, even with no disability exclusion', () => {
    const profile = makeProfile({ prefs: { ...DEFAULT_PREFS, webcamAttention: false } });
    expect(webcamAllowed(profile)).toBe(false);
  });

  it('is true when webcamAttention is on and no excluded disability is present', () => {
    const profile = makeProfile({ disabilities: ['adhd'], prefs: { ...DEFAULT_PREFS, webcamAttention: true } });
    expect(webcamAllowed(profile)).toBe(true);
  });
});

describe('canUseWebcam — the actual gate <Eye/> must be mounted behind (roadmap task P2-09)', () => {
  it('is false for a blind student even with webcam consent granted', () => {
    const profile = makeProfile({ disabilities: ['blind'], prefs: { ...DEFAULT_PREFS, webcamAttention: true } });
    expect(canUseWebcam(profile, CONSENT_GRANTED)).toBe(false);
  });

  it('is false when webcamAllowed() is true but consent was never granted', () => {
    const profile = makeProfile({ prefs: { ...DEFAULT_PREFS, webcamAttention: true } });
    expect(canUseWebcam(profile, CONSENT_DENIED)).toBe(false);
  });

  it('is false while consent has not loaded yet (null) — absence must never default to allowed', () => {
    const profile = makeProfile({ prefs: { ...DEFAULT_PREFS, webcamAttention: true } });
    expect(canUseWebcam(profile, null)).toBe(false);
  });

  it('is true only when both webcamAllowed() AND consent.webcam are true', () => {
    const profile = makeProfile({ disabilities: ['adhd'], prefs: { ...DEFAULT_PREFS, webcamAttention: true } });
    expect(canUseWebcam(profile, CONSENT_GRANTED)).toBe(true);
  });

  it('is false for low_vision even with every other condition satisfied', () => {
    const profile = makeProfile({ disabilities: ['low_vision'], prefs: { ...DEFAULT_PREFS, webcamAttention: true } });
    expect(canUseWebcam(profile, CONSENT_GRANTED)).toBe(false);
  });
});
