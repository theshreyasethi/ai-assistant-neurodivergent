import React from 'react';

interface Props {
  value: number;
  min?: number;
  max?: number;
  target?: number;
  onChange: (value: number) => void;
  label?: string;
}

/**
 * Keyboard-operable number line (roadmap P4-06) — dyscalculia manipulative.
 * Arrow keys move the marker by 1; Home/End jump to the ends. Never
 * drag-only: a motor-impaired student must be able to use this too.
 */
const NumberLine: React.FC<Props> = ({ value, min = 0, max = 10, target, onChange, label = 'Number line' }) => {
  const clamp = (v: number) => Math.max(min, Math.min(max, v));

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
      e.preventDefault();
      onChange(clamp(value + 1));
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
      e.preventDefault();
      onChange(clamp(value - 1));
    } else if (e.key === 'Home') {
      e.preventDefault();
      onChange(min);
    } else if (e.key === 'End') {
      e.preventDefault();
      onChange(max);
    }
  };

  const positionPct = ((value - min) / (max - min)) * 100;
  const remaining = target !== undefined ? target - value : null;
  const announcement =
    remaining === null
      ? `${label} at ${value}`
      : remaining === 0
        ? `${label} at ${value}; that's the target`
        : `${label} at ${value}; ${Math.abs(remaining)} more to ${target}`;

  return (
    <div className="py-4">
      <div
        role="slider"
        tabIndex={0}
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={announcement}
        onKeyDown={onKeyDown}
        className="relative h-10 outline-none focus:ring-2 focus:ring-primary rounded-full cursor-pointer"
      >
        <div className="absolute top-1/2 left-0 right-0 h-1 bg-outline-variant rounded-full -translate-y-1/2" />
        {target !== undefined && target >= min && target <= max && (
          <div
            aria-hidden="true"
            className="absolute top-1/2 w-3 h-3 rounded-full bg-tertiary-fixed-dim -translate-y-1/2 -translate-x-1/2"
            style={{ left: `${((target - min) / (max - min)) * 100}%` }}
          />
        )}
        <div
          aria-hidden="true"
          className="absolute top-1/2 w-6 h-6 rounded-full bg-primary border-2 border-white shadow-md -translate-y-1/2 -translate-x-1/2 transition-all"
          style={{ left: `${positionPct}%` }}
        />
      </div>
      <div className="flex justify-between text-xs text-on-surface-variant font-body mt-1">
        <span>{min}</span>
        <span className="font-heading font-semibold text-primary">{value}</span>
        <span>{max}</span>
      </div>
      <p role="status" aria-live="polite" className="sr-only">{announcement}</p>
    </div>
  );
};

export default NumberLine;
