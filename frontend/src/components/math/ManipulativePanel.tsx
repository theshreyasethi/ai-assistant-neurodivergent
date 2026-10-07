import React, { useState } from 'react';

import NumberLine from './NumberLine';
import TenFrame from './TenFrame';
import FractionBar from './FractionBar';
import BaseTenBlocks from './BaseTenBlocks';

export type ManipulativeKind = 'numberline' | 'tenframe' | 'fraction' | 'baseten';

interface Props {
  kind: ManipulativeKind;
  /** Called with the student's current manipulative value whenever it
   * changes — the caller (e.g. QuizPage) decides what, if anything, to do
   * with it (such as filling in a fill_blank answer). */
  onValueChange: (value: number) => void;
  max?: number;
  target?: number;
}

/**
 * Mounts the right manipulative beside a math item for the dyscalculia
 * profile (roadmap P4-06) — appears alongside the question, never replaces
 * the normal answer controls, so a student can use it or ignore it.
 */
const ManipulativePanel: React.FC<Props> = ({ kind, onValueChange, max = 20, target }) => {
  const [value, setValue] = useState(0);
  const [denominator, setDenominator] = useState(4);

  const update = (next: number) => {
    setValue(next);
    onValueChange(next);
  };

  return (
    <div className="glass-card rounded-2xl p-4 mt-3">
      <p className="text-xs font-heading font-semibold text-on-surface-variant uppercase tracking-widest mb-2">
        Try it with blocks
      </p>
      {kind === 'numberline' && <NumberLine value={value} max={max} target={target} onChange={update} />}
      {kind === 'tenframe' && <TenFrame value={value} max={Math.min(max, 10)} onChange={update} />}
      {kind === 'fraction' && (
        <FractionBar
          numerator={value}
          denominator={denominator}
          onNumeratorChange={update}
          onDenominatorChange={setDenominator}
        />
      )}
      {kind === 'baseten' && <BaseTenBlocks value={value} max={max} onChange={update} />}
    </div>
  );
};

export default ManipulativePanel;
