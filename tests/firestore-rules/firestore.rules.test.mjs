// Firestore Security Rules test — proves (not just asserts) that the two things
// P5-07 items 4/5 asked for actually hold: a signed-in client cannot write its
// own `role`/`teacherId`/`status`, and self-registration (creating a `users/{uid}`
// document from the client) is closed.
//
// Deliberately isolated from frontend/ (see package.json here) so this test's
// pinned dependency versions never touch the shipped app's dependency tree.
// Run with the Firestore emulator active, e.g.:
//   npx firebase-tools@13 emulators:exec --only firestore --project demo-eduease \
//     "node tests/firestore-rules/firestore.rules.test.mjs"

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  initializeTestEnvironment,
  assertFails,
  assertSucceeds,
} from '@firebase/rules-unit-testing';
import { doc, getDoc, setDoc, updateDoc } from 'firebase/firestore';

const PROJECT_ID = 'demo-eduease';

async function main() {
  const testEnv = await initializeTestEnvironment({
    projectId: PROJECT_ID,
    firestore: {
      rules: readFileSync('../../firestore.rules', 'utf8'),
      host: '127.0.0.1',
      port: 8080,
    },
  });

  let passed = 0;
  const check = async (name, fn) => {
    await fn();
    passed += 1;
    console.log('  PASS  ' + name);
  };

  try {
    // Seed two student docs and a teacher doc with the Admin SDK context,
    // which bypasses rules entirely — exactly like the real backend does.
    await testEnv.withSecurityRulesDisabled(async (adminCtx) => {
      const db = adminCtx.firestore();
      await setDoc(doc(db, 'users', 'student-a'), {
        email: 'a@test.com', role: 'student', teacherId: 'teacher-1',
        profile: { disabilities: [], primary: null, severity: null, prefs: {} },
      });
      await setDoc(doc(db, 'users', 'student-b'), {
        email: 'b@test.com', role: 'student', teacherId: 'teacher-2',
        profile: { disabilities: [], primary: null, severity: null, prefs: {} },
      });
      await setDoc(doc(db, 'users', 'teacher-1'), { email: 't1@test.com', role: 'teacher' });
    });

    const asStudentA = testEnv.authenticatedContext('student-a').firestore();
    const anon = testEnv.unauthenticatedContext().firestore();

    await check('unauthenticated client cannot read a user profile', async () => {
      await assertFails(getDoc(doc(anon, 'users', 'student-a')));
    });

    await check('a student can read their own profile', async () => {
      await assertSucceeds(getDoc(doc(asStudentA, 'users', 'student-a')));
    });

    await check('a student cannot read a classmate mapped to a different teacher', async () => {
      await assertFails(getDoc(doc(asStudentA, 'users', 'student-b')));
    });

    await check('a student CAN update their own accessibility prefs', async () => {
      await assertSucceeds(
        updateDoc(doc(asStudentA, 'users', 'student-a'), { 'profile.prefs': { ttsEnabled: true } }),
      );
    });

    // The core assertion for this task: a signed-in client must not be able
    // to grant itself a higher role by writing its own users/{uid} document.
    await check('a student CANNOT escalate their own role to admin', async () => {
      await assertFails(updateDoc(doc(asStudentA, 'users', 'student-a'), { role: 'admin' }));
    });

    await check('a student CANNOT reassign their own teacherId', async () => {
      await assertFails(updateDoc(doc(asStudentA, 'users', 'student-a'), { teacherId: 'teacher-2' }));
    });

    await check('a student CANNOT set their own status (e.g. to bypass first-login)', async () => {
      await assertFails(updateDoc(doc(asStudentA, 'users', 'student-a'), { status: 'active' }));
    });

    // Self-registration: a client creating its own users/{uid} document — the
    // exact mechanism the old public /register + AuthForm setDoc() used.
    await check('self-registration (client-created user document) is closed', async () => {
      await assertFails(
        setDoc(doc(asStudentA, 'users', 'new-self-registered-uid'), { role: 'admin', email: 'x@test.com' }),
      );
    });

    await check('an unauthenticated client cannot self-register either', async () => {
      await assertFails(
        setDoc(doc(anon, 'users', 'new-self-registered-uid'), { role: 'admin', email: 'x@test.com' }),
      );
    });

    console.log(`\n${passed}/${passed} Firestore rules assertions passed.`);
  } finally {
    await testEnv.cleanup();
  }
}

main().catch((err) => {
  console.error('FAILED:', err);
  process.exit(1);
});
