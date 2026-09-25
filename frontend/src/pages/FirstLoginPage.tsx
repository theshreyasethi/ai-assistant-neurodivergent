import React from 'react';
import { useNavigate } from 'react-router-dom';
import { signOut } from 'firebase/auth';
import { useAuthState } from 'react-firebase-hooks/auth';

import api from '../services/api';
import { auth } from '../services/firebase';
import { notify } from '../services/notify';

const MIN_LENGTH = 10;
const MAX_LENGTH = 128;

const FIELD =
  'w-full bg-surface-container-low border border-outline-variant rounded-xl px-4 py-3 text-on-surface ' +
  'focus:ring-2 focus:ring-primary focus:border-primary outline-none transition-all font-body';

/** FastAPI returns either a plain string detail (our own HTTPException calls)
 * or, for a Pydantic field_validator rejection (routers/auth_flow.py's
 * "too easy to guess" / "too predictable" checks), a 422 with
 * detail: [{ msg: "Value error, ...", ... }]. Handle both shapes rather
 * than showing the user "[object Object]". */
function extractErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    if (typeof first?.msg === 'string') {
      // Pydantic prefixes custom field_validator messages with "Value error, ".
      return first.msg.replace(/^Value error,\s*/, '');
    }
  }
  return fallback;
}

const FirstLoginPage: React.FC = () => {
  const [user, authLoading] = useAuthState(auth);
  const navigate = useNavigate();

  const [newPassword, setNewPassword] = React.useState('');
  const [confirmPassword, setConfirmPassword] = React.useState('');
  const [showPasswords, setShowPasswords] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState('');

  React.useEffect(() => {
    if (!authLoading && !user) {
      navigate('/login', { replace: true });
    }
  }, [authLoading, user, navigate]);

  const clientError = (): string | null => {
    if (newPassword.length < MIN_LENGTH) {
      return `Your new password needs to be at least ${MIN_LENGTH} characters.`;
    }
    if (newPassword.length > MAX_LENGTH) {
      return `Your new password can be at most ${MAX_LENGTH} characters.`;
    }
    if (newPassword !== confirmPassword) {
      return 'The two passwords you entered do not match.';
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const localIssue = clientError();
    if (localIssue) {
      setError(localIssue);
      return;
    }

    setSubmitting(true);
    try {
      await api.post('/api/auth/first-login-password', { newPassword });
      notify('Password changed. Please sign in again with your new password.', { kind: 'success' });
      await signOut(auth);
      navigate('/login', { replace: true });
    } catch (err) {
      setError(extractErrorMessage(err, 'Could not change your password. Please try again.'));
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center" role="status">
        Loading…
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12 bg-surface-bright">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="font-heading text-3xl font-bold text-primary mb-1">EduEase</h1>
          <p className="text-sm text-on-surface-variant font-body">Choose your own password</p>
        </div>

        <div className="glass-card rounded-3xl p-8 md:p-10">
          <h2 className="font-heading text-2xl font-bold text-on-surface mb-2">Set a new password</h2>
          <p id="first-login-help" className="text-sm text-on-surface-variant mb-6 font-body">
            You signed in with a temporary password. Before you can continue, choose a
            password only you know — at least {MIN_LENGTH} characters. A short phrase of a
            few ordinary words is easy to remember and hard to guess.
          </p>

          <form onSubmit={handleSubmit} noValidate className="space-y-5">
            <div className="space-y-1.5">
              <label
                className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-wider"
                htmlFor="new-password"
              >
                New password
              </label>
              <div className="relative">
                <input
                  className={FIELD + ' pr-11'}
                  id="new-password"
                  name="newPassword"
                  type={showPasswords ? 'text' : 'password'}
                  autoComplete="new-password"
                  required
                  minLength={MIN_LENGTH}
                  maxLength={MAX_LENGTH}
                  aria-describedby="first-login-help password-requirements"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
              <p id="password-requirements" className="text-xs text-on-surface-variant font-body">
                {MIN_LENGTH}–{MAX_LENGTH} characters. Avoid common or obvious passwords.
              </p>
            </div>

            <div className="space-y-1.5">
              <label
                className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-wider"
                htmlFor="confirm-password"
              >
                Type it again to confirm
              </label>
              <input
                className={FIELD}
                id="confirm-password"
                name="confirmPassword"
                type={showPasswords ? 'text' : 'password'}
                autoComplete="new-password"
                required
                minLength={MIN_LENGTH}
                maxLength={MAX_LENGTH}
                aria-describedby="confirm-help"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
              <p id="confirm-help" className="sr-only">
                Must match the new password above exactly.
              </p>
            </div>

            <label className="flex items-center gap-2 text-sm text-on-surface-variant font-body cursor-pointer">
              <input
                type="checkbox"
                className="h-4 w-4 accent-primary"
                checked={showPasswords}
                onChange={(e) => setShowPasswords(e.target.checked)}
              />
              Show passwords
            </label>

            <button
              className="w-full bg-primary-container text-white font-heading text-sm font-semibold py-3.5 rounded-xl hover:bg-primary transition-colors active:scale-[0.98] shadow-lg shadow-primary/20 disabled:opacity-60 disabled:cursor-not-allowed"
              type="submit"
              disabled={submitting}
            >
              {submitting ? 'Saving…' : 'Save new password'}
            </button>

            {/* Announced to screen readers the moment an error appears, without
                needing focus to move there first. */}
            <div role="alert" aria-live="assertive" className="min-h-[1.25rem]">
              {error && (
                <p className="p-3 rounded-xl bg-error-container text-on-error-container text-sm font-body">
                  {error}
                </p>
              )}
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default FirstLoginPage;
