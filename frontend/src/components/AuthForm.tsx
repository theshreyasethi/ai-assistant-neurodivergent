import React from 'react';
import { useSignInWithEmailAndPassword } from 'react-firebase-hooks/auth';
import { auth, db } from '../services/firebase';
import { useNavigate } from 'react-router-dom';
import { doc, getDoc } from 'firebase/firestore';

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

  const handleFillCredentials = (e: React.MouseEvent<HTMLButtonElement>, role: 'student' | 'teacher') => {
    e.preventDefault();
    if (role === 'student') {
      setEmail('student1@test.com');
      setPassword('student@123');
    } else {
      setEmail('teacher1@test.com');
      setPassword('teacher@123');
    }
  };

  React.useEffect(() => {
    if (!user) return;
    const redirect = async () => {
      try {
        const snap = await getDoc(doc(db, 'users', user.user.uid));
        const role = snap.exists() ? (snap.data()?.role || 'student') : 'student';
        if (role === 'admin') navigate('/admin-dashboard');
        else if (role === 'teacher') navigate('/teacher-dashboard');
        else navigate('/student-dashboard');
      } catch {
        navigate('/student-dashboard');
      }
    };
    redirect();
  }, [user, navigate]);

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="space-y-1.5">
        <label className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-wider" htmlFor="email">Email Address</label>
        <input
          className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-4 py-3 text-on-surface focus:ring-2 focus:ring-primary focus:border-primary outline-none transition-all font-body"
          id="email" type="email" placeholder="you@eduease.edu"
          value={email} onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <label className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-wider" htmlFor="password">Password</label>
        <div className="relative">
          <input
            className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-4 py-3 pr-11 text-on-surface focus:ring-2 focus:ring-primary focus:border-primary outline-none transition-all font-body"
            id="password" type={showPassword ? 'text' : 'password'} placeholder="Enter your password"
            value={password} onChange={(e) => setPassword(e.target.value)}
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
        className="w-full bg-primary-container text-white font-heading text-sm font-semibold py-3.5 rounded-xl hover:bg-primary transition-colors active:scale-[0.98] shadow-lg shadow-primary/20"
        type="submit"
        disabled={loading}
      >
        {loading ? 'Signing in...' : 'Sign In'}
      </button>
      {/* Demo Access */}
      <div className="relative flex items-center my-4">
        <div className="flex-grow border-t border-slate-200" />
        <span className="mx-3 text-xs text-slate-400 uppercase tracking-wider whitespace-nowrap">Or preview with Demo Access</span>
        <div className="flex-grow border-t border-slate-200" />
      </div>
      <div className="bg-slate-50 border border-slate-100 p-3 rounded-xl space-y-2">
        <div className="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-100 hover:border-indigo-200 transition-all shadow-sm">
          <div>
            <p className="text-xs font-semibold text-slate-700">Student</p>
            <p className="text-[11px] text-slate-400">student1@test.com</p>
          </div>
          <button
            className="text-xs text-indigo-600 font-medium bg-indigo-50 hover:bg-indigo-100 px-2.5 py-1.5 rounded-md transition-colors cursor-pointer"
            onClick={(e) => handleFillCredentials(e, 'student')}
          >
            Fill Credentials
          </button>
        </div>
        <div className="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-100 hover:border-indigo-200 transition-all shadow-sm">
          <div>
            <p className="text-xs font-semibold text-slate-700">Teacher</p>
            <p className="text-[11px] text-slate-400">teacher1@test.com</p>
          </div>
          <button
            className="text-xs text-indigo-600 font-medium bg-indigo-50 hover:bg-indigo-100 px-2.5 py-1.5 rounded-md transition-colors cursor-pointer"
            onClick={(e) => handleFillCredentials(e, 'teacher')}
          >
            Fill Credentials
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-error-container text-on-error-container text-xs font-body">
          {error.message}
        </div>
      )}
    </form>
  );
};

export default AuthForm;
