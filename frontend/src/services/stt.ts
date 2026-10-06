/**
 * Thin wrapper around the Web Speech API's SpeechRecognition — Chrome/Edge
 * only (no vendor-neutral spec exists yet; see docs/PHASE_LEARNINGS.md
 * Phase 3 §3.8). Every caller MUST handle the rejection path — this never
 * silently resolves with an empty transcript on an unsupported browser,
 * because a blind student on Firefox/Safari needs to be told voice input
 * isn't available here, not left wondering why nothing happened.
 *
 * Audio is sent to a cloud speech-recognition service by the browser
 * itself (Google's, for Chrome) — a privacy fact surfaced in the consent
 * screen (AuthForm.tsx), not repeated per call here.
 */

function getSpeechRecognitionCtor(): (new () => any) | null {
  if (typeof window === 'undefined') return null;
  return (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition || null;
}

export function isSttSupported(): boolean {
  return getSpeechRecognitionCtor() !== null;
}

export interface SttResult {
  transcript: string;
  confidence: number;
}

/** One utterance, one result. Rejects with an Error whose message is the
 * recognition error code ("no-speech", "audio-capture", "not-allowed", …),
 * or "unsupported" / "nomatch". Never used in "hands-free always listening"
 * mode by default — see VoiceNavigator.tsx: an always-open microphone is a
 * privacy and battery cost this app does not impose without the student
 * opting in. */
export function listenOnce(lang?: string): Promise<SttResult> {
  const Ctor = getSpeechRecognitionCtor();
  if (!Ctor) return Promise.reject(new Error('unsupported'));

  return new Promise((resolve, reject) => {
    const recognition: any = new Ctor();
    recognition.lang = lang ?? (typeof document !== 'undefined' ? document.documentElement.lang : '') || 'en-US';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (e: any) => {
      const result = e?.results?.[0]?.[0];
      resolve({ transcript: result?.transcript ?? '', confidence: result?.confidence ?? 0 });
    };
    recognition.onerror = (e: any) => reject(new Error(e?.error || 'recognition-error'));
    recognition.onnomatch = () => reject(new Error('nomatch'));

    try {
      recognition.start();
    } catch (err) {
      reject(err instanceof Error ? err : new Error('recognition-start-failed'));
    }
  });
}
