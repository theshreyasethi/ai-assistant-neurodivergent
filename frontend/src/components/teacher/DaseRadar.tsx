import React from 'react';
import {
  Legend, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer,
} from 'recharts';

import ChartFrame from './ChartFrame';

export interface DaseEvaluation {
  profile: string;
  score: number | null;
  coverage: number;
  parameters: Record<string, number>;
  diagnosticOnly: Record<string, number>;
  missingParameters: string[];
  /** 95% Wilson interval per proportion-shaped parameter (ACC/COMP/PATTERN/
   * TASK_COMP) — absent for parameters that aren't a simple proportion, and
   * absent entirely on an evaluation computed before U8. */
  parameterIntervals?: Record<string, [number, number]>;
}

const PARAM_LABEL: Record<string, string> = {
  ACC: 'Accuracy', ADJ_ACC: 'Adjusted accuracy', COMP: 'Comprehension', TIME_EFF: 'Time efficiency',
  ATT_SPAN: 'Face presence', PACE_STAB: 'Pace stability', ACC_STAB: 'Accuracy stability',
  EFFORT: 'Effort', LRN_VEL: 'Learning velocity',
  TASK_COMP: 'Task completion', READ_FL: 'Reading fluency', VOICE_Q: 'Voice quality',
  NAV_EFF: 'Navigation efficiency', PATTERN: 'Pattern recognition', RESIL: 'Resilience',
  VIS_ENG: 'Visual engagement', KNOW: 'Knowledge', EXPR: 'Written expression',
};

interface Props {
  latest: DaseEvaluation;
}

/**
 * Per-student DASE parameter radar (roadmap P5-02). Unmeasured parameters
 * are OMITTED, never plotted at 0 (a 0 would read as "measured and
 * failing", which is a different and false claim). Diagnostic-only
 * parameters are drawn as a separate, dashed series labelled "reported,
 * not scored" — never visually indistinguishable from a scored one.
 */
const DaseRadar: React.FC<Props> = ({ latest }) => {
  const rows = Object.entries(latest.parameters).map(([key, value]) => ({
    key,
    label: PARAM_LABEL[key] ?? key,
    value,
    diagnostic: key in (latest.diagnosticOnly ?? {}),
  }));

  if (rows.length === 0) {
    return (
      <div className="glass-card rounded-3xl p-6">
        <p className="text-sm text-on-surface-variant font-body">No DASE parameters measured yet for this student.</p>
      </div>
    );
  }

  const sorted = [...rows].sort((a, b) => b.value - a.value);
  const top = sorted[0];
  const low = sorted[sorted.length - 1];
  const summary =
    `DASE parameters, ${latest.profile} profile. Strongest: ${top.label} ${top.value.toFixed(2)}; ` +
    `lowest: ${low.label} ${low.value.toFixed(2)}. Coverage ${Math.round(latest.coverage * 100)} percent — ` +
    `face-presence ("ATT_SPAN") measures whether a face was visible, not attention.`;

  return (
    <ChartFrame
      title={`DASE parameters (${latest.profile} profile)`}
      summary={summary}
      tableChildren={
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th scope="col" className="text-left px-3 py-2 font-heading text-xs uppercase text-on-surface-variant">Parameter</th>
              <th scope="col" className="text-left px-3 py-2 font-heading text-xs uppercase text-on-surface-variant">Value</th>
              <th scope="col" className="text-left px-3 py-2 font-heading text-xs uppercase text-on-surface-variant">95% CI</th>
              <th scope="col" className="text-left px-3 py-2 font-heading text-xs uppercase text-on-surface-variant">Used in score?</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const interval = latest.parameterIntervals?.[r.key];
              return (
                <tr key={r.key} className="border-t border-outline-variant/30">
                  <th scope="row" className="text-left px-3 py-2 font-body font-normal">{r.label}</th>
                  <td className="px-3 py-2">{r.value.toFixed(2)}</td>
                  <td className="px-3 py-2 text-on-surface-variant">
                    {interval ? `${interval[0].toFixed(2)}–${interval[1].toFixed(2)}` : '—'}
                  </td>
                  <td className="px-3 py-2">{r.diagnostic ? 'No — reported only' : 'Yes'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      }
    >
      <ResponsiveContainer width="100%" height={320}>
        <RadarChart data={rows}>
          <PolarGrid />
          <PolarAngleAxis dataKey="label" tick={{ fontSize: 11 }} />
          <PolarRadiusAxis domain={[0, 1]} tickCount={5} />
          <Radar
            name="Scored"
            dataKey={(r: any) => (r.diagnostic ? null : r.value)}
            stroke="#2a14b4" fill="#2a14b4" fillOpacity={0.35}
          />
          <Radar
            name="Reported, not scored"
            dataKey={(r: any) => (r.diagnostic ? r.value : null)}
            stroke="#0f766e" fill="none" strokeDasharray="5 4"
          />
          <Legend />
        </RadarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
};

export default DaseRadar;
