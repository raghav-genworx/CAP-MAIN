import {
  createUserWithEmailAndPassword,
  getRedirectResult,
  onAuthStateChanged,
  sendEmailVerification,
  signInWithEmailAndPassword,
  signInWithPopup,
  signInWithRedirect,
  signOut,
  type AuthProvider as FirebaseAuthProvider,
  type User,
} from "firebase/auth";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  assertFirebaseAuth,
  auth,
  googleProvider,
  microsoftProvider,
} from "../../../lib/firebase";
import { AuthContext } from "./authContextValue";
import {
  clearOAuthIntent,
  saveOAuthError,
} from "../utils/oauthIntent";
import { getAuthErrorMessage } from "../utils/authErrors";

interface AuthProviderProps {
  children: ReactNode;
}

const REDIRECT_FALLBACK_CODES = new Set([
  "auth/cancelled-popup-request",
  "auth/internal-error",
  "auth/popup-blocked",
]);

function shouldFallbackToRedirect(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string" &&
    REDIRECT_FALLBACK_CODES.has(error.code)
  );
}

async function signInWithProvider(provider: FirebaseAuthProvider) {
  const firebaseAuth = assertFirebaseAuth();

  try {
    await signInWithPopup(firebaseAuth, provider);
  } catch (error) {
    if (shouldFallbackToRedirect(error)) {
      await signInWithRedirect(firebaseAuth, provider);
      return;
    }

    throw error;
  }
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const firebaseAuth = auth;
    if (!firebaseAuth) {
      setLoading(false);
      return undefined;
    }
    const configuredAuth = firebaseAuth;

    let unsubscribe: () => void = () => undefined;
    let active = true;

    async function initializeAuth() {
      try {
        await getRedirectResult(configuredAuth);
      } catch (error) {
        clearOAuthIntent();
        saveOAuthError(
          getAuthErrorMessage(error, "Unable to complete provider sign-in."),
        );
      } finally {
        if (active) {
          unsubscribe = onAuthStateChanged(configuredAuth, (user) => {
            setCurrentUser(user);
            setLoading(false);
          });
        }
      }
    }

    void initializeAuth();

    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  const loginWithEmail = useCallback(async (email: string, password: string) => {
    const firebaseAuth = assertFirebaseAuth();
    const credential = await signInWithEmailAndPassword(
      firebaseAuth,
      email,
      password,
    );
    if (!credential.user.emailVerified) {
      await signOut(firebaseAuth);
      throw new Error(
        "Your email is not verified. Open the Firebase verification link sent to your inbox before logging in.",
      );
    }
  }, []);

  const signupWithEmail = useCallback(async (email: string, password: string) => {
    const firebaseAuth = assertFirebaseAuth();
    const credential = await createUserWithEmailAndPassword(
      firebaseAuth,
      email,
      password,
    );
    try {
      await sendEmailVerification(credential.user, {
        url: `${window.location.origin}/recruiter/login`,
        handleCodeInApp: false,
      });
    } finally {
      await signOut(firebaseAuth);
    }
  }, []);

  const signInWithGoogle = useCallback(async () => {
    await signInWithProvider(googleProvider);
  }, []);

  const signInWithMicrosoft = useCallback(async () => {
    await signInWithProvider(microsoftProvider);
  }, []);

  const logout = useCallback(async () => {
    await signOut(assertFirebaseAuth());
  }, []);

  const value = useMemo(
    () => ({
      currentUser,
      loading,
      loginWithEmail,
      signupWithEmail,
      signInWithGoogle,
      signInWithMicrosoft,
      logout,
    }),
    [
      currentUser,
      loading,
      loginWithEmail,
      logout,
      signInWithGoogle,
      signInWithMicrosoft,
      signupWithEmail,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
