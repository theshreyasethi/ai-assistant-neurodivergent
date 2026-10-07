import React, { useEffect, useState } from 'react';

import api from '../services/api';

interface AuditEntry {
  id: string;
  actor: string;
  action: string;
  target: string;
  details: { weights?: Record<string, number>; reason?: string };
  at: unknown;
}

/**
 * A teacher's own DASE weight-override history (roadmap P5-06) — every
 * PUT/DELETE to /api/teachers/students/{id}/dase-weights they've made,
 * each with the mandatory reason they gave at the time.
 */
const AuditLogPage: React.FC = () => {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/api/teachers/audit-log')
      .then((res) => setEntries(res.data.entries))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div>
        <span className="font-heading text-xs font-semibold text-primary uppercase tracking-widest">Teacher Dashboard</span>
        <h1 className="font-heading text-3xl font-bold text-on-surface mt-1">Weight Override History</h1>
        <p className="text-on-surface-variant font-body mt-1">
          Every DASE weight change you've made, with the reason you gave at the time.
        </p>
      </div>

      <div className="glass-card rounded-3xl overflow-hidden">
        {loading ? (
          <p className="text-on-surface-variant text-center py-8">Loading…</p>
        ) : entries.length === 0 ? (
          <p className="text-on-surface-variant text-center py-8">You haven't changed any student's weights yet.</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="bg-surface-container-low">
                <th scope="col" className="px-6 py-3 text-left font-heading text-xs font-semibold text-on-surface-variant uppercase">When</th>
                <th scope="col" className="px-6 py-3 text-left font-heading text-xs font-semibold text-on-surface-variant uppercase">Student</th>
                <th scope="col" className="px-6 py-3 text-left font-heading text-xs font-semibold text-on-surface-variant uppercase">Action</th>
                <th scope="col" className="px-6 py-3 text-left font-heading text-xs font-semibold text-on-surface-variant uppercase">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {entries.map((e) => (
                <tr key={e.id}>
                  <td className="px-6 py-4 text-sm text-on-surface-variant">
                    {typeof e.at === 'number' ? new Date(e.at).toLocaleString() : String(e.at ?? '—')}
                  </td>
                  <td className="px-6 py-4 text-sm font-heading font-semibold text-on-surface">{e.target}</td>
                  <td className="px-6 py-4 text-sm text-on-surface-variant">{e.action.replace('dase_weights.', '').replace(/_/g, ' ')}</td>
                  <td className="px-6 py-4 text-sm text-on-surface-variant">{e.details?.reason ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default AuditLogPage;
