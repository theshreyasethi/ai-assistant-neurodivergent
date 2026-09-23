import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import TeacherDashboardPage from './pages/TeacherDashboardPage';
import AdminDashboardPage from './pages/AdminDashboardPage';
import UploadPage from './pages/UploadPage';
import LearningPage from './pages/LearningPage';
import ContentPage from './pages/ContentPage';
import RoleGate from './components/RoleGate';
import QuizPage from './pages/QuizPage';
import SettingsPage from './pages/SettingsPage';
import Layout from './components/Layout';
import AccessibleNotification from './components/AccessibleNotification';

const App: React.FC = () => {
  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AccessibleNotification />
      <Layout>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          {/* Public self-registration is closed — accounts are admin-provisioned only
              (see docs/PROJECT_EXPLANATION.md and the patent-readiness audit, finding A03).
              Anyone hitting the old /register link lands safely on /login. */}
          <Route path="/register" element={<Navigate to="/login" replace />} />
          <Route path="/" element={<LoginPage />} />

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
          <Route
            path="/learning"
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

          {/* Unknown path -> login, rather than a blank screen. */}
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Layout>
    </Router>
  );
};

export default App;
