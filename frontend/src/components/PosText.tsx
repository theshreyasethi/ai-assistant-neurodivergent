import React, { useState } from 'react';

import api from '../services/api';

interface PosToken {
  text: string;
  pos: string;
  whitespaceAfter: boolean;
}

interface Props {
  text: string;
}

// Colour AND underline style/shape per tag — never colour alone (WCAG 1.4.1),
// and each combination stays distinguishable in greyscale.
const POS_STYLE: Record<string, { color: string; underline: string }> = {
  NOUN: { color: 'text-primary', underline: 'border-b-2 border-solid border-primary' },
  PROPN: { color: 'text-primary', underline: 'border-b-2 border-solid border-primary' },
  VERB: { color: 'text-error', underline: 'border-b-2 border-dashed border-error' },
  ADJ: { color: 'text-tertiary-fixed-dim', underline: 'border-b-2 border-dotted border-tertiary-fixed-dim' },
  ADV: { color: 'text-tertiary-fixed-dim', underline: 'border-b border-dotted border-tertiary-fixed-dim' },
  PRON: { color: 'text-secondary', underline: 'border-b border-double border-secondary' },
  DET: { color: 'text-on-surface-variant', underline: '' },
  ADP: { color: 'text-on-surface-variant', underline: '' },
  NUM: { color: 'text-error', underline: 'border-b-2 border-solid border-error' },
};

const LEGEND: Array<[string, string]> = [
  ['NOUN / PROPN', 'Naming word'],
  ['VERB', 'Action word'],
  ['ADJ', 'Describes a noun'],
  ['ADV', 'Describes a verb'],
  ['PRON', 'Stands in for a noun'],
];

/**
 * Experimental part-of-speech reader (roadmap P4-03). Labelled experimental
 * everywhere — docs/ROADMAP.md is explicit that colour-coded POS tags have
 * no supporting evidence yet for this population; this exists so that
 * hypothesis CAN be tested, not because it's already proven.
 */
const PosText: React.FC<Props> = ({ text }) => {
  const [tokens, setTokens] = useState<PosToken[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [degraded, setDegraded] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.post('/api/nlp/pos', { text });
      setTokens(data.tokens);
      setDegraded(data.degraded);
    } catch {
      setDegraded(true);
      setTokens([]);
    } finally {
      setLoading(false);
    }
  };

  if (!tokens) {
    return (
      <button
        type="button"
        onClick={load}
        disabled={loading}
        className="px-4 py-2 rounded-xl font-heading text-xs font-semibold border border-outline text-on-surface-variant disabled:opacity-60"
      >
        {loading ? 'Tagging…' : 'Show word types (experimental)'}
      </button>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs font-heading font-semibold text-on-surface-variant uppercase tracking-widest">
        Experimental — word types
      </p>
      {degraded && <p className="text-xs text-error font-body">Tagging unavailable right now.</p>}
      <p className="text-base leading-relaxed font-body">
        {tokens.map((t, i) => {
          const style = POS_STYLE[t.pos];
          return (
            <span key={i} className={style ? `${style.color} ${style.underline}` : undefined}>
              {t.text}
              {t.whitespaceAfter ? ' ' : ''}
            </span>
          );
        })}
      </p>
      <div className="flex flex-wrap gap-3 text-xs text-on-surface-variant font-body border-t border-outline-variant/30 pt-2">
        {LEGEND.map(([label, desc]) => (
          <span key={label}>
            <strong>{label}</strong>: {desc}
          </span>
        ))}
      </div>
    </div>
  );
};

export default PosText;
