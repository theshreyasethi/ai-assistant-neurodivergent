import axios from 'axios';
import { signOut } from 'firebase/auth';
import { auth } from './firebase';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});

// Resolves once Firebase has determined the initial auth state (session restored or empty).
// Without this, auth.currentUser is null on the first request after a page load,
// causing a 401 even when the user is logged in.
const authReady = new Promise<void>((resolve) => {
  const unsub = auth.onAuthStateChanged(() => {
    unsub();
    resolve();
  });
});

api.interceptors.request.use(async (config) => {
  await authReady;
  const token = await auth.currentUser?.getIdToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Every account backend/services/accounts.py provisions gets
// mustChangePassword=True; backend/auth.py's require_active_user() gate
// enforces it on every route except POST /api/auth/first-login-password
// itself, returning 403 {code:"PASSWORD_CHANGE_REQUIRED"}. RoleGate.tsx
// already redirects to /first-login right after reading the profile (the
// fast path), but that read can race a freshly-created session or simply
// not run on every screen — this interceptor is the backstop: whichever
// API call hits the gate first sends the user to /first-login, no matter
// which page they were on. A disabled account (backend detail
// "ACCOUNT_DISABLED") is signed out and sent back to /login instead, since
// there is nothing for them to fix on their own.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error?.response?.data?.detail;
    if (detail?.code === 'PASSWORD_CHANGE_REQUIRED') {
      if (window.location.pathname !== '/first-login') {
        window.location.assign('/first-login');
      }
    } else if (detail === 'ACCOUNT_DISABLED') {
      if (window.location.pathname !== '/login') {
        void signOut(auth).finally(() => window.location.assign('/login'));
      }
    }
    return Promise.reject(error);
  },
);

export default api;
