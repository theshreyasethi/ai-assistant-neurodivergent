import React, { useState } from 'react';

import api from '../../services/api';
import { speakSentences, stopSpeaking } from '../../services/speech';
import BaseTenBlocks from './BaseTenBlocks';

interface MathStep {
  op: string;
  expr: string;
  result: string;
  say: string;
}

interface Props {
  problem: string;
  /** Called each time a step is replayed — counts as `reRead` the same way
   * a quiz question's TTS replay does, for whichever telemetry consumer
   * cares. */
  onReplay?: () => void;
}

/**
 * Multi-sensory math step player (roadmap P4-08): speaks each verified
 * micro-step (backend/services/math_steps.py — every step is re-checked by
 * a restricted evaluator before being shown here) while the base-ten block
 * display updates to match, so the same information reaches both an
 * auditory and a visual channel at once.
 */
const StepPlayer: React.FC<Props> = ({ problem, onReplay }) => {
  const [steps, setSteps] = useState<MathStep[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [degraded, setDegraded] = useState(false);
  const [currentStep, setCurrentStep] = useState(-1);
  const [playing, setPlaying] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.post('/api/math/steps', { problem });
      setSteps(data.steps);
      setDegraded(data.degraded);
    } catch {
      setSteps([]);
      setDegraded(true);
    } finally {
      setLoading(false);
    }
  };

  const play = (fromReplay = false) => {
    if (!steps || steps.length === 0) return;
    if (fromReplay) onReplay?.();
    setPlaying(true);
    speakSentences(steps.map((s) => s.say), {
      rate: 0.9,
      onSentenceStart: (idx) => setCurrentStep(idx),
      onDone: () => {
        setPlaying(false);
        setCurrentStep(-1);
      },
    });
  };

  const stop = () => {
    stopSpeaking();
    setPlaying(false);
    setCurrentStep(-1);
  };

  const currentValue = currentStep >= 0 && steps ? Number(steps[currentStep].result) || 0 : 0;

  if (!steps) {
    return (
      <button
        type="button"
        onClick={load}
        disabled={loading}
        className="px-4 py-2 rounded-xl font-heading text-xs font-semibold bg-primary text-white disabled:opacity-60"
      >
        {loading ? 'Working it out…' : 'Show step by step'}
      </button>
    );
  }

  if (steps.length === 0) {
    return (
      <p role="alert" className="text-sm text-error font-body">
        {degraded ? 'Could not verify a step-by-step breakdown right now.' : 'No steps to show.'}
      </p>
    );
  }

  return (
    <div className="glass-card rounded-2xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest">
          Step by step
        </h4>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => play(steps.length > 0 && currentStep === -1 ? false : true)}
            disabled={playing}
            className="text-xs font-heading font-semibold text-primary underline disabled:opacity-50"
          >
            {playing ? 'Playing…' : 'Play'}
          </button>
          <button type="button" onClick={stop} className="text-xs font-heading font-semibold text-on-surface-variant underline">
            Stop
          </button>
        </div>
      </div>

      <ol className="space-y-1">
        {steps.map((step, idx) => (
          <li
            key={idx}
            className={`text-sm font-body p-2 rounded-lg ${idx === currentStep ? 'bg-primary-container/30 font-semibold' : ''}`}
          >
            {step.say}
          </li>
        ))}
      </ol>

      {currentStep >= 0 && (
        <BaseTenBlocks value={currentValue} max={999} onChange={() => {}} label="Current result" />
      )}
    </div>
  );
};

export default StepPlayer;
