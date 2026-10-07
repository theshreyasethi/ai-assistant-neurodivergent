import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";
import RosterTable, { RosterEntry } from "../components/teacher/RosterTable";
import DaseRadar, { DaseEvaluation } from "../components/teacher/DaseRadar";
import ErrorCausePie, { ErrorBreakdown } from "../components/teacher/ErrorCausePie";
import WeightOverride from "../components/teacher/WeightOverride";

interface ClassAggregates {
  totalStudents: number;
  scoredStudents: number;
  classAverageScore: number | null;
  averageByPrimaryDisability: Record<string, number>;
  averageCompletionRate: number | null;
}

interface StudentDetail {
  studentId: string;
  profile: { primary: string | null; disabilities: string[] };
  latest: (DaseEvaluation & { errorBreakdown: ErrorBreakdown; overrideId?: string }) | null;
  trend: { computedAt: unknown; score: number; coverage: number }[];
  errorBreakdownCombined: Record<string, number>;
  evaluationCount: number;
}

/**
 * Sourced EXCLUSIVELY from /api/analytics/{roster,class,student/:id}
 * (roadmap P5-01) — the legacy /teacher/students + one /teacher/analytics/
 * {uid} call PER STUDENT (an N+1 pattern the original dashboard had) are
 * gone. On load this makes exactly 2 requests (roster + class); a 3rd
 * (student detail) fires only once a row is actually selected.
 */
const TeacherDashboardPage: React.FC = () => {
  const [roster, setRoster] = useState<RosterEntry[]>([]);
  const [rosterLoading, setRosterLoading] = useState(true);
  const [classAgg, setClassAgg] = useState<ClassAggregates | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<StudentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [recommendation, setRecommendation] = useState<string | null>(null);
  const [recommendationLoading, setRecommendationLoading] = useState(false);

  useEffect(() => {
    api.get("/api/analytics/roster")
      .then((res) => setRoster(res.data.students))
      .catch(() => setRoster([]))
      .finally(() => setRosterLoading(false));

    api.get("/api/analytics/class")
      .then((res) => setClassAgg(res.data))
      .catch(() => setClassAgg(null));
  }, []);

  useEffect(() => {
    setRecommendation(null);
    if (!selectedId) { setDetail(null); return; }
    setDetailLoading(true);
    api.get(`/api/analytics/student/${selectedId}`)
      .then((res) => setDetail(res.data))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  const handleGetRecommendation = async () => {
    if (!selectedId) return;
    setRecommendationLoading(true);
    try {
      const res = await api.post("/api/analytics/recommendation", { studentId: selectedId });
      setRecommendation(res.data.recommendation);
    } catch {
      setRecommendation("Could not load suggestions right now.");
    } finally {
      setRecommendationLoading(false);
    }
  };

  const selectedStudent = roster.find((s) => s.uid === selectedId);

  return (
    <div className="min-h-screen bg-surface-bright animate-fade-in">
      <div className="max-w-[1440px] mx-auto px-4 md:px-12 py-8 space-y-8">
        {/* Page Header */}
        <div className="flex flex-wrap justify-between items-end gap-3">
          <div>
            <span className="font-heading text-xs font-semibold text-primary uppercase tracking-widest">Teacher Dashboard</span>
            <h1 className="font-heading text-3xl md:text-4xl font-bold text-on-surface mt-1">Classroom Overview</h1>
          </div>
          <Link to="/audit-log" className="text-xs font-heading font-semibold text-primary underline">
            View weight-override history
          </Link>
        </div>

        {/* Face-presence disclaimer — shown once, prominently, rather than
            buried in a tooltip, since it qualifies every score below. */}
        <div role="note" className="glass-card rounded-2xl p-4 border-l-4 border-primary text-sm font-body text-on-surface-variant">
          <strong className="text-on-surface">A note on these numbers:</strong> any focus/attention-related
          figure here measures <strong>face presence</strong> — whether a face was visible to the camera —
          not where the student was actually looking or whether they were paying attention. DASE scores are
          a support signal, not a grade, and always shown with their <strong>coverage</strong>: the fraction
          of the scoring profile's intended weight that could actually be measured this session. A score at
          low coverage is a weaker claim than one at high coverage.
        </div>

        {/* Hero Banner */}
        <section className="relative overflow-hidden rounded-3xl p-8 md:p-10 bg-primary-container text-white shadow-lg">
          <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
            <div>
              <h2 className="font-heading text-2xl md:text-3xl font-bold mb-2">Welcome back, Professor</h2>
              <p className="text-lg opacity-90 max-w-2xl font-body">
                {rosterLoading ? "Loading your classroom…" : `Your classroom has ${roster.length} students.`}
              </p>
            </div>
            <div className="flex gap-3">
              <div className="bg-white/20 backdrop-blur-md rounded-2xl p-4 border border-white/30 text-center min-w-[150px]">
                <p className="font-heading text-xs font-semibold uppercase tracking-wider opacity-80">Students</p>
                <p className="font-heading text-3xl font-bold">{rosterLoading ? "—" : roster.length}</p>
              </div>
              <div className="bg-white/20 backdrop-blur-md rounded-2xl p-4 border border-white/30 text-center min-w-[150px]">
                <p className="font-heading text-xs font-semibold uppercase tracking-wider opacity-80">Class avg. DASE</p>
                <p className="font-heading text-3xl font-bold">
                  {classAgg?.classAverageScore != null
                    ? `${Math.round(classAgg.classAverageScore * 100)}%`
                    : "—"}
                </p>
                {classAgg && (
                  <p className="text-[11px] opacity-80 mt-0.5">
                    {classAgg.scoredStudents}/{classAgg.totalStudents} scored
                  </p>
                )}
              </div>
              <div className="bg-white/20 backdrop-blur-md rounded-2xl p-4 border border-white/30 text-center min-w-[150px]">
                <p className="font-heading text-xs font-semibold uppercase tracking-wider opacity-80">Avg. completion</p>
                <p className="font-heading text-3xl font-bold">
                  {classAgg?.averageCompletionRate != null ? `${Math.round(classAgg.averageCompletionRate * 100)}%` : "—"}
                </p>
              </div>
            </div>
          </div>
        </section>

        {classAgg && Object.keys(classAgg.averageByPrimaryDisability).length > 0 && (
          <div className="glass-card rounded-3xl p-6">
            <h3 className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-3">
              Average DASE score by primary profile
            </h3>
            <div className="flex flex-wrap gap-3">
              {Object.entries(classAgg.averageByPrimaryDisability).map(([profile, avg]) => (
                <span key={profile} className="text-xs font-body bg-surface-container-low px-3 py-1.5 rounded-full">
                  {profile.replace(/_/g, " ")}: <strong>{Math.round(avg * 100)}%</strong>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Student Roster */}
        {rosterLoading ? (
          <p className="text-on-surface-variant text-center py-8">Loading students...</p>
        ) : roster.length === 0 ? (
          <div className="glass-card rounded-3xl p-8 text-center text-on-surface-variant">
            No students assigned to you yet.
          </div>
        ) : (
          <RosterTable students={roster} selectedId={selectedId} onSelect={setSelectedId} />
        )}

        {/* Per-student drill-down */}
        {selectedId && (
          <div className="space-y-6 animate-fade-in">
            <h2 className="font-heading text-xl font-semibold text-on-surface text-center">
              Analytics: {selectedStudent?.email ?? selectedId}
            </h2>

            {detailLoading ? (
              <p className="text-on-surface-variant text-center py-8">Loading analytics...</p>
            ) : !detail || !detail.latest ? (
              <p className="text-on-surface-variant text-center py-8">
                No DASE evaluation yet for this student — one is computed after their first scored quiz session.
              </p>
            ) : (
              <>
                {detail.latest.overrideId && (
                  <div className="glass-card rounded-2xl p-4 border-l-4 border-tertiary-fixed-dim text-sm font-body">
                    This student's score uses a <strong>teacher-set weight override</strong> rather than the
                    profile default — see the override panel below.
                  </div>
                )}

                <DaseRadar latest={detail.latest} />
                <ErrorCausePie breakdown={detail.latest.errorBreakdown} />

                {Object.keys(detail.errorBreakdownCombined).length > 0 && (
                  <div className="glass-card rounded-2xl p-5">
                    <p className="text-xs text-on-surface-variant mb-2">
                      Across all {detail.evaluationCount} evaluated sessions
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(detail.errorBreakdownCombined).map(([label, count]) => (
                        <span key={label} className="text-xs font-body bg-surface-container-low px-3 py-1.5 rounded-full">
                          {label.replace(/_/g, " ")}: <strong>{count}</strong>
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="glass-card rounded-3xl p-6 flex items-center justify-between">
                  <h3 className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest">
                    Teaching suggestions
                  </h3>
                  <button
                    onClick={handleGetRecommendation}
                    disabled={recommendationLoading}
                    className="text-xs font-heading font-semibold px-3 py-1.5 rounded-full bg-primary/10 text-primary hover:bg-primary hover:text-white transition-all disabled:opacity-50"
                  >
                    {recommendationLoading ? "Thinking…" : "Get teaching suggestions"}
                  </button>
                </div>
                {recommendation && (
                  <div className="glass-card rounded-2xl p-4 text-sm text-on-surface font-body whitespace-pre-line">
                    {recommendation}
                  </div>
                )}

                <WeightOverride studentId={selectedId} />
              </>
            )}
          </div>
        )}
      </div>

      <div className="fixed top-0 left-0 w-full h-full pointer-events-none -z-10 overflow-hidden">
        <div className="absolute top-[-10%] right-[-5%] w-[40%] h-[60%] bg-primary/5 rounded-full blur-[120px] motion-safe:animate-pulse"></div>
        <div className="absolute bottom-[-10%] left-[-5%] w-[30%] h-[50%] bg-surface-variant/40 rounded-full blur-[120px]"></div>
      </div>
    </div>
  );
};

export default TeacherDashboardPage;
