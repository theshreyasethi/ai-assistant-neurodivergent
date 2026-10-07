import React from 'react';

interface Props {
  numerator: number;
  denominator: number;
  onNumeratorChange: (value: number) => void;
  onDenominatorChange?: (value: number) => void;
  label?: string;
}

/**
 * Keyboard-operable fraction bar (roadmap P4-06). Left/Right adjust how many
 * parts are filled; Up/Down adjust how many EQUAL parts the bar is divided
 * into (only when onDenominatorChange is given — some uses fix the
 * denominator and only let the student select the numerator).
 */
const FractionBar: React.FC<Props> = ({ numerator, denominator, onNumeratorChange, onDenominatorChange, label = 'Fraction bar' }) => {
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      onNumeratorChange(Math.min(denominator, numerator + 1));
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      onNumeratorChange(Math.max(0, numerator - 1));
    } else if (e.key === 'ArrowUp' && onDenominatorChange) {
      e.preventDefault();
      const next = Math.min(12, denominator + 1);
      onDenominatorChange(next);
      if (numerator > next) onNumeratorChange(next);
    } else if (e.key === 'ArrowDown' && onDenominatorChange) {
      e.preventDefault();
      const next = Math.max(1, denominator - 1);
      onDenominatorChange(next);
      if (numerator > next) onNumeratorChange(next);
    }
  };

  const segments = Array.from({ length: denominator }, (_, i) => i < numerator);
  const announcement = `${label}: ${numerator} of ${denominator} parts filled`;

  return (
    <div
      role="group"
      tabIndex={0}
      aria-label={label}
      aria-description={announcement}
      onKeyDown={onKeyDown}
      className="outline-none focus:ring-2 focus:ring-primary rounded-xl p-2 cursor-pointer"
    >
      <div className="flex w-full h-10 rounded-lg overflow-hidden border border-outline-variant" aria-hidden="true">
        {segments.map((filled, i) => (
          <div
            key={i}
            className={`flex-1 border-r border-white/50 last:border-r-0 transition-colors ${
              filled ? 'bg-primary' : 'bg-surface-container-low'
            }`}
          />
        ))}
      </div>
      <p className="text-center font-heading font-semibold text-sm text-on-surface mt-2">
        {numerator} / {denominator}
      </p>
      <p role="status" aria-live="polite" className="sr-only">{announcement}</p>
    </div>
  );
};

export default FractionBar;
