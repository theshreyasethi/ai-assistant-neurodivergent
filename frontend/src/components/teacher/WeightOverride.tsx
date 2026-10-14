import React, { useEffect, useState } from 'react';

import api from '../../services/api';

interface Props {
  studentId: string;
}

interface OverrideState {
  active: boolean;
  weights: Record<string, number> | null;
  reason: string | null;
}

/**
 * Teacher-facing editor for a per-student DASE weight override (roadmap
 * P5-06, backend/routers/overrides.py — built in Phase 3, had no frontend
 * until this component). A reason is mandatory and every change is logged
 * to audit_log server-side; this component only has to make sure a reason
 * is actually typed before the request can be sent.
 */
const WeightOverride: React.FC<Props> = ({ studentId }) => {
  // code -> full-form plain-language description (backend/data/dase_profiles.json's
  // _parameters, served as-is by GET /api/dase/profiles). Previously only the
  // codes (Object.keys) were kept and the descriptions already being fetched
  // were thrown away, which is why this panel showed bare codes like "ACC"
  // with no explanation of what they meant.
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const [current, setCurrent] = useState<OverrideState | null>(null);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.get('/api/dase/profiles'),
      api.get(`/api/teachers/students/${studentId}/dase-weights`),
    ])
      .then(([profilesRes, overrideRes]) => {
        setParameters(profilesRes.data.parameters ?? {});
        setCurrent(overrideRes.data);
        setDraft(overrideRes.data.weights ?? {});
        setReason('');
      })
      .catch(() => setError('Could not load weight override settings.'))
      .finally(() => setLoading(false));
  }, [studentId]);

  const toggleParam = (param: string, included: boolean) => {
    setDraft((prev) => {
      const next = { ...prev };
      if (included) next[param] = next[param] ?? 0.1;
      else delete next[param];
      return next;
    });
  };

  const save = async () => {
    if (!reason.trim() || Object.keys(draft).length === 0) return;
    setSaving(true);
    setError(null);
    try {
      await api.put(`/api/teachers/students/${studentId}/dase-weights`, { weights: draft, reason: reason.trim() });
      setCurrent({ active: true, weights: draft, reason: reason.trim() });
      setReason('');
    } catch {
      setError('Could not save the override — check the reason is at least a few words and every weight is zero or more.');
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.delete(`/api/teachers/students/${studentId}/dase-weights`);
      setCurrent({ active: false, weights: null, reason: null });
      setDraft({});
    } catch {
      setError('Could not clear the override.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p className="text-sm text-on-surface-variant font-body">Loading weight settings…</p>;

  return (
    <div className="glass-card rounded-3xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest">
            DASE weight override
          </h3>
          <p className="text-[11px] text-on-surface-variant font-body mt-0.5">
            DASE = Disability-Adaptive Scoring Engine
          </p>
        </div>
        {current?.active && (
          <button onClick={clear} disabled={saving} className="text-xs font-heading font-semibold text-error underline disabled:opacity-50">
            Clear override
          </button>
        )}
      </div>

      <p className="text-sm text-on-surface-variant font-body">
        {current?.active
          ? `An override is active for this student. Reason on file: "${current.reason}"`
          : 'This student is currently scored on their profile default weights.'}
      </p>

      <fieldset className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <legend className="sr-only">Parameters to include in the override</legend>
        {Object.keys(parameters).map((param) => {
          const included = param in draft;
          return (
            <label key={param} className="flex items-center gap-2 text-sm font-body" title={parameters[param]}>
              <input type="checkbox" checked={included} onChange={(e) => toggleParam(param, e.target.checked)} />
              {param}
              {included && (
                <input
                  type="number" min={0} step={0.01} value={draft[param]}
                  onChange={(e) => setDraft((prev) => ({ ...prev, [param]: Number(e.target.value) }))}
                  className="w-16 rounded border border-outline-variant px-1 text-xs"
                  aria-label={`Weight for ${param}`}
                />
              )}
            </label>
          );
        })}
      </fieldset>

      {Object.keys(parameters).length > 0 && (
        <details className="rounded-xl border border-outline-variant/40 px-4 py-2">
          <summary className="text-xs font-heading font-semibold text-on-surface-variant cursor-pointer select-none">
            What do these parameters mean?
          </summary>
          <dl className="mt-3 space-y-2">
            {Object.entries(parameters).map(([code, description]) => (
              <div key={code}>
                <dt className="text-xs font-heading font-bold text-on-surface">{code}</dt>
                <dd className="text-xs text-on-surface-variant font-body">{description}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}

      <label htmlFor="override-reason" className="block text-sm font-heading font-semibold text-on-surface">
        Reason (required)
      </label>
      <textarea
        id="override-reason"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={2}
        className="w-full rounded-xl border-2 border-outline-variant p-2 font-body text-sm"
        placeholder="Why are you adjusting this student's weights?"
      />

      {error && <p role="alert" className="text-xs text-error font-body">{error}</p>}

      <button
        onClick={save}
        disabled={saving || !reason.trim() || Object.keys(draft).length === 0}
        className="px-5 py-2 rounded-xl font-heading text-sm font-semibold bg-primary text-white disabled:opacity-50"
      >
        {saving ? 'Saving…' : 'Save override'}
      </button>
    </div>
  );
};

export default WeightOverride;
