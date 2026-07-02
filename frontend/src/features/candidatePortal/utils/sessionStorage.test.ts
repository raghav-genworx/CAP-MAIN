import { beforeEach, describe, expect, it } from "vitest";

import {
  readSubmissionResult,
  saveSubmissionResult,
} from "./sessionStorage";

describe("candidate session storage", () => {
  beforeEach(() => sessionStorage.clear());

  it("round-trips a typed submission receipt", () => {
    saveSubmissionResult({
      candidate_assessment_id: "candidate-assessment-1",
      status: "submitted",
      submitted_at: "2026-06-27T12:00:00Z",
      pending_evaluation: true,
      auto: false,
    });

    expect(readSubmissionResult()).toMatchObject({
      candidate_assessment_id: "candidate-assessment-1",
      status: "submitted",
      pending_evaluation: true,
    });
  });

  it("removes malformed or stale receipts instead of throwing", () => {
    sessionStorage.setItem("cap_candidate_submission_result", "not-json");

    expect(readSubmissionResult()).toBeNull();
    expect(sessionStorage.getItem("cap_candidate_submission_result")).toBeNull();
  });
});
