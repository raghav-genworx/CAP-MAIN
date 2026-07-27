import type { CandidateQuestion } from "../../types/CandidatePortal";

/**
 * One executed test case, normalised for display. Hidden-check cases only ever
 * carry the safe fields the backend exposes (index, status, timing, error
 * category) — never inputs, expected output, or actual output.
 */
export interface RunResultCase {
  index: number;
  passed: boolean;
  status: string;
  executionTime: string;
  errorType: string;
  input?: string;
  expectedOutput?: string;
  actualOutput?: string;
  stderr?: string;
  compileOutput?: string;
  checkerMessage?: string;
  memoryKb?: number | null;
}

export type RunResultKind = "sample" | "hidden";

export interface RunResultState {
  kind: RunResultKind;
  summary: string;
  cases: RunResultCase[];
  passedCount?: number;
  totalCount?: number;
}

/** Persistent, non-blocking autosave / connection state shown in the header. */
export type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; at: string | null }
  | { kind: "error"; message: string }
  | { kind: "conflict"; message: string };

export type QuestionProgressStatus =
  | "not_started"
  | "in_progress"
  | "submitted"
  | "passed"
  | "needs_attention";

export interface QuestionProgress {
  question: CandidateQuestion;
  status: QuestionProgressStatus;
  isAttempted: boolean;
  isSubmitted: boolean;
}

export const QUESTION_STATUS_LABEL: Record<QuestionProgressStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  submitted: "Submitted",
  passed: "Passed",
  needs_attention: "Needs attention",
};
