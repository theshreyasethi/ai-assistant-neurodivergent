import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthState } from 'react-firebase-hooks/auth';
import { EmailAuthProvider, reauthenticateWithCredential, updatePassword } from 'firebase/auth';

import api from '../services/api';
import { auth } from '../services/firebase';
import { notify } from '../services/notify';

const MIN_PASSWORD_LENGTH = 10;

const FIELD =
  'w-full bg-surface-container-low border border-outline-variant rounded-xl px-4 py-3 text-on-surface ' +
  'focus:ring-2 focus:ring-primary focus:border-primary outline-none transition-all font-body';

interface MeProfile {
  uid: string;
  email: string | null;
  username: string | null;
  displayName: string | null;
  role: string | null;
}

function extractErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    if (typeof first?.msg === 'string') return first.msg.replace(/^Value error,\s*/, '');
  }
  return fallback;
}

const AccountPage: React.FC = () => {
  const [user, authLoading] = useAuthState(auth);
  const navigate = useNavigate();

  const [me, setMe] = React.useState<MeProfile | null>(null);
  const [loading, setLoading] = React.useState(true);

  const [displayName, setDisplayName] = React.useState('');
  const [username, setUsername] = React.useState('');
  const [profileSaving, setProfileSaving] = React.useState(false);
  const [profileError, setProfileError] = React.useState('');

  const [currentPassword, setCurrentPassword] = React.useState('');
  const [newPassword, setNewPassword] = React.useState('');
  const [confirmPassword, setConfirmPassword] = React.useState('');
  const [passwordSaving, setPasswordSaving] = React.useState(false);
  const [passwordError, setPasswordError] = React.useState('');

  React.useEffect(() => {
    if (!authLoading && !user) {
      navigate('/login', { replace: true });
    }
  }, [authLoading, user, navigate]);

  React.useEffect(() => {
    if (!user) return;
    let cancelled = false;
    api
      .get('/api/me')
      .then((res) => {
        if (cancelled) return;
        setMe(res.data);
        setDisplayName(res.data.displayName ?? '');
        setUsername(res.data.username ?? '');
      })
      .catch((err) => {
        console.error('[AccountPage] failed to load profile', err);
        notify('Could not load your account details.', { kind: 'error' });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError('');

    const patch: { displayName?: string; username?: string } = {};
    if (displayName.trim() && displayName.trim() !== me?.displayName) patch.displayName = displayName.trim();
    if (username.trim() && username.trim() !== me?.username) patch.username = username.trim().toLowerCase();
    if (Object.keys(patch).length === 0) {
      notify('Nothing to save.', { kind: 'info' });
      return;
    }

    setProfileSaving(true);
    try {
      const res = await api.patch('/api/me', patch);
      setMe((prev) => (prev ? { ...prev, ...res.data } : prev));
      if (res.data.username) setUsername(res.data.username);
      notify('Account details saved.', { kind: 'success' });
    } catch (err) {
      setProfileError(extractErrorMessage(err, 'Could not save your account details. Please try again.'));
    } finally {
      setProfileSaving(false);
    }
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError('');

    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setPasswordError(`Your new password needs to be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('The two passwords you entered do not match.');
      return;
    }
    if (!user?.email) {
      setPasswordError('Could not verify your account. Please sign in again.');
      return;
    }

    setPasswordSaving(true);
    try {
      // Firebase requires a RECENT sign-in before it allows a password
      // change — reauthenticateWithCredential + updatePassword is the
      // standard client-side pattern for that, and needs no backend route
      // at all (contrast the forced first-login change in
      // routers/auth_flow.py, which has different requirements — a
      // generated temp password, revoking every other session — and is
      // server-enforced for that reason).
      const credential = EmailAuthProvider.credential(user.email, currentPassword);
      await reauthenticateWithCredential(user, credential);
      await updatePassword(user, newPassword);
      notify('Password changed.', { kind: 'success' });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: any) {
      if (err?.code === 'auth/wrong-password' || err?.code === 'auth/invalid-credential') {
        setPasswordError('Your current password was not correct.');
      } else if (err?.code === 'auth/too-many-requests') {
        setPasswordError('Too many attempts. Please wait a moment and try again.');
      } else {
        setPasswordError('Could not change your password. Please try again.');
      }
    } finally {
      setPasswordSaving(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-[40vh] flex items-center justify-center" role="status">
        Loading your account…
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="text-center">
        <h1 className="font-heading text-2xl sm:text-3xl font-semibold text-on-surface flex items-center justify-center gap-2">
          <span className="material-symbols-outlined" aria-hidden="true">account_circle</span>
          Your Account
        </h1>
        <p className="text-on-surface-variant mt-1 font-body">
          Update your name, username, and password. Changes apply right away.
        </p>
      </div>

      {/* Read-only identity */}
      <section className="glass-card rounded-[2rem] p-6">
        <h2 className="text-xs font-heading font-semibold text-on-surface-variant uppercase tracking-wider mb-3">
          Signed in as
        </h2>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-on-surface-variant">Login email</dt>
            <dd className="font-body font-medium text-on-surface">{me?.email ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-on-surface-variant">Role</dt>
            <dd className="font-body font-medium text-on-surface capitalize">{me?.role ?? '—'}</dd>
          </div>
        </dl>
      </section>

      {/* Profile */}
      <section className="glass-card rounded-[2rem] p-6">
        <h2 className="text-xs font-heading font-semibold text-on-surface-variant uppercase tracking-wider mb-3">
          Display name &amp; username
        </h2>
        <form onSubmit={handleProfileSubmit} noValidate className="space-y-5">
          <div className="space-y-1.5">
            <label className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-wider" htmlFor="display-name">
              Display name
            </label>
            <input
              className={FIELD}
              id="display-name"
              type="text"
              maxLength={80}
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <label className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-wider" htmlFor="username">
              Username
            </label>
            <input
              className={FIELD}
              id="username"
              type="text"
              pattern="[a-z0-9._-]{3,32}"
              aria-describedby="username-help"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            <p id="username-help" className="text-xs text-on-surface-variant font-body">
              Lowercase letters, numbers, dots, underscores or hyphens, 3–32 characters. If you
              sign in with this username, changing it changes your login too.
            </p>
          </div>

          <button
            className="px-6 py-3 rounded-xl bg-primary-container text-white font-heading text-sm font-semibold hover:bg-primary transition-colors active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
            type="submit"
            disabled={profileSaving}
          >
            {profileSaving ? 'Saving…' : 'Save changes'}
          </button>

          <div role="alert" aria-live="assertive" className="min-h-[1.25rem]">
            {profileError && (
              <p className="p-3 rounded-xl bg-error-container text-on-error-container text-sm font-body">
                {profileError}
              </p>
            )}
          </div>
        </form>
      </section>

      {/* Password */}
      <section className="glass-card rounded-[2rem] p-6">
        <h2 className="text-xs font-heading font-semibold text-on-surface-variant uppercase tracking-wider mb-3">
          Change password
        </h2>
        <form onSubmit={handlePasswordSubmit} noValidate className="space-y-5">
          <div className="space-y-1.5">
            <label className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-wider" htmlFor="current-password">
              Current password
            </label>
            <input
              className={FIELD}
              id="current-password"
              type="password"
              autoComplete="current-password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <label className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-wider" htmlFor="account-new-password">
              New password
            </label>
            <input
              className={FIELD}
              id="account-new-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              aria-describedby="account-password-requirements"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
            <p id="account-password-requirements" className="text-xs text-on-surface-variant font-body">
              At least {MIN_PASSWORD_LENGTH} characters.
            </p>
          </div>

          <div className="space-y-1.5">
            <label className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-wider" htmlFor="account-confirm-password">
              Confirm new password
            </label>
            <input
              className={FIELD}
              id="account-confirm-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </div>

          <button
            className="px-6 py-3 rounded-xl bg-primary-container text-white font-heading text-sm font-semibold hover:bg-primary transition-colors active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
            type="submit"
            disabled={passwordSaving}
          >
            {passwordSaving ? 'Saving…' : 'Change password'}
          </button>

          <div role="alert" aria-live="assertive" className="min-h-[1.25rem]">
            {passwordError && (
              <p className="p-3 rounded-xl bg-error-container text-on-error-container text-sm font-body">
                {passwordError}
              </p>
            )}
          </div>
        </form>
      </section>

      {me?.role === 'student' && (
        <p className="text-center text-sm font-body">
          <Link to="/settings" className="font-heading font-semibold text-primary hover:text-primary-container">
            Looking for reading &amp; accessibility settings?
          </Link>
        </p>
      )}
    </div>
  );
};

export default AccountPage;
