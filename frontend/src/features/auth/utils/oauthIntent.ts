export const OAUTH_INTENT_KEY = "cap_recruiter_oauth_intent";
const OAUTH_ERROR_KEY = "cap_recruiter_oauth_error";

export type OAuthIntent = "login" | "signup";

export function saveOAuthIntent(intent: OAuthIntent) {
  sessionStorage.setItem(OAUTH_INTENT_KEY, intent);
}

export function consumeOAuthIntent(): OAuthIntent | null {
  const intent = sessionStorage.getItem(OAUTH_INTENT_KEY);
  sessionStorage.removeItem(OAUTH_INTENT_KEY);
  return intent === "login" || intent === "signup" ? intent : null;
}

export function clearOAuthIntent() {
  sessionStorage.removeItem(OAUTH_INTENT_KEY);
}

export function saveOAuthError(message: string) {
  sessionStorage.setItem(OAUTH_ERROR_KEY, message);
}

export function consumeOAuthError(): string {
  const message = sessionStorage.getItem(OAUTH_ERROR_KEY) ?? "";
  sessionStorage.removeItem(OAUTH_ERROR_KEY);
  return message;
}
