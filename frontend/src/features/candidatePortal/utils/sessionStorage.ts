import type { CandidateSubmitResponse } from "../types/CandidatePortal";

const SESSION_KEY = "cap_candidate_session_token";
const INVITE_KEY = "cap_candidate_invite_token";
const SUBMISSION_KEY = "cap_candidate_submission_result";

/**
 * The stored receipt is the backend `CandidateSubmitResponse` plus a few
 * optional, locally captured display fields. They are read from the already
 * loaded assessment before the session token is cleared so the completion page
 * can name the assessment without a second request. The backend contract is
 * unchanged.
 */
export interface CandidateSubmissionReceipt extends CandidateSubmitResponse {
  auto?: boolean;
  candidate_name?: string;
  assessment_title?: string;
  slot_title?: string;
}

export function saveCandidateSessionToken(token: string) {
  localStorage.setItem(SESSION_KEY, token);
}

export function readCandidateSessionToken() {
  return localStorage.getItem(SESSION_KEY);
}

export function clearCandidateSessionToken() {
  localStorage.removeItem(SESSION_KEY);
}

export function saveCandidateInviteToken(token: string) {
  localStorage.setItem(INVITE_KEY, token);
}

export function readCandidateInviteToken() {
  return localStorage.getItem(INVITE_KEY);
}

export function clearSubmissionResult() {
  sessionStorage.removeItem(SUBMISSION_KEY);
}

export function saveSubmissionResult(payload: CandidateSubmissionReceipt) {
  sessionStorage.setItem(SUBMISSION_KEY, JSON.stringify(payload));
}

export function readSubmissionResult(): CandidateSubmissionReceipt | null {
  const stored = sessionStorage.getItem(SUBMISSION_KEY);
  if (!stored) {
    return null;
  }
  try {
    const value: unknown = JSON.parse(stored);
    if (!isSubmissionReceipt(value)) {
      sessionStorage.removeItem(SUBMISSION_KEY);
      return null;
    }
    return value;
  } catch {
    sessionStorage.removeItem(SUBMISSION_KEY);
    return null;
  }
}

function isOptionalString(value: unknown) {
  return value === undefined || typeof value === "string";
}

function isSubmissionReceipt(value: unknown): value is CandidateSubmissionReceipt {
  if (!value || typeof value !== "object") {
    return false;
  }
  const receipt = value as Record<string, unknown>;
  return (
    typeof receipt.candidate_assessment_id === "string" &&
    (receipt.status === "submitted" || receipt.status === "auto_submitted") &&
    typeof receipt.submitted_at === "string" &&
    typeof receipt.pending_evaluation === "boolean" &&
    isOptionalString(receipt.candidate_name) &&
    isOptionalString(receipt.assessment_title) &&
    isOptionalString(receipt.slot_title)
  );
}
