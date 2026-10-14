import { useCallback, useEffect, useState } from 'react';
import { useAuthState } from 'react-firebase-hooks/auth';
import { doc, getDoc, updateDoc } from 'firebase/firestore';

import { auth, db } from '../services/firebase';
import { applyPrefs, CONSENT_VERSION, Consent, DEFAULT_PREFS, DEFAULT_PROFILE, Prefs, Profile } from '../types/profile';

/** Single source of truth for the signed-in student's accessibility profile. */
export function useProfile() {
  const [user, authLoading] = useAuthState(auth);
  const [profile, setProfile] = useState<Profile>(DEFAULT_PROFILE);
  const [consent, setConsent] = useState<Consent | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [gradeLevel, setGradeLevel] = useState<string | null>(null);
  const [readingDifficulty, setReadingDifficulty] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      setProfile(DEFAULT_PROFILE);
      setConsent(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const snap = await getDoc(doc(db, 'users', user.uid));
        const data = snap.data();
        if (cancelled) return;
        // Merge against defaults: accounts created before this profile field
        // existed have no `profile` at all, and every screen must still work.
        const merged: Profile = {
          ...DEFAULT_PROFILE,
          ...(data?.profile ?? {}),
          prefs: { ...DEFAULT_PREFS, ...(data?.profile?.prefs ?? {}) },
        };
        setProfile(merged);
        setConsent((data?.consent as Consent | undefined) ?? null);
        setRole(data?.role ?? 'student');
        setGradeLevel(data?.grade_level ?? null);
        setReadingDifficulty(data?.reading_difficulty ?? null);
        applyPrefs(merged.prefs);
      } catch (err) {
        console.error('[useProfile] load failed, using defaults', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [user, authLoading]);

  const savePrefs = useCallback(
    async (patch: Partial<Prefs>) => {
      const next = { ...profile, prefs: { ...profile.prefs, ...patch } };
      setProfile(next);
      applyPrefs(next.prefs);
      if (user) await updateDoc(doc(db, 'users', user.uid), { 'profile.prefs': next.prefs });
    },
    [profile, user],
  );

  const saveProfile = useCallback(
    async (patch: Partial<Profile>) => {
      const next = { ...profile, ...patch };
      setProfile(next);
      if (user) await updateDoc(doc(db, 'users', user.uid), { profile: next });
    },
    [profile, user],
  );

  /** No dedicated consent-flow screen exists yet — granting a specific
   * consent (e.g. webcam, alongside the "Camera focus check" toggle in
   * SettingsPage) is the only way `consent.*` is ever written. Merges onto
   * whatever consent already exists so granting one flag never silently
   * resets the others, and always stamps the current CONSENT_VERSION. */
  const saveConsent = useCallback(
    async (patch: Partial<Consent>) => {
      const next: Consent = {
        dataCollection: consent?.dataCollection ?? false,
        webcam: consent?.webcam ?? false,
        disabilityDisclosure: consent?.disabilityDisclosure ?? false,
        version: CONSENT_VERSION,
        ...patch,
      };
      setConsent(next);
      if (user) await updateDoc(doc(db, 'users', user.uid), { consent: next });
    },
    [consent, user],
  );

  return {
    user,
    uid: user?.uid ?? null,
    role,
    gradeLevel,
    readingDifficulty,
    profile,
    consent,
    loading: loading || authLoading,
    savePrefs,
    saveProfile,
    saveConsent,
  };
}
