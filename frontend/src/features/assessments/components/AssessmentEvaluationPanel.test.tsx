import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CandidateEvaluationSummary } from "../../codeEvaluation";
import type { Assessment, AssessmentSlot } from "../types/Assessment";
import { AssessmentEvaluationPanel } from "./AssessmentEvaluationPanel";
import {
  downloadAssessmentEvaluationReport,
  downloadCandidateEvaluationReport,
  fetchAssessmentEvaluationDashboard,
} from "../../codeEvaluation";

const getIdToken = vi.fn(async () => "recruiter-id-token");

vi.mock("../../auth", () => ({
  useAuth: () => ({ currentUser: { getIdToken } }),
}));

vi.mock("../../codeEvaluation", () => ({
  downloadAssessmentEvaluationReport: vi.fn(),
  downloadCandidateEvaluationReport: vi.fn(),
  fetchAssessmentEvaluationDashboard: vi.fn(),
}));

const fetchDashboardMock = vi.mocked(fetchAssessmentEvaluationDashboard);
const downloadAssessmentMock = vi.mocked(downloadAssessmentEvaluationReport);
const downloadCandidateMock = vi.mocked(downloadCandidateEvaluationReport);

const assessment: Assessment = {
  id: "assessment-1",
  recruiter_uid: "recruiter-1",
  title: "Backend Engineering Assessment",
  description: "Backend hiring assessment",
  instructions: "Complete every question.",
  duration_minutes: 90,
  passing_score: 60,
  test_case_score_weight: 60,
  coding_score_weight: 20,
  ai_score_weight: 20,
  allow_resume: true,
  shuffle_questions: false,
  question_count_per_candidate: 0,
  show_score_to_candidate: false,
  proctoring_mode: "basic",
  hidden_feedback_mode: "summary",
  max_hidden_checks: 0,
  hidden_check_cooldown_seconds: 5,
  supported_languages: ["python"],
  status: "live",
  questions: [],
  question_count: 1,
  slots: [],
  test_count: 1,
  scheduled_test_count: 0,
  live_test_count: 1,
  created_at: "2026-06-27T08:00:00Z",
  updated_at: "2026-06-27T08:00:00Z",
};

const slot: AssessmentSlot = {
  id: "slot-1",
  assessment_id: "assessment-1",
  recruiter_uid: "recruiter-1",
  title: "June Hiring Window",
  instructions_override: "",
  start_at: "2026-06-27T08:00:00Z",
  end_at: "2026-06-27T10:00:00Z",
  timezone_name: "Asia/Kolkata",
  timezone_offset_minutes: 330,
  status: "active",
  effective_status: "active",
  seconds_until_start: 0,
  accepting_closes_in_seconds: 3600,
  is_accepting_responses: true,
  paused_at: null,
  total_paused_seconds: 0,
  candidate_count: 5,
  submitted_count: 4,
  created_at: "2026-06-27T08:00:00Z",
  updated_at: "2026-06-27T08:00:00Z",
};

function candidate(id: string, name: string, rank: number): CandidateEvaluationSummary {
  return {
    assessment_id: "assessment-1",
    candidate_assessment_id: id,
    candidate_id: `candidate-${rank}`,
    candidate_name: name,
    candidate_email: `${name.toLowerCase().replace(" ", ".")}@example.com`,
    submission_id: `submission-${rank}`,
    language: "python",
    status: "completed",
    rank,
    scores: {
      test_case_score: 80,
      coding_score: 85,
      ai_score: 75,
      final_score: 81,
      percentage: 81,
    },
    hidden_passed: 4,
    hidden_total: 5,
    total_execution_time_ms: 120,
    peak_memory_kb: 32000,
    ai_quality: {
      score: 75,
      approach: "Linear scan",
      time_complexity: "O(n)",
      space_complexity: "O(1)",
      readability: "Clear",
      maintainability: "Maintainable",
      strengths: ["Simple"],
      weaknesses: [],
      improvements: [],
    },
    question_breakdown: [
      {
        question_id: "question-1",
        question_title: "Array Balance",
        language: "python",
        submitted_code: `print("${name}")`,
        passed_count: 4,
        total_count: 5,
        earned_points: 8,
        total_points: 10,
        score: 80,
        mandatory_failed: false,
        test_cases: [],
      },
    ],
    submitted_at: "2026-06-27T09:00:00Z",
    evaluated_at: "2026-06-27T09:01:00Z",
    time_taken_seconds: 1200,
  };
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const onBackfill = vi.fn();
  const onOpenTest = vi.fn();
  render(
    <QueryClientProvider client={queryClient}>
      <AssessmentEvaluationPanel
        assessment={assessment}
        slots={[slot]}
        backfillPending={false}
        backfillError=""
        backfillResult={null}
        onBackfill={onBackfill}
        onOpenTest={onOpenTest}
      />
    </QueryClientProvider>,
  );
  return { onBackfill, onOpenTest };
}

describe("AssessmentEvaluationPanel journey", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchDashboardMock.mockResolvedValue({
      overview: {
        assessment_id: "assessment-1",
        title: "Backend Engineering Assessment",
        total_candidates: 5,
        completed_candidates: 2,
        pending_jobs: 1,
        failed_jobs: 0,
        average_score: 78,
        average_test_case_score: 80,
        average_coding_score: 75,
        average_ai_score: 72,
        pass_rate: 80,
        highest_score: 92,
        report_status: "ready",
        generated_at: "2026-06-27T09:05:00Z",
      },
      leaderboard: [
        candidate("candidate-assessment-1", "Candidate One", 1),
        candidate("candidate-assessment-2", "Candidate Two", 2),
      ],
      jobs: [],
    });
    downloadAssessmentMock.mockResolvedValue();
    downloadCandidateMock.mockResolvedValue();
  });

  it("moves from leaderboard selection to scorecard and report commands", async () => {
    const { onBackfill, onOpenTest } = renderPanel();

    expect(
      await screen.findByRole("heading", { name: "Candidate One" }),
    ).toBeInTheDocument();
    expect(screen.getByText("2/5")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Evaluation completion" }))
      .toHaveAttribute("aria-valuenow", "40");

    fireEvent.click(screen.getByRole("button", { name: "Candidate Two" }));
    expect(
      screen.getByRole("heading", { name: "Candidate Two" }),
    ).toBeInTheDocument();
    expect(screen.getByText('print("Candidate Two")')).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Download PDF" }));
    await waitFor(() =>
      expect(downloadCandidateMock).toHaveBeenCalledWith(
        "recruiter-id-token",
        "assessment-1",
        "candidate-assessment-2",
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Assessment PDF" }));
    await waitFor(() =>
      expect(downloadAssessmentMock).toHaveBeenCalledWith(
        "recruiter-id-token",
        "assessment-1",
      ),
    );

    fireEvent.click(
      screen.getByRole("button", { name: /June Hiring Window/ }),
    );
    expect(onOpenTest).toHaveBeenCalledWith("slot-1");

    fireEvent.click(screen.getByRole("button", { name: "Evaluate previous" }));
    expect(onBackfill).toHaveBeenCalledOnce();
  });

  it("announces a report download failure without losing the scorecard", async () => {
    downloadCandidateMock.mockRejectedValue(new Error("Report is not ready."));
    renderPanel();

    expect(
      await screen.findByRole("heading", { name: "Candidate One" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Download PDF" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Report is not ready.",
    );
    expect(
      screen.getByRole("heading", { name: "Candidate One" }),
    ).toBeInTheDocument();
  });
});
