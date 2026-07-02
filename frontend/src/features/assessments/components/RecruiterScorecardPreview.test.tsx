import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CandidateEvaluationSummary } from "../../codeEvaluation";
import { RecruiterScorecardPreview } from "./RecruiterScorecardPreview";

const candidate: CandidateEvaluationSummary = {
  assessment_id: "assessment-1",
  candidate_assessment_id: "candidate-assessment-1",
  candidate_id: "candidate-1",
  candidate_name: "Candidate One",
  candidate_email: "candidate@example.com",
  submission_id: "submission-1",
  language: "python",
  status: "completed",
  rank: 2,
  scores: {
    test_case_score: 75,
    coding_score: 90,
    ai_score: 85,
    final_score: 81,
    percentage: 81,
  },
  hidden_passed: 3,
  hidden_total: 4,
  total_execution_time_ms: 120,
  peak_memory_kb: 32_000,
  ai_quality: {
    score: 85,
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
      question_title: "Array Balancer",
      language: "python",
      submitted_code: "def solve(values):\n    return sum(values)",
      passed_count: 1,
      total_count: 2,
      earned_points: 5,
      total_points: 10,
      score: 50,
      mandatory_failed: false,
      test_cases: [
        {
          test_case_id: "case-1",
          passed: true,
          verdict: "accepted",
          execution_time_ms: 10,
          memory_kb: 1024,
          points: 5,
          mandatory: true,
          input: "1 2",
          expected_output: "3",
          actual_output: "3",
          message: "",
        },
        {
          test_case_id: "case-2",
          passed: false,
          verdict: "wrong_answer",
          execution_time_ms: 12,
          memory_kb: 1024,
          points: 5,
          mandatory: false,
          input: "-1 1",
          expected_output: "0",
          actual_output: "1",
          message: "Wrong answer",
        },
      ],
    },
  ],
  submitted_at: "2026-06-27T08:00:00Z",
  evaluated_at: "2026-06-27T08:01:00Z",
  time_taken_seconds: 1200,
};

describe("RecruiterScorecardPreview", () => {
  it("shows submitted code and question-level test outcomes", () => {
    const onDownload = vi.fn();
    render(
      <RecruiterScorecardPreview
        candidate={candidate}
        loading={false}
        error=""
        downloadPending={false}
        onDownload={onDownload}
      />,
    );

    expect(screen.getByText("Candidate One")).toBeInTheDocument();
    expect(screen.getByText("Array Balancer")).toBeInTheDocument();
    expect(screen.getByText(/def solve\(values\)/)).toBeInTheDocument();
    expect(screen.getByText("Passed - accepted")).toBeInTheDocument();
    expect(screen.getByText("Failed - wrong answer")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Download PDF" }));
    expect(onDownload).toHaveBeenCalledOnce();
  });

  it("announces scorecard loading failures", () => {
    render(
      <RecruiterScorecardPreview
        candidate={null}
        loading={false}
        error="Scorecard unavailable"
        downloadPending={false}
        onDownload={() => undefined}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Scorecard unavailable");
  });
});
