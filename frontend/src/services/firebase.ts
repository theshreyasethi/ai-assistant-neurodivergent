import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
  measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID,
};

// Patent-readiness audit finding A11: this used to console.log the full
// config, including the API key, on every page load in every environment
// (dev AND production) — logged to the browser console, so logged into
// crash-reporting tools, HAR exports, screen-share sessions, anything that
// captures devtools output. Never log config/secrets; the guard below only
// reports the ONE actionable fact a developer needs (the key is missing).
if (!firebaseConfig.apiKey) {
  console.error(
    "[Firebase] VITE_FIREBASE_API_KEY is undefined. " +
    "Ensure frontend/.env exists and the dev server was restarted after adding it."
  );
}

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db = getFirestore(app);
export default app;