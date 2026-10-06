import { useEffect, useRef } from 'react';
import type { Intent } from '../services/voiceIntents';

/** Same window-CustomEvent pattern services/notify.ts already uses for
 * app:notify — a page-agnostic bus so VoiceNavigator (mounted once,
 * globally) can reach whichever page is currently subscribed without prop
 * drilling its command state through every route. */
export const VOICE_INTENT_EVENT = 'app:voice-intent';

export function dispatchVoiceIntent(intent: Intent): void {
  window.dispatchEvent(new CustomEvent<Intent>(VOICE_INTENT_EVENT, { detail: intent }));
}

/**
 * Subscribe a page to one or more voice intents (READ_NEXT, ANSWER,
 * SUBMIT, EXPLAIN, FASTER, SLOWER, PROGRESS, …) without needing to know
 * anything about VoiceNavigator itself. Intents VoiceNavigator fully
 * handles on its own (STOP, NAVIGATE, HELP, DESCRIBE_PAGE) are never
 * dispatched here — only intents a specific page's content can act on.
 */
export function useVoiceCommand(intentNames: string | string[], handler: (intent: Intent) => void): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  const key = Array.isArray(intentNames) ? intentNames.join('|') : intentNames;

  useEffect(() => {
    const names = key.split('|');
    const onIntent = (e: Event) => {
      const detail = (e as CustomEvent<Intent>).detail;
      if (names.includes(detail.intent)) handlerRef.current(detail);
    };
    window.addEventListener(VOICE_INTENT_EVENT, onIntent);
    return () => window.removeEventListener(VOICE_INTENT_EVENT, onIntent);
  }, [key]);
}
