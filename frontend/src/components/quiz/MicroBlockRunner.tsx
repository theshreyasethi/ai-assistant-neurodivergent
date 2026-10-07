import React from 'react';

export const DEFAULT_BLOCK_SIZE = 4;

interface Props {
  blockNumber: number;
  onContinue: () => void;
  onBreak: () => void;
  onStopHere: () => void;
}

/**
 * The pause point between micro-blocks (roadmap P4-12): after every 3-4
 * questions, explicitly offer "Take a break / Continue / Stop here" rather
 * than silently running the student through the whole quiz. Stopping here
 * is tracked as a COMPLETED block, not an abandoned session — anxiety
 * support means stopping early must never look like failure.
 */
const MicroBlockRunner: React.FC<Props> = ({ blockNumber, onContinue, onBreak, onStopHere }) => (
  <div role="dialog" aria-label="Block finished" className="glass-card rounded-3xl p-8 text-center space-y-4 max-w-md mx-auto">
    <span className="material-symbols-outlined text-primary text-4xl" aria-hidden="true">task_alt</span>
    <h3 className="font-heading text-xl font-semibold text-on-surface">Block {blockNumber} done!</h3>
    <p className="text-on-surface-variant font-body">You can keep going, take a short break, or stop here — all of these are a good choice.</p>
    <div className="flex flex-col gap-3 pt-2">
      <button
        type="button"
        onClick={onContinue}
        className="px-6 py-3 rounded-xl font-heading text-sm font-semibold bg-primary text-white shadow-md"
      >
        Continue
      </button>
      <button
        type="button"
        onClick={onBreak}
        className="px-6 py-3 rounded-xl font-heading text-sm font-semibold border border-outline text-on-surface"
      >
        Take a short break
      </button>
      <button
        type="button"
        onClick={onStopHere}
        className="px-6 py-3 rounded-xl font-heading text-sm font-semibold text-on-surface-variant underline"
      >
        Stop here for now
      </button>
    </div>
  </div>
);

export default MicroBlockRunner;
