import { initializeApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  OAuthProvider,
  type Auth,
} from "firebase/auth";

import { env } from "../config/env";

const hasFirebaseConfig =
  env.firebaseApiKey &&
  env.firebaseAuthDomain &&
  env.firebaseProjectId &&
  env.firebaseAppId;

export const firebaseApp = hasFirebaseConfig
  ? initializeApp({
      apiKey: env.firebaseApiKey,
      authDomain: env.firebaseAuthDomain,
      projectId: env.firebaseProjectId,
      appId: env.firebaseAppId,
    })
  : null;

export const auth: Auth | null = firebaseApp ? getAuth(firebaseApp) : null;

export const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: "select_account" });

export const microsoftProvider = new OAuthProvider("microsoft.com");
microsoftProvider.setCustomParameters({ prompt: "select_account" });

export function assertFirebaseAuth(): Auth {
  if (!auth) {
    throw new Error(
      "Firebase is not configured. Add VITE_FIREBASE_API_KEY, VITE_FIREBASE_AUTH_DOMAIN, VITE_FIREBASE_PROJECT_ID, and VITE_FIREBASE_APP_ID to frontend/.env.",
    );
  }

  return auth;
}
