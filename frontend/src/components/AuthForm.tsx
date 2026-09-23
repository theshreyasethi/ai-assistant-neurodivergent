import React from 'react';
import { useSignInWithEmailAndPassword } from 'react-firebase-hooks/auth';
import { doc, getDoc } from 'firebase/firestore';
import { useNavigate } from 'react-router-dom';

import { auth, db } from '../services/firebase';

// Sign-in only. Accounts are admin-provisioned (see backend /admin/create-user) —
// there is no client-side registration path, and this component must never grow
// one back in. See docs/PROJECT_EXPLANATION.md and the patent-readiness audit,
// finding A03, for why: a public /register that lets the browser choose its own
// role is exactly the hole a neurodivergent-learner platform can't afford.

const FIELD =
  'w-full bg-surface-container-low border border-outline-variant rounded-xl px-4 py-3 text-on-surface ' +
  'focus:ring-2 focus:ring-primary focus:border-primary outline-none transition-all font-body';

const AuthForm: React.FC = () => {
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [showPassword, setShowPassword] = React.useState(false);

  const [signInWithEmailAndPassword, user, loading, error] = useSignInWithEmailAndPassword(auth);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    signInWithEmailAndPassword(email, password);
  };

  React.useEffect(() => {
    if (!user) return;
    const redirect = async () => {
      try {
        const snap = await getDoc(doc(db, 'users', user.user.uid));
        const r = snap.exists() ? snap.data()?.role || 'student' : 'student';
        if (r === 'admin') navigate('/admin-dashboard');
        else if (r === 'teacher') navigate('/teacher-dashboard');
        else navigate('/student-dashboard');
      } catch {
        navigate('/student-dashboard');
      }
    };
    redirect();
  }, [user, navigate]);

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5">
      <div className="space-y-1.5">
        <label className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-wider" htmlFor="email">
          Email Address
        </label>
        <input
          className={FIELD}
          id="email"
          type="email"
          autoComplete="email"
          placeholder="you@eduease.edu"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <label className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-wider" htmlFor="password">
          Password
        </label>
        <div className="relative">
          <input
            className={FIELD + ' pr-11'}
            id="password"
            type={showPassword ? 'text' : 'password'}
            autoComplete="current-password"
            placeholder="Enter your password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button
            type="button"
            aria-label={showPassword ? 'Hide password' : 'Show password'}
            onClick={() => setShowPassword((prev) => !prev)}
            className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors"
          >
            <span className="material-symbols-outlined text-[16px] leading-none">
              {showPassword ? 'visibility_off' : 'visibility'}
            </span>
          </button>
        </div>
      </div>

      <button
        className="w-full bg-primary-container text-white font-heading text-sm font-semibold py-3.5 rounded-xl hover:bg-primary transition-colors active:scale-[0.98] shadow-lg shadow-primary/20 flex items-center justify-center gap-2"
        type="submit"
        disabled={loading}
      >
        <span className="material-symbols-outlined text-[18px]">login</span>
        {loading ? 'Signing in…' : 'Sign In'}
      </button>

      <p className="text-center text-xs text-on-surface-variant font-body">
        Don't have an account? Ask your teacher or school admin to set one up for you.
      </p>

      {error && (
        <div className="p-3 rounded-xl bg-error-container text-on-error-container text-xs font-body">
          {error.message}
        </div>
      )}
    </form>
  );
};

export default AuthForm;
