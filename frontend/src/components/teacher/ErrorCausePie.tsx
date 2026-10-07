import React from 'react';
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

import ChartFrame from './ChartFrame';

export interface ErrorBreakdown {
  counts: Record<string, number>;
  proportions: Record<string, number>;
  meanConfidence: Record<string, number | null>;
  totalWrong: number;
  unclassified: number;
}

const CAUSE_LABEL: Record<string, string> = {
  KNOWLEDGE_GAP: 'Knowledge gap',
  ATTENTION_LAPSE: 'Attention lapse',
  PROCESSING_DELAY: 'Processing delay',
  COMPREHENSION_BARRIER: 'Comprehension barrier',
};

// Distinct fill AND an SVG stripe pattern per slice — never colour alone
// (WCAG 1.4.1). "Unclassified" gets a neutral grey with a cross-hatch, so
// it visually reads as "we don't know," not as a fifth cause on equal footing.
const CAUSE_FILL: Record<string, string> = {
  KNOWLEDGE_GAP: '#2a14b4', ATTENTION_LAPSE: '#c3c0ff', PROCESSING_DELAY: '#4edea3',
  COMPREHENSION_BARRIER: '#F59E0B', UNCLASSIFIED: '#9aa5b1',
};

interface Props {
  breakdown: ErrorBreakdown;
}

/**
 * Error-cause distribution donut (roadmap P5-03) with an explicit
 * "unclassified" slice — a small unclassified count is honest signal
 * (a telemetry gap), never hidden by folding it into another cause.
 */
const ErrorCausePie: React.FC<Props> = ({ breakdown }) => {
  const slices = Object.entries(breakdown.counts)
    .filter(([, count]) => count > 0)
    .map(([cause, count]) => ({ key: cause, label: CAUSE_LABEL[cause] ?? cause, value: count }));
  if (breakdown.unclassified > 0) {
    slices.push({ key: 'UNCLASSIFIED', label: 'Unclassified', value: breakdown.unclassified });
  }

  const total = breakdown.totalWrong + breakdown.unclassified;
  if (total === 0) {
    return (
      <div className="glass-card rounded-3xl p-6">
        <p className="text-sm text-on-surface-variant font-body">No wrong answers recorded yet.</p>
      </div>
    );
  }

  const sorted = [...slices].sort((a, b) => b.value - a.value);
  const summary =
    `Error causes for ${total} wrong answers. Most common: ${sorted[0].label}, ${sorted[0].value} ` +
    `(${Math.round((sorted[0].value / total) * 100)} percent).` +
    (breakdown.unclassified > 0
      ? ` ${breakdown.unclassified} unclassified — a telemetry gap, not a fifth cause.`
      : '');

  return (
    <ChartFrame
      title="Why wrong answers happen"
      summary={summary}
      tableChildren={
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th scope="col" className="text-left px-3 py-2 font-heading text-xs uppercase text-on-surface-variant">Cause</th>
              <th scope="col" className="text-left px-3 py-2 font-heading text-xs uppercase text-on-surface-variant">Count</th>
              <th scope="col" className="text-left px-3 py-2 font-heading text-xs uppercase text-on-surface-variant">Share</th>
              <th scope="col" className="text-left px-3 py-2 font-heading text-xs uppercase text-on-surface-variant">Mean confidence</th>
            </tr>
          </thead>
          <tbody>
            {slices.map((s) => (
              <tr key={s.key} className="border-t border-outline-variant/30">
                <th scope="row" className="text-left px-3 py-2 font-body font-normal">{s.label}</th>
                <td className="px-3 py-2">{s.value}</td>
                <td className="px-3 py-2">{Math.round((s.value / total) * 100)}%</td>
                <td className="px-3 py-2">
                  {s.key === 'UNCLASSIFIED' ? '—' : (breakdown.meanConfidence[s.key]?.toFixed(2) ?? '—')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <defs>
            {slices.map((s) => (
              <pattern key={s.key} id={`hatch-${s.key}`} patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
                <rect width="6" height="6" fill={CAUSE_FILL[s.key] ?? '#999'} />
                <line x1="0" y1="0" x2="0" y2="6" stroke="white" strokeOpacity={0.5} strokeWidth="2" />
              </pattern>
            ))}
          </defs>
          <Pie data={slices} dataKey="value" nameKey="label" innerRadius={55} outerRadius={90} paddingAngle={3}>
            {slices.map((s) => <Cell key={s.key} fill={`url(#hatch-${s.key})`} stroke={CAUSE_FILL[s.key]} strokeWidth={2} />)}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
};

export default ErrorCausePie;
