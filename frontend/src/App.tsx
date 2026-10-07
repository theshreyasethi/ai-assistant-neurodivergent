import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import TeacherDashboardPage from './pages/TeacherDashboardPage';
import AuditLogPage from './pages/AuditLogPage';
import AdminDashboardPage from './pages/AdminDashboardPage';
import UploadPage from './pages/UploadPage';
import LearningPage from './pages/LearningPage';
import ContentPage from './pages/ContentPage';
import RoleGate from './components/RoleGate';
import QuizPage from './pages/QuizPage';
import SettingsPage from './pages/SettingsPage';
import FirstLoginPage from './pages/FirstLoginPage';
import AccountPage from './pages/AccountPage';
import Layout from './components/Layout';
import AccessibleNotification from './components/AccessibleNotification';
import VoiceBootstrap from './components/VoiceBootstrap';
import VoiceNavigator from './components/VoiceNavigator';
import VisualAlert from './components/VisualAlert';

const App: React.FC = () => {
  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AccessibleNotification />
      {/* Non-audio channels (border pulse, badge) + the persistent caption
          log — additive to, not a replacement for, the toast above
          (roadmap P4-02). */}
      <VisualAlert />
      {/* Route-aware (useLocation), so one mount here covers every page,
          /login included — see VoiceBootstrap.tsx for why a second mount
          inside LoginPage would just duplicate the same listeners. */}
      <VoiceBootstrap />
      <VoiceNavigator />
      <Layout>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          {/* Public self-registration is closed — accounts are admin-provisioned only
              (see docs/PROJECT_EXPLANATION.md and the patent-readiness audit, finding A03).
              Anyone hitting the old /register link lands safely on /login. */}
          <Route path="/register" element={<Navigate to="/login" replace />} />
          <Route path="/" element={<LoginPage />} />

          {/* Forced first-login password change — the only route reachable
              while backend/auth.py's require_active_user() gate is blocking
              everything else with 403 PASSWORD_CHANGE_REQUIRED. Not wrapped
              in RoleGate: it is role-agnostic (any freshly admin-provisioned
              account lands here regardless of role) and RoleGate's own
              redirect logic is what sends the user here in the first place. */}
          <Route path="/first-login" element={<FirstLoginPage />} />

          {/* Self-service account page (P1-08) — role-agnostic, same reason
              /first-login isn't wrapped in RoleGate: every role (student,
              teacher, admin) reaches it from the same account menu entry. */}
          <Route path="/account" element={<AccountPage />} />

          {/* Admin */}
          <Route
            path="/admin-dashboard"
            element={
              <RoleGate expectedRole="admin">
                <AdminDashboardPage />
              </RoleGate>
            }
          />

          {/* Student */}
          <Route
            path="/student-dashboard"
            element={
              <RoleGate expectedRole="student">
                <DashboardPage />
              </RoleGate>
            }
          />
          <Route
            path="/upload"
            element={
              <RoleGate expectedRole="student">
                <UploadPage />
              </RoleGate>
            }
          />
          {/* :contentId is optional — resumable lessons (roadmap task P2-06):
              a fresh upload navigates here without one and LearningPage
              assigns + redirects to it; a refresh or revisit reads it back
              from localStorage via the param. */}
          <Route
            path="/learning/:contentId?"
            element={
              <RoleGate expectedRole="student">
                <LearningPage />
              </RoleGate>
            }
          />
          <Route
            path="/content"
            element={
              <RoleGate expectedRole="student">
                <ContentPage />
              </RoleGate>
            }
          />
          <Route
            path="/quiz"
            element={
              <RoleGate expectedRole="student">
                <QuizPage />
              </RoleGate>
            }
          />
          <Route
            path="/settings"
            element={
              <RoleGate expectedRole="student">
                <SettingsPage />
              </RoleGate>
            }
          />

          {/* Teacher */}
          <Route
            path="/teacher-dashboard"
            element={
              <RoleGate expectedRole="teacher">
                <TeacherDashboardPage />
              </RoleGate>
            }
          />
          <Route
            path="/audit-log"
            element={
              <RoleGate expectedRole="teacher">
                <AuditLogPage />
              </RoleGate>
            }
          />

          {/* Unknown path -> login, rather than a blank screen. */}
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Layout>
    </Router>
  );
};

export default App;
