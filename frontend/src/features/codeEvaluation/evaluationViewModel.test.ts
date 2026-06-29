import { describe, expect, it } from "vitest";

import type { Assessment } from "../assessments/types/Assessment";
import { buildAssessmentOptions, makeEmptyDashboard } from "./evaluationViewModel";

function makeAssessment(overrides: Partial<Assessment> = {}): Assessment {
  return {
    id: "assessment-1",
    recruiter_uid: "recruiter-1",
    title: "Backend screening",
    description: "Production assessment",
    instructions: "Complete every question.",
    duration_minutes: 60,
    passing_score: 70,
    test_case_score_weight: 60,
    coding_score_weight: 20,
    ai_score_weight: 20,
    allow_resume: true,
    shuffle_questions: false,
    question_count_per_candidate: 0,
    show_score_to_candidate: false,
    proctoring_mode: "basic",
    hidden_feedback_mode: "none",
    max_hidden_checks: 0,
    hidden_check_cooldown_seconds: 30,
    supported_languages: ["python"],
    status: "available",
    questions: [],
    question_count: 0,
    slots: [],
    test_count: 0,
    scheduled_test_count: 0,
    live_test_count: 0,
    created_at: "2026-06-27T10:00:00Z",
    updated_at: "2026-06-27T10:00:00Z",
    ...overrides,
  };
}

describe("evaluation view model", () => {
  it("does not fabricate demo data when no assessments exist", () => {
    expect(buildAssessmentOptions([])).toEqual([]);
  });

  it("builds an empty dashboard from the selected real assessment", () => {
    const [assessment] = buildAssessmentOptions([makeAssessment()]);

    expect(assessment).toMatchObject({
      id: "assessment-1",
      candidateCount: 0,
      submittedCount: 0,
      testCount: 0,
    });
    expect(makeEmptyDashboard(assessment)).toMatchObject({
      overview: {
        assessment_id: "assessment-1",
        title: "Backend screening",
        total_candidates: 0,
        completed_candidates: 0,
      },
      leaderboard: [],
      jobs: [],
    });
  });
});
