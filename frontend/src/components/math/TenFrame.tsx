import React from 'react';

interface Props {
  value: number;
  max?: number;
  onChange: (value: number) => void;
  label?: string;
}

/**
 * Keyboard-operable ten-frame (roadmap P4-06) — a 2x5 grid where arrow
 * keys fill/empty cells one at a time, making "how many more to ten"
 * visible rather than purely symbolic.
 */
const TenFrame: React.FC<Props> = ({ value, max = 10, onChange, label = 'Ten frame' }) => {
  const clamp = (v: number) => Math.max(0, Math.min(max, v));

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
      e.preventDefault();
      onChange(clamp(value + 1));
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
      e.preventDefault();
      onChange(clamp(value - 1));
    } else if (e.key === 'Home') {
      e.preventDefault();
      onChange(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      onChange(max);
    }
  };

  const cells = Array.from({ length: max }, (_, i) => i < value);
  const announcement = `${label}: ${value} filled, ${max - value} empty`;

  return (
    <div
      role="slider"
      tabIndex={0}
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-valuetext={announcement}
      onKeyDown={onKeyDown}
      className="inline-block p-2 rounded-2xl outline-none focus:ring-2 focus:ring-primary cursor-pointer"
    >
      <div className="grid grid-cols-5 gap-2" aria-hidden="true">
        {cells.map((filled, i) => (
          <div
            key={i}
            className={`w-8 h-8 rounded-md border-2 transition-colors ${
              filled ? 'bg-primary border-primary' : 'bg-surface-container-low border-outline-variant'
            }`}
          />
        ))}
      </div>
      <p className="text-center text-xs font-heading font-semibold text-on-surface-variant mt-2">
        {value} / {max}
      </p>
      <p role="status" aria-live="polite" className="sr-only">{announcement}</p>
    </div>
  );
};

export default TenFrame;
