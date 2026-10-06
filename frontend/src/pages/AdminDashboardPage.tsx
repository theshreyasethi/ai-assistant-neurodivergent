import React, { useEffect, useState } from "react";
import api from "../services/api";
import { notify } from "../services/notify";
import CredentialSheet, { Credential } from "../components/admin/CredentialSheet";

interface UserRecord {
  uid: string;
  email: string;
  role: string;
  grade_level: string | null;
  teacher_id: string | null;
  status: string | null;
}

function extractErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    if (typeof first?.msg === "string") return first.msg.replace(/^Value error,\s*/, "");
  }
  return fallback;
}

const AdminDashboardPage: React.FC = () => {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(true);

  // Create-account form — v2 schema (roadmap task P1-09): no password field
  // at all, the backend always generates one (services/accounts.py).
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<"student" | "teacher">("student");
  const [gradeLevel, setGradeLevel] = useState("");
  const [teacherId, setTeacherId] = useState("");
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // One-time credential hand-off (shown after create, reset-password)
  const [credential, setCredential] = useState<Credential | null>(null);

  // Per-row lifecycle actions
  const [reassigningUid, setReassigningUid] = useState<string | null>(null);
  const [reassignTeacherId, setReassignTeacherId] = useState("");
  const [busyUid, setBusyUid] = useState<string | null>(null);

  const fetchUsers = () => {
    setLoading(true);
    api
      .get("/admin/users")
      .then((res) => setUsers(res.data.users))
      .catch(() => setUsers([]))
      .finally(() => setLoading(false));
  };

  useEffect(fetchUsers, []);

  const teachers = users.filter((u) => u.role === "teacher");
  const activeTeachers = teachers.filter((t) => t.status !== "disabled");
  const students = users.filter((u) => u.role === "student");
  const admins = users.filter((u) => u.role === "admin");

  const teacherEmailMap: Record<string, string> = {};
  teachers.forEach((t) => {
    teacherEmailMap[t.uid] = t.email;
  });

  // Required teacher when creating a student (roadmap task P1-09): the
  // backend already rejects this server-side (422 TeacherInvalid), but a
  // blocked submit button gives the admin an immediate, clear reason
  // rather than a round trip to find out.
  const teacherRequiredAndMissing = role === "student" && !teacherId;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (teacherRequiredAndMissing) {
      setMessage("Students must be assigned to an active teacher.");
      return;
    }
    setCreating(true);
    setMessage(null);
    try {
      const payload: Record<string, unknown> = { role, displayName, username };
      if (role === "student") {
        if (gradeLevel) payload.gradeLevel = gradeLevel;
        payload.teacherId = teacherId;
      }
      const res = await api.post("/api/admin/users", payload);
      setDisplayName("");
      setUsername("");
      setGradeLevel("");
      setTeacherId("");
      fetchUsers();
      setCredential({
        loginId: res.data.loginId,
        temporaryPassword: res.data.temporaryPassword,
        displayName: res.data.displayName,
      });
    } catch (err) {
      setMessage(extractErrorMessage(err, "Failed to create user"));
    } finally {
      setCreating(false);
    }
  };

  const handleResetPassword = async (u: UserRecord) => {
    setBusyUid(u.uid);
    try {
      const res = await api.post(`/api/admin/users/${u.uid}/reset-password`);
      setCredential({
        loginId: res.data.loginId,
        temporaryPassword: res.data.temporaryPassword,
        displayName: u.email,
      });
      fetchUsers();
    } catch (err) {
      notify(extractErrorMessage(err, "Could not reset that password."), { kind: "error" });
    } finally {
      setBusyUid(null);
    }
  };

  const handleToggleDisabled = async (u: UserRecord) => {
    const action = u.status === "disabled" ? "enable" : "disable";
    setBusyUid(u.uid);
    try {
      await api.post(`/api/admin/users/${u.uid}/${action}`);
      notify(`Account ${action}d.`, { kind: "success" });
      fetchUsers();
    } catch (err) {
      notify(extractErrorMessage(err, `Could not ${action} that account.`), { kind: "error" });
    } finally {
      setBusyUid(null);
    }
  };

  const startReassign = (u: UserRecord) => {
    setReassigningUid(u.uid);
    setReassignTeacherId(u.teacher_id || "");
  };

  const cancelReassign = () => {
    setReassigningUid(null);
    setReassignTeacherId("");
  };

  const confirmReassign = async (u: UserRecord) => {
    if (!reassignTeacherId) return;
    setBusyUid(u.uid);
    try {
      await api.patch(`/api/admin/students/${u.uid}/teacher`, { teacherId: reassignTeacherId });
      notify("Student reassigned.", { kind: "success" });
      cancelReassign();
      fetchUsers();
    } catch (err) {
      notify(extractErrorMessage(err, "Could not reassign that student."), { kind: "error" });
    } finally {
      setBusyUid(null);
    }
  };

  const roleIcon = (r: string) =>
    r === "admin" ? "admin_panel_settings" : r === "teacher" ? "person" : "school";
  const roleBadge = (r: string) =>
    r === "admin"
      ? "bg-tertiary-fixed text-on-tertiary-fixed-variant"
      : r === "teacher"
      ? "bg-primary-fixed text-on-primary-fixed-variant"
      : "bg-surface-variant text-primary";

  return (
    <div className="min-h-screen bg-surface-bright animate-fade-in">
      <div className="max-w-[1440px] mx-auto px-4 md:px-12 py-8 space-y-8">
        {/* Header */}
        <div>
          <span className="font-heading text-sm font-semibold text-primary uppercase tracking-widest">Administration</span>
          <h1 className="font-heading text-3xl md:text-4xl font-bold text-on-surface mt-1">Dashboard</h1>
        </div>

        {/* Bento KPI Grid */}
        <div className="bento-grid">
          <div className="col-span-12 md:col-span-4 glass-card p-8 rounded-3xl flex flex-col justify-between overflow-hidden relative group">
            <div className="z-10">
              <p className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">Total Students</p>
              <h2 className="font-heading text-4xl font-bold text-primary">{students.length}</h2>
              <div className="flex items-center gap-1.5 text-on-tertiary-fixed-variant mt-3">
                <span className="material-symbols-outlined text-[18px]">school</span>
                <span className="text-xs font-medium">Active learners</span>
              </div>
            </div>
            <div className="absolute -right-8 -bottom-8 opacity-10 group-hover:opacity-20 transition-opacity">
              <span className="material-symbols-outlined text-[160px]" style={{fontVariationSettings: "'FILL' 1"}}>groups</span>
            </div>
          </div>
          <div className="col-span-12 md:col-span-4 glass-card p-8 rounded-3xl flex flex-col justify-between overflow-hidden relative group">
            <div className="z-10">
              <p className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">Total Teachers</p>
              <h2 className="font-heading text-4xl font-bold text-primary">{teachers.length}</h2>
              <div className="flex items-center gap-1.5 text-on-tertiary-fixed-variant mt-3">
                <span className="material-symbols-outlined text-[18px]">person</span>
                <span className="text-xs font-medium">Educators on platform</span>
              </div>
            </div>
            <div className="absolute -right-8 -bottom-8 opacity-10 group-hover:opacity-20 transition-opacity">
              <span className="material-symbols-outlined text-[160px]" style={{fontVariationSettings: "'FILL' 1"}}>school</span>
            </div>
          </div>
          <div className="col-span-12 md:col-span-4 glass-card p-8 rounded-3xl flex flex-col justify-between overflow-hidden relative group bg-primary-container/10 border-primary/20">
            <div className="z-10">
              <div className="flex justify-between items-start">
                <p className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">System Admins</p>
                <span className="flex h-3 w-3 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-on-tertiary-fixed-variant opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-tertiary-fixed-dim"></span>
                </span>
              </div>
              <h2 className="font-heading text-4xl font-bold text-primary">{admins.length}</h2>
            </div>
          </div>
        </div>

        {/* Grid: Form + Roster */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Create User Form */}
          <section className="lg:col-span-4 space-y-6">
            <div className="glass-card p-8 rounded-3xl flex flex-col gap-5">
              <header>
                <span className="font-heading text-xs font-semibold text-primary uppercase tracking-widest block mb-1">Administration</span>
                <h3 className="font-heading text-xl font-semibold text-on-surface">Create New User</h3>
                <p className="text-xs text-on-surface-variant font-body mt-1">
                  A temporary password is generated automatically and shown once you create the account.
                </p>
              </header>
              <form onSubmit={handleCreate} className="space-y-4">
                <div className="space-y-1.5">
                  <label className="font-heading text-xs font-semibold text-on-surface-variant" id="role-label">Select User Role</label>
                  <div className="grid grid-cols-2 gap-2" role="group" aria-labelledby="role-label">
                    <button type="button" onClick={() => setRole("teacher")}
                      aria-pressed={role === "teacher"}
                      className={`border rounded-xl py-2.5 flex flex-col items-center gap-1 transition-all active:scale-95 ${role === "teacher" ? "border-primary bg-primary/5" : "border-outline-variant/30 hover:border-primary"}`}>
                      <span className={`material-symbols-outlined ${role === "teacher" ? "text-primary" : "text-on-surface-variant"}`}>person</span>
                      <span className={`text-xs font-medium ${role === "teacher" ? "text-primary" : ""}`}>Teacher</span>
                    </button>
                    <button type="button" onClick={() => setRole("student")}
                      aria-pressed={role === "student"}
                      className={`border rounded-xl py-2.5 flex flex-col items-center gap-1 transition-all active:scale-95 ${role === "student" ? "border-primary bg-primary/5" : "border-outline-variant/30 hover:border-primary"}`}>
                      <span className={`material-symbols-outlined ${role === "student" ? "text-primary" : "text-on-surface-variant"}`}>school</span>
                      <span className={`text-xs font-medium ${role === "student" ? "text-primary" : ""}`}>Student</span>
                    </button>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label className="font-heading text-xs font-semibold text-on-surface-variant" htmlFor="new-display-name">Display Name</label>
                  <input id="new-display-name" type="text" required maxLength={80} placeholder="Jamie Rivera" value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-4 py-2.5 focus:ring-2 focus:ring-primary focus:border-primary outline-none transition-all" />
                </div>
                <div className="space-y-1.5">
                  <label className="font-heading text-xs font-semibold text-on-surface-variant" htmlFor="new-username">Username</label>
                  <input id="new-username" type="text" required pattern="[a-z0-9._-]{3,32}" placeholder="jamie.r" value={username}
                    aria-describedby="new-username-help"
                    onChange={(e) => setUsername(e.target.value)}
                    className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-4 py-2.5 focus:ring-2 focus:ring-primary focus:border-primary outline-none transition-all" />
                  <p id="new-username-help" className="text-xs text-on-surface-variant">
                    Lowercase letters, numbers, dots, underscores or hyphens, 3–32 characters.
                  </p>
                </div>
                {role === "student" && (
                  <>
                    <div className="space-y-1.5">
                      <label className="font-heading text-xs font-semibold text-on-surface-variant" htmlFor="new-grade">Grade Level</label>
                      <select id="new-grade" value={gradeLevel} onChange={(e) => setGradeLevel(e.target.value)}
                        className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-4 py-2.5 focus:ring-2 focus:ring-primary focus:border-primary outline-none transition-all">
                        <option value="">Select grade...</option>
                        {["1","2","3","4","5","6","7","8"].map((g) => (
                          <option key={g} value={g}>Grade {g}</option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-1.5 pt-3 border-t border-outline-variant/30">
                      <label className="font-heading text-xs font-semibold text-on-surface-variant" htmlFor="new-teacher">
                        Assign Teacher <span aria-hidden="true">*</span>
                      </label>
                      <select id="new-teacher" required value={teacherId} onChange={(e) => setTeacherId(e.target.value)}
                        aria-describedby="new-teacher-help"
                        className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-4 py-2.5 focus:ring-2 focus:ring-primary focus:border-primary outline-none transition-all">
                        <option value="">Select a teacher...</option>
                        {activeTeachers.map((t) => (
                          <option key={t.uid} value={t.uid}>{t.email}</option>
                        ))}
                      </select>
                      <p id="new-teacher-help" className="text-xs text-on-surface-variant italic">
                        Required — students must be assigned to an active teacher.
                      </p>
                      {activeTeachers.length === 0 && (
                        <p className="text-xs text-error">No active teachers yet — create a teacher account first.</p>
                      )}
                    </div>
                  </>
                )}
                <button type="submit" disabled={creating || teacherRequiredAndMissing}
                  className="w-full bg-primary-container text-white font-heading text-sm font-semibold py-3 rounded-xl hover:bg-primary transition-colors active:scale-[0.98] shadow-lg shadow-primary/20 disabled:opacity-60 disabled:cursor-not-allowed">
                  {creating ? "Creating..." : "Create Account"}
                </button>
              </form>
              {message && (
                <p role="alert" className="text-sm font-medium text-error">
                  {message}
                </p>
              )}
            </div>
          </section>

          {/* User Roster */}
          <section className="lg:col-span-8">
            <div className="glass-card p-8 rounded-3xl h-full flex flex-col">
              <header className="flex justify-between items-center mb-6">
                <h3 className="font-heading text-xl font-semibold text-on-surface">User Roster</h3>
              </header>
              {loading ? (
                <p className="text-on-surface-variant text-center py-8" role="status">Loading...</p>
              ) : (
                <div className="space-y-3 overflow-y-auto max-h-[720px] pr-2">
                  {users.map((u) => (
                    <div key={u.uid} className={`p-4 rounded-xl bg-surface-container-low border transition-all group ${u.status === "disabled" ? "border-error/30 opacity-70" : "border-outline-variant/10 hover:border-primary/20"}`}>
                      <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div className="flex items-center gap-4 min-w-0">
                          <div className={`w-12 h-12 shrink-0 rounded-full flex items-center justify-center ${u.role === "admin" ? "bg-tertiary/10" : u.role === "teacher" ? "bg-primary-fixed" : "bg-surface-variant"}`}>
                            <span className={`material-symbols-outlined ${u.role === "admin" ? "text-tertiary" : "text-primary"}`}>{roleIcon(u.role)}</span>
                          </div>
                          <div className="min-w-0">
                            <p className="font-heading text-sm font-semibold text-on-surface truncate">{u.email}</p>
                            <p className="text-xs text-on-surface-variant">
                              {u.grade_level ? `Grade ${u.grade_level}` : ""}
                              {u.teacher_id ? ` · ${teacherEmailMap[u.teacher_id] || "Assigned"}` : ""}
                              {!u.grade_level && !u.teacher_id ? "—" : ""}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {u.status === "disabled" && (
                            <span className="px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider bg-error-container text-on-error-container">
                              Disabled
                            </span>
                          )}
                          <span className={`px-3 py-1 rounded-full text-[11px] font-bold uppercase tracking-wider ${roleBadge(u.role)}`}>
                            {u.role}
                          </span>
                        </div>
                      </div>

                      {u.role !== "admin" && (
                        <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-outline-variant/20">
                          {u.role === "student" && (
                            <button type="button" onClick={() => startReassign(u)} disabled={busyUid === u.uid}
                              className="text-xs font-heading font-semibold px-3 py-1.5 rounded-full bg-primary/10 text-primary hover:bg-primary hover:text-white transition-all disabled:opacity-50">
                              Reassign teacher
                            </button>
                          )}
                          <button type="button" onClick={() => handleResetPassword(u)} disabled={busyUid === u.uid}
                            className="text-xs font-heading font-semibold px-3 py-1.5 rounded-full bg-surface-variant/40 text-on-surface hover:bg-surface-variant transition-all disabled:opacity-50">
                            {busyUid === u.uid ? "Working…" : "Reset password"}
                          </button>
                          <button type="button" onClick={() => handleToggleDisabled(u)} disabled={busyUid === u.uid}
                            className={`text-xs font-heading font-semibold px-3 py-1.5 rounded-full transition-all disabled:opacity-50 ${
                              u.status === "disabled"
                                ? "bg-tertiary-fixed/40 text-on-tertiary-fixed-variant hover:bg-tertiary-fixed"
                                : "bg-error-container/50 text-on-error-container hover:bg-error-container"
                            }`}>
                            {u.status === "disabled" ? "Enable account" : "Disable account"}
                          </button>
                        </div>
                      )}

                      {reassigningUid === u.uid && (
                        <div className="mt-3 pt-3 border-t border-outline-variant/20 flex flex-wrap items-center gap-2">
                          <label className="sr-only" htmlFor={`reassign-${u.uid}`}>New teacher for {u.email}</label>
                          <select id={`reassign-${u.uid}`} value={reassignTeacherId}
                            onChange={(e) => setReassignTeacherId(e.target.value)}
                            className="flex-1 min-w-[180px] bg-surface-container-low border border-outline-variant rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-primary outline-none">
                            <option value="">Select a teacher...</option>
                            {activeTeachers.map((t) => (
                              <option key={t.uid} value={t.uid}>{t.email}</option>
                            ))}
                          </select>
                          <button type="button" onClick={() => confirmReassign(u)}
                            disabled={!reassignTeacherId || busyUid === u.uid}
                            className="text-xs font-heading font-semibold px-3 py-2 rounded-xl bg-primary text-white disabled:opacity-50">
                            Save
                          </button>
                          <button type="button" onClick={cancelReassign}
                            className="text-xs font-heading font-semibold px-3 py-2 rounded-xl border border-outline-variant text-on-surface-variant">
                            Cancel
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>

      {credential && <CredentialSheet credential={credential} onClose={() => setCredential(null)} />}

      {/* Atmospheric background */}
      <div className="fixed top-0 left-0 w-full h-full pointer-events-none -z-10 overflow-hidden">
        <div className="absolute top-[-10%] right-[-5%] w-[40%] h-[60%] bg-primary/5 rounded-full blur-[120px] motion-safe:animate-pulse"></div>
        <div className="absolute bottom-[-10%] left-[-5%] w-[30%] h-[50%] bg-surface-variant/40 rounded-full blur-[120px]"></div>
      </div>
    </div>
  );
};

export default AdminDashboardPage;
