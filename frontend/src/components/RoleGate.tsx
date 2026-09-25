import { useAuthState } from 'react-firebase-hooks/auth';
import { auth, db } from '../services/firebase';
import { useNavigate } from 'react-router-dom';
import { doc, getDoc } from 'firebase/firestore';
import React from 'react';

export default function RoleGate({ children, expectedRole }: { children: React.ReactNode, expectedRole: string }) {
  const [user, loading] = useAuthState(auth);
  const [userRole, setUserRole] = React.useState<string | null>(null);
  const [roleLoading, setRoleLoading] = React.useState(true);
  const navigate = useNavigate();

  React.useEffect(() => {
    if (loading) return; // Wait until auth state is determined

    if (!user) {
      navigate('/login');
      setRoleLoading(false);
      return;
    }

    const fetchUserRole = async () => {
      try {
        const docRef = doc(db, 'users', user.uid);
        const docSnap = await getDoc(docRef);
        const data = docSnap.data();
        const fetchedRole = docSnap.exists() ? (data?.role || 'student') : 'student';

        // Fast path: redirect to the forced password-change screen before
        // any dashboard content renders or any protected API call is made,
        // rather than waiting for the first API call to 403 with
        // PASSWORD_CHANGE_REQUIRED (services/api.ts's response interceptor
        // is the backstop for that, not the primary route here).
        if (docSnap.exists() && data?.mustChangePassword) {
          navigate('/first-login');
          setRoleLoading(false);
          return;
        }

        setUserRole(fetchedRole);

        // Only redirect if the fetched role doesn't match what this route expects
        if (fetchedRole !== expectedRole) {
          if (fetchedRole === 'admin') {
            navigate('/admin-dashboard');
          } else if (fetchedRole === 'teacher') {
            navigate('/teacher-dashboard');
          } else {
            navigate('/student-dashboard');
          }
        }
      } catch (err) {
        console.error('Error fetching user role:', err);
        // Default to student on error
        setUserRole('student');
      } finally {
        setRoleLoading(false);
      }
    };

    fetchUserRole();
  }, [user, loading, expectedRole]);

  if (loading || roleLoading) {
    return <div role="status">Loading...</div>;
  }

  if (user && userRole === expectedRole) {
    return <>{children}</>;
  }

  return null;
}
