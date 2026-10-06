import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import api from '../services/api';
import { earcon } from '../services/earcons';
import { speakOnce, stopSpeaking } from '../services/speech';
import { isSttSupported, listenOnce } from '../services/stt';
import { getCurrentSession, track } from '../services/telemetry';
import { getPageInfo } from '../config/pageRegistry';
import { useProfile } from '../hooks/useProfile';
import { dispatchVoiceIntent } from '../hooks/useVoiceCommand';
import { ANSWER, DESCRIBE_PAGE, HELP, HELP_TEXT, matchRules, NAVIGATE, STOP, type Intent } from '../services/voiceIntents';

const OPTION_LETTERS = ['A', 'B', 'C', 'D'];

/**
 * The global voice layer (roadmap task P2-04) — mounted once in App.tsx.
 * Push-to-talk (Ctrl+Shift+V): rules first (services/voiceIntents.ts),
 * the LLM fallback (POST /api/voice/intent) only on a miss. A small
 * number of intents are truly global and handled right here (STOP,
 * NAVIGATE, HELP, DESCRIBE_PAGE); everything else (READ_NEXT, REPEAT,
 * ANSWER, SUBMIT, EXPLAIN, FASTER, SLOWER, PROGRESS) is dispatched onto
 * the bus for whichever page is currently listening via useVoiceCommand.
 *
 * Hands-free is deliberately NOT the default — an always-open microphone
 * is a privacy and battery cost this app does not impose without the
 * student opting in; push-to-talk is always available regardless.
 */
const VoiceNavigator: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { uid, profile } = useProfile();
  const [listening, setListening] = React.useState(false);

  const pathnameRef = React.useRef(location.pathname);
  pathnameRef.current = location.pathname;
  const repeatCounts = React.useRef<Record<string, number>>({});

  const dispatch = React.useCallback(
    (intent: Intent): string | null => {
      switch (intent.intent) {
        case STOP:
          stopSpeaking();
          return null;
        case NAVIGATE: {
          const path = (intent.slots.path as string) || '/student-dashboard';
          navigate(path);
          return path;
        }
        case HELP:
          speakOnce(HELP_TEXT);
          return null;
        case DESCRIBE_PAGE:
          speakOnce(getPageInfo(pathnameRef.current).longSummary);
          return null;
        case ANSWER: {
          const idx = intent.slots.optionIndex as number;
          const letter = OPTION_LETTERS[idx] ?? '?';
          dispatchVoiceIntent(intent);
          // "Confirm what you heard before acting on it" — the only way a
          // blind student knows speech recognition heard the option they
          // meant (docs/PHASE_LEARNINGS.md Phase 3 Learning #20).
          speakOnce(`Selected ${letter}. Say submit to confirm.`);
          return null;
        }
        default:
          dispatchVoiceIntent(intent);
          return null;
      }
    },
    [navigate],
  );

  const handleUtterance = React.useCallback(
    async (transcript: string, sttConfidence: number) => {
      const t0 = performance.now();
      let intent = matchRules(transcript);
      let source: Intent['source'] = intent ? 'rules' : 'none';

      if (!intent) {
        try {
          const { data } = await api.post('/api/voice/intent', {
            text: transcript,
            allowLlm: true,
            context: pathnameRef.current,
          });
          intent = { intent: data.intent, slots: data.slots || {}, confidence: data.confidence ?? 0, source: data.source };
          source = data.source;
        } catch {
          intent = { intent: 'UNKNOWN', slots: {}, confidence: 0, source: 'none' };
        }
      }

      const understood = intent.intent !== 'UNKNOWN';
      let route: string | null = null;

      if (!understood) {
        earcon.notUnderstood();
        speakOnce('Sorry, I did not catch that. Say help to hear what I can do.');
      } else {
        route = dispatch(intent);
      }

      const actionMs = Math.round(performance.now() - t0);
      const sessionId = getCurrentSession();
      if (sessionId && uid) {
        const key = transcript.trim().toLowerCase();
        const priorRepeats = repeatCounts.current[key] ?? 0;
        repeatCounts.current[key] = priorRepeats + 1;
        track({
          type: 'voice',
          sessionId,
          studentId: uid,
          ts: Date.now(),
          transcript,
          sttConfidence,
          intent: intent.intent,
          intentSource: source,
          intentConfidence: intent.confidence,
          understood,
          repeats: priorRepeats,
          actionMs,
          route,
        });
      }
    },
    [dispatch, uid],
  );

  const startListening = React.useCallback(() => {
    if (!isSttSupported()) {
      speakOnce('Voice input is not supported in this browser. Please use the keyboard instead.');
      return;
    }
    if (listening) return;
    setListening(true);
    earcon.micOpen();
    listenOnce(profile.prefs.speechLang)
      .then(({ transcript, confidence }) => void handleUtterance(transcript, confidence))
      .catch(() => earcon.notUnderstood())
      .finally(() => setListening(false));
  }, [handleUtterance, listening, profile.prefs.speechLang]);

  // Push-to-talk (Ctrl+Shift+V), always available. Escape silences
  // immediately regardless of whether anything is actively listening.
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'v') {
        e.preventDefault();
        startListening();
      } else if (e.key === 'Escape') {
        stopSpeaking();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [startListening]);

  return (
    <div className="fixed bottom-24 left-4 z-[150]">
      <button
        type="button"
        onClick={startListening}
        aria-label={listening ? 'Listening for your command' : 'Activate voice command (Control, Shift, V)'}
        aria-pressed={listening}
        className={`w-12 h-12 rounded-full shadow-lg flex items-center justify-center transition-all ${
          listening
            ? 'bg-error text-on-error motion-safe:animate-pulse'
            : 'bg-primary text-on-primary hover:scale-105 active:scale-95'
        }`}
      >
        <span className="material-symbols-outlined" aria-hidden="true">
          {listening ? 'mic' : 'mic_none'}
        </span>
      </button>
    </div>
  );
};

export default VoiceNavigator;
