import React from 'react';

interface Props {
  value: number;
  max?: number;
  onChange: (value: number) => void;
  label?: string;
}

/**
 * Keyboard-operable base-ten blocks (roadmap P4-06): hundreds/tens/ones
 * rendered as distinct block sizes. ArrowUp/Down change ones by 1;
 * PageUp/PageDown change tens by 10 — both always clamp to [0, max].
 */
const BaseTenBlocks: React.FC<Props> = ({ value, max = 999, onChange, label = 'Base-ten blocks' }) => {
  const clamp = (v: number) => Math.max(0, Math.min(max, v));

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowUp' || e.key === 'ArrowRight') {
      e.preventDefault();
      onChange(clamp(value + 1));
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') {
      e.preventDefault();
      onChange(clamp(value - 1));
    } else if (e.key === 'PageUp') {
      e.preventDefault();
      onChange(clamp(value + 10));
    } else if (e.key === 'PageDown') {
      e.preventDefault();
      onChange(clamp(value - 10));
    } else if (e.key === 'Home') {
      e.preventDefault();
      onChange(0);
    }
  };

  const hundreds = Math.floor(value / 100);
  const tens = Math.floor((value % 100) / 10);
  const ones = value % 10;
  const announcement = `${label}: ${value} — ${hundreds} hundreds, ${tens} tens and ${ones} ones`;

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
      className="outline-none focus:ring-2 focus:ring-primary rounded-xl p-3 cursor-pointer"
    >
      <div className="flex flex-wrap gap-3 items-end" aria-hidden="true">
        {Array.from({ length: hundreds }, (_, i) => (
          <div key={`h${i}`} className="w-12 h-12 bg-primary rounded-md" title="hundred" />
        ))}
        {Array.from({ length: tens }, (_, i) => (
          <div key={`t${i}`} className="w-3 h-12 bg-tertiary-fixed-dim rounded-sm" title="ten" />
        ))}
        {Array.from({ length: ones }, (_, i) => (
          <div key={`o${i}`} className="w-3 h-3 bg-secondary rounded-sm" title="one" />
        ))}
        {value === 0 && <span className="text-xs text-on-surface-variant font-body">(zero)</span>}
      </div>
      <p className="text-center font-heading font-semibold text-sm text-on-surface mt-3">
        {hundreds} hundreds, {tens} tens, {ones} ones = {value}
      </p>
      <p role="status" aria-live="polite" className="sr-only">{announcement}</p>
    </div>
  );
};

export default BaseTenBlocks;
