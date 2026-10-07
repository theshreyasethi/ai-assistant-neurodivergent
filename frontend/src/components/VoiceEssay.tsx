import React, { useRef, useState } from 'react';

import api from '../services/api';
import { isSttSupported, listenOnce } from '../services/stt';
import { earcon } from '../services/earcons';

interface StructuredResult {
  outline: string[];
  paragraphs: string[];
  warnings: string[];
  degraded: boolean;
}

interface Props {
  prompt: string;
  expectedConcepts?: string[];
  onScored?: (result: { know: number | null; expr: number | null }) => void;
}

/**
 * Voice-to-structured-essay (roadmap P4-09) for dysgraphia: continuous
 * dictation is simulated as repeated one-shot listenOnce() calls (this
 * codebase's SpeechRecognition wrapper is one-shot by design — see
 * services/stt.ts), each appended to an editable transcript, so the
 * mechanical act of writing is never the barrier between what the student
 * knows and what gets captured.
 */
const VoiceEssay: React.FC<Props> = ({ prompt, expectedConcepts = [], onScored }) => {
  const [transcript, setTranscript] = useState('');
  const [listening, setListening] = useState(false);
  const [structured, setStructured] = useState<StructuredResult | null>(null);
  const [structuring, setStructuring] = useState(false);
  const [scoring, setScoring] = useState(false);
  const [scoreResult, setScoreResult] = useState<{ know: number | null; expr: number | null } | null>(null);
  const stopRequested = useRef(false);

  const dictate = async () => {
    if (!isSttSupported()) return;
    stopRequested.current = false;
    setListening(true);
    earcon.micOpen();
    while (!stopRequested.current) {
      try {
        const result = await listenOnce();
        if (result.transcript.trim()) {
          setTranscript((prev) => (prev ? `${prev} ${result.transcript.trim()}` : result.transcript.trim()));
        }
      } catch {
        // A single failed utterance (e.g. "no-speech" after a pause) ends
        // the dictation loop rather than retrying forever — the student can
        // always press the button again.
        break;
      }
    }
    setListening(false);
  };

  const stopDictating = () => {
    stopRequested.current = true;
  };

  const structure = async () => {
    setStructuring(true);
    try {
      const { data } = await api.post('/api/writing/structure', { transcript });
      setStructured(data);
    } catch {
      setStructured({ outline: [], paragraphs: [transcript], warnings: ['Could not structure right now.'], degraded: true });
    } finally {
      setStructuring(false);
    }
  };

  const score = async () => {
    const answer = structured?.paragraphs.join(' ') || transcript;
    if (!answer.trim()) return;
    setScoring(true);
    try {
      const { data } = await api.post('/api/writing/score', { answer, expectedConcepts });
      setScoreResult({ know: data.know, expr: data.expr });
      onScored?.({ know: data.know, expr: data.expr });
    } catch {
      setScoreResult(null);
    } finally {
      setScoring(false);
    }
  };

  return (
    <div className="glass-card rounded-3xl p-6 space-y-4">
      <div>
        <h3 className="font-heading text-lg font-semibold text-on-surface">{prompt}</h3>
        <p className="text-sm text-on-surface-variant font-body mt-1">
          Say your answer out loud, or type it — whichever is easier.
        </p>
      </div>

      <div className="flex gap-2">
        {isSttSupported() && (
          <button
            type="button"
            onClick={listening ? stopDictating : dictate}
            className={`px-4 py-2 rounded-xl font-heading text-xs font-semibold ${
              listening ? 'bg-error text-on-error' : 'bg-primary text-white'
            }`}
          >
            {listening ? 'Stop dictating' : 'Start dictating'}
          </button>
        )}
      </div>

      <label htmlFor="voice-essay-transcript" className="sr-only">Your answer</label>
      <textarea
        id="voice-essay-transcript"
        value={transcript}
        onChange={(e) => setTranscript(e.target.value)}
        rows={6}
        className="w-full rounded-xl border-2 border-outline-variant p-3 font-body text-base"
        placeholder="Your dictated or typed answer appears here — edit it freely."
      />

      <div className="flex gap-2">
        <button
          type="button"
          onClick={structure}
          disabled={!transcript.trim() || structuring}
          className="px-4 py-2 rounded-xl font-heading text-xs font-semibold border border-outline text-on-surface disabled:opacity-50"
        >
          {structuring ? 'Organizing…' : 'Organize into an essay'}
        </button>
        <button
          type="button"
          onClick={score}
          disabled={!transcript.trim() || scoring}
          className="px-4 py-2 rounded-xl font-heading text-xs font-semibold border border-outline text-on-surface disabled:opacity-50"
        >
          {scoring ? 'Scoring…' : 'Check my answer'}
        </button>
      </div>

      {structured && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-outline-variant/30">
          <div>
            <h4 className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">
              What you said
            </h4>
            <p className="text-sm font-body text-on-surface-variant whitespace-pre-wrap">{transcript}</p>
          </div>
          <div>
            <h4 className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">
              Organized version
            </h4>
            {structured.warnings.length > 0 && (
              <p role="alert" className="text-xs text-error font-body mb-2">{structured.warnings.join(' ')}</p>
            )}
            <ol className="list-decimal list-inside text-sm font-body space-y-1">
              {structured.outline.map((item, i) => <li key={i}>{item}</li>)}
            </ol>
            <div className="mt-2 space-y-2 text-sm font-body">
              {structured.paragraphs.map((p, i) => <p key={i}>{p}</p>)}
            </div>
          </div>
        </div>
      )}

      {scoreResult && (
        <div role="status" className="pt-2 border-t border-outline-variant/30 text-sm font-body">
          {scoreResult.know !== null && <p>Concepts covered: {Math.round(scoreResult.know * 100)}%</p>}
          <p className="text-xs text-on-surface-variant mt-1">
            Writing mechanics are shown separately and never affect how much credit you get for what you know.
          </p>
        </div>
      )}
    </div>
  );
};

export default VoiceEssay;
