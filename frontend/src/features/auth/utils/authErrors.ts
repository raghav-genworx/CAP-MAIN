import { FirebaseError } from "firebase/app";

const AUTH_ERROR_MESSAGES: Record<string, string> = {
  "auth/account-exists-with-different-credential":
    "An account already exists with this email using a different sign-in method.",
  "auth/email-already-in-use": "An account already exists with this email.",
  "auth/expired-action-code":
    "This verification link has expired. Request another verification email.",
  "auth/invalid-action-code":
    "This verification link is invalid or has already been used.",
  "auth/invalid-credential": "The email or password is incorrect.",
  "auth/internal-error":
    "Google sign-in could not complete. Check that Google is enabled in Firebase Authentication and that this domain is authorized.",
  "auth/operation-not-allowed":
    "This sign-in provider is not enabled in Firebase Authentication.",
  "auth/popup-blocked":
    "The browser blocked the sign-in popup. Allow popups and try again.",
  "auth/popup-closed-by-user":
    "The sign-in popup was closed before authentication finished.",
  "auth/unauthorized-domain":
    "This domain is not authorized in Firebase. Add localhost in Firebase Authentication settings.",
  "auth/weak-password": "Password should be at least 6 characters.",
};

export function getAuthErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof FirebaseError) {
    return AUTH_ERROR_MESSAGES[error.code] || error.message.replace("Firebase: ", "");
  }

  if (error instanceof Error) {
    return error.message.replace("Firebase: ", "");
  }

  return fallback;
}
