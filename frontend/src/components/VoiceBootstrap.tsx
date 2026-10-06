import React from 'react';
import { useLocation } from 'react-router-dom';

import { earcon } from '../services/earcons';
import { speakSentences, unlockAudio } from '../services/speech';
import { getPageInfo } from '../config/pageRegistry';
import { useProfile } from '../hooks/useProfile';

const STORAGE_KEY = 'eduease.voiceFirst';

function readDevicePref(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false; // private window / storage blocked — fall back cleanly, never throw
  }
}
function writeDevicePref(v: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, v ? '1' : '0');
  } catch {
    /* device memory just won't persist this session — not fatal */
  }
}

/**
 * Mounted once, globally, in App.tsx (inside the Router, so useLocation()
 * resolves) — this single mount covers every page, /login included, which
 * is what "mount in App.tsx and LoginPage.tsx" means in practice: a
 * route-aware component mounted once at the top already reaches every
 * route, a second mount inside LoginPage would just duplicate the same
 * listeners.
 *
 * Browsers block speechSynthesis and AudioContext until a real user
 * gesture — "speaks on load" cannot be literal in any browser. The
 * pattern here is the closest compliant approximation:
 *   1. An aria-live announcement fires IMMEDIATELY, no gesture needed — a
 *      screen-reader user hears it right away regardless of audio-unlock
 *      rules, since that's text, not synthesized audio.
 *   2. The first keydown or pointerdown ANYWHERE unlocks audio and speaks
 *      the welcome script for whichever page that gesture happened on.
 *   3. The choice is remembered per device (localStorage) and, once
 *      signed in, on the profile too — so a returning voice-first user
 *      gets the welcome on their very first keypress next session,
 *      without needing to press V again.
 */
const VoiceBootstrap: React.FC = () => {
  const location = useLocation();
  const pathnameRef = React.useRef(location.pathname);
  pathnameRef.current = location.pathname;

  const { profile, savePrefs, loading } = useProfile();
  const [armed, setArmed] = React.useState(readDevicePref);
  const [announce, setAnnounce] = React.useState('');
  const firedRef = React.useRef(false);

  const start = React.useCallback(() => {
    if (firedRef.current) return;
    firedRef.current = true;

    unlockAudio();
    earcon.heading();
    const info = getPageInfo(pathnameRef.current);
    speakSentences([info.longSummary], { rate: profile.prefs.ttsRate || 1 });

    writeDevicePref(true);
    if (!loading && !profile.prefs.voiceFirst) void savePrefs({ voiceFirst: true });
    setArmed(false);
  }, [loading, profile.prefs.ttsRate, profile.prefs.voiceFirst, savePrefs]);

  React.useEffect(() => {
    setAnnounce(
      armed
        ? 'EduEase voice mode is on. Press any key to hear this page.'
        : 'Press V for voice-first mode.',
    );
    if (!armed) return;
    // Any key (including Tab) or pointer counts as user activation.
    window.addEventListener('keydown', start, { once: true });
    window.addEventListener('pointerdown', start, { once: true });
    return () => {
      window.removeEventListener('keydown', start);
      window.removeEventListener('pointerdown', start);
    };
  }, [armed, start]);

  // Opt-in trigger for a user who has NOT already armed voice-first on this
  // device: pressing V (outside a text field) arms it, same welcome flow.
  React.useEffect(() => {
    if (armed) return;
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const inField = /input|textarea|select/i.test(target?.tagName ?? '');
      if (!inField && e.key.toLowerCase() === 'v') {
        writeDevicePref(true);
        setArmed(true);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [armed]);

  return (
    <>
      {/* Reaches a screen-reader user instantly — no gesture needed, since
          this is text in a live region, not synthesized audio. */}
      <div role="status" aria-live="polite" className="sr-only">
        {announce}
      </div>
      {armed && (
        <button
          type="button"
          autoFocus
          onClick={start}
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[300] focus:bg-primary focus:text-on-primary focus:px-4 focus:py-2 focus:rounded-lg"
        >
          Voice mode is on. Press any key to hear this page.
        </button>
      )}
    </>
  );
};

export default VoiceBootstrap;
