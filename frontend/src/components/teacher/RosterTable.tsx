import React, { useMemo, useState } from 'react';

export interface RosterEntry {
  uid: string;
  email: string;
  gradeLevel: string | null;
  disabilities: string[];
  primary: string | null;
  daseScore: number | null;
  coverage: number | null;
  /** 95% bootstrap interval [lo, hi] (routers/evaluation.py); null for an
   * evaluation computed before this field existed. */
  scoreInterval: [number, number] | null;
  evaluatedAt: unknown;
  sessionsTotal: number;
  sessionsCompleted: number;
}

type SortKey = 'name' | 'score' | 'sessions';

interface Props {
  students: RosterEntry[];
  selectedId: string | null;
  onSelect: (uid: string) => void;
}

/**
 * Roster sourced ENTIRELY from GET /api/analytics/roster (roadmap P5-01) —
 * no per-student follow-up call. Score and coverage are always shown
 * together ("72% · coverage 65%"), never the score alone, since a score
 * at 40% coverage is a materially weaker claim than one at 90%.
 */
const RosterTable: React.FC<Props> = ({ students, selectedId, onSelect }) => {
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [filterDisability, setFilterDisability] = useState<string>('');

  const disabilityOptions = useMemo(() => {
    const set = new Set<string>();
    students.forEach((s) => s.disabilities.forEach((d) => set.add(d)));
    return Array.from(set).sort();
  }, [students]);

  const filtered = useMemo(() => {
    const base = filterDisability
      ? students.filter((s) => s.disabilities.includes(filterDisability))
      : students;
    const sorted = [...base];
    if (sortKey === 'score') {
      sorted.sort((a, b) => (b.daseScore ?? -1) - (a.daseScore ?? -1));
    } else if (sortKey === 'sessions') {
      sorted.sort((a, b) => b.sessionsTotal - a.sessionsTotal);
    } else {
      sorted.sort((a, b) => a.email.localeCompare(b.email));
    }
    return sorted;
  }, [students, filterDisability, sortKey]);

  return (
    <div className="glass-card rounded-3xl overflow-hidden">
      <div className="p-6 border-b border-white/20 flex flex-wrap justify-between items-center gap-3">
        <h3 className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest">
          Student Roster
        </h3>
        <div className="flex gap-2 items-center">
          <label htmlFor="roster-filter" className="sr-only">Filter by disability</label>
          <select
            id="roster-filter"
            value={filterDisability}
            onChange={(e) => setFilterDisability(e.target.value)}
            className="text-xs font-heading font-semibold bg-surface-container-low rounded-full px-3 py-1.5 border border-outline-variant"
          >
            <option value="">All students</option>
            {disabilityOptions.map((d) => <option key={d} value={d}>{d.replace(/_/g, ' ')}</option>)}
          </select>
          <label htmlFor="roster-sort" className="sr-only">Sort by</label>
          <select
            id="roster-sort"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="text-xs font-heading font-semibold bg-surface-container-low rounded-full px-3 py-1.5 border border-outline-variant"
          >
            <option value="name">Sort: Name</option>
            <option value="score">Sort: DASE score</option>
            <option value="sessions">Sort: Sessions</option>
          </select>
          <span className="text-xs text-primary font-bold">{filtered.length} students</span>
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="text-on-surface-variant text-center py-8">No students match this filter.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-surface-container-low">
                <th scope="col" className="px-6 py-3 text-left font-heading text-xs font-semibold text-on-surface-variant uppercase">Student</th>
                <th scope="col" className="px-6 py-3 text-left font-heading text-xs font-semibold text-on-surface-variant uppercase">Grade</th>
                <th scope="col" className="px-6 py-3 text-left font-heading text-xs font-semibold text-on-surface-variant uppercase">Primary profile</th>
                <th scope="col" className="px-6 py-3 text-left font-heading text-xs font-semibold text-on-surface-variant uppercase">DASE score · coverage</th>
                <th scope="col" className="px-6 py-3 text-left font-heading text-xs font-semibold text-on-surface-variant uppercase">Sessions</th>
                <th scope="col" className="px-6 py-3 text-right font-heading text-xs font-semibold text-on-surface-variant uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {filtered.map((s) => (
                <tr
                  key={s.uid}
                  className={`hover:bg-white/40 transition-colors cursor-pointer ${selectedId === s.uid ? 'bg-primary-fixed/30' : ''}`}
                  onClick={() => onSelect(s.uid)}
                >
                  <td className="px-6 py-4 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-surface-variant flex items-center justify-center font-bold text-primary text-sm">
                      {s.email.substring(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <p className="font-heading text-sm font-semibold text-on-surface">{s.email.split('@')[0]}</p>
                      <p className="text-xs text-on-surface-variant">{s.email}</p>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-on-surface">{s.gradeLevel ? `Grade ${s.gradeLevel}` : '—'}</td>
                  <td className="px-6 py-4 text-sm text-on-surface-variant">{s.primary ? s.primary.replace(/_/g, ' ') : '—'}</td>
                  <td className="px-6 py-4 text-sm">
                    {s.daseScore != null ? (
                      <>
                        <span className="font-heading font-semibold text-primary">
                          {Math.round(s.daseScore * 100)}% · coverage {Math.round((s.coverage ?? 0) * 100)}%
                        </span>
                        {s.scoreInterval && (
                          <span className="block text-[11px] text-on-surface-variant font-body">
                            95% CI: {Math.round(s.scoreInterval[0] * 100)}%–{Math.round(s.scoreInterval[1] * 100)}%
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-on-surface-variant text-xs">Not yet scored</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-on-surface-variant">{s.sessionsCompleted}/{s.sessionsTotal}</td>
                  <td className="px-6 py-4 text-right">
                    <button
                      onClick={(e) => { e.stopPropagation(); onSelect(s.uid); }}
                      className={`font-heading text-xs font-semibold px-4 py-2 rounded-full transition-all ${
                        selectedId === s.uid
                          ? 'bg-primary text-on-primary shadow-md'
                          : 'text-primary bg-primary/10 hover:bg-primary hover:text-white'
                      }`}
                    >
                      {selectedId === s.uid ? 'Selected' : 'View Analytics'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default RosterTable;
