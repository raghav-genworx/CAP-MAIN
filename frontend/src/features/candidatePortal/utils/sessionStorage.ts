import type { CandidateSubmitResponse } from "../types/CandidatePortal";

const SESSION_KEY = "cap_candidate_session_token";
const SUBMISSION_KEY = "cap_candidate_submission_result";

export interface CandidateSubmissionReceipt extends CandidateSubmitResponse {
  auto?: boolean;
}

export function saveCandidateSessionToken(token: string) {
  sessionStorage.setItem(SESSION_KEY, token);
}

export function readCandidateSessionToken() {
  return sessionStorage.getItem(SESSION_KEY);
}

export function clearCandidateSessionToken() {
  sessionStorage.removeItem(SESSION_KEY);
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

function isSubmissionReceipt(value: unknown): value is CandidateSubmissionReceipt {
  if (!value || typeof value !== "object") {
    return false;
  }
  const receipt = value as Record<string, unknown>;
  return (
    typeof receipt.candidate_assessment_id === "string" &&
    (receipt.status === "submitted" || receipt.status === "auto_submitted") &&
    typeof receipt.submitted_at === "string" &&
    typeof receipt.pending_evaluation === "boolean"
  );
}
