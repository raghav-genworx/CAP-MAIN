import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
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

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!auth) {
      setLoading(false);
      return undefined;
    }

    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setCurrentUser(user);
      setLoading(false);
    });

    return unsubscribe;
  }, []);

  const loginWithEmail = useCallback(async (email: string, password: string) => {
    await signInWithEmailAndPassword(assertFirebaseAuth(), email, password);
  }, []);

  const signupWithEmail = useCallback(async (email: string, password: string) => {
    await createUserWithEmailAndPassword(assertFirebaseAuth(), email, password);
  }, []);

  const signInWithGoogle = useCallback(async () => {
    await signInWithPopup(assertFirebaseAuth(), googleProvider);
  }, []);

  const signInWithMicrosoft = useCallback(async () => {
    await signInWithPopup(assertFirebaseAuth(), microsoftProvider);
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
