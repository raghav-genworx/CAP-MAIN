import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  downloadCandidateEvaluationReport,
  downloadTestEvaluationReport,
  fetchCandidateEvaluationReport,
} from "../../codeEvaluation";
import type { CandidateEvaluationSummary } from "../../codeEvaluation";
import type { SlotCandidate } from "../types/Assessment";
import { TestResultsTab } from "./TestResultsTab";

const getIdToken = vi.fn(async () => "recruiter-token");

vi.mock("../../auth", () => ({
  useAuth: () => ({ currentUser: { getIdToken } }),
}));

vi.mock("../../codeEvaluation", () => ({
  downloadCandidateEvaluationReport: vi.fn(),
  downloadTestEvaluationReport: vi.fn(),
  fetchCandidateEvaluationReport: vi.fn(),
}));

vi.mock("./RecruiterScorecardPreview", () => ({
  RecruiterScorecardPreview: ({
    candidate,
    loading,
  }: {
    candidate: CandidateEvaluationSummary | null;
    loading: boolean;
  }) => (
    <div data-testid="scorecard">
      {loading ? "Loading scorecard" : candidate?.candidate_name}
    </div>
  ),
}));

const fetchScorecardMock = vi.mocked(fetchCandidateEvaluationReport);
const downloadCandidateMock = vi.mocked(downloadCandidateEvaluationReport);
const downloadTestMock = vi.mocked(downloadTestEvaluationReport);

function candidate(
  id: string,
  name: string,
  rank: number | null,
  percentage: number | null,
): SlotCandidate {
  return {
    candidate_assessment_id: id,
    candidate_id: `candidate-${id}`,
    name,
    email: `${name.toLowerCase()}@example.com`,
    external_id: id,
    invite_status: "sent",
    assessment_status: "submitted",
    hidden_checks_used: 0,
    started_at: "2026-06-28T08:00:00Z",
    submitted_at: "2026-06-28T09:00:00Z",
    last_activity_at: "2026-06-28T09:00:00Z",
    total_score: percentage,
    percentage,
    rank,
  };
}

const candidates = [
  candidate("candidate-2", "Bina", 2, 74),
  candidate("candidate-1", "Asha", 1, 92),
  candidate("candidate-3", "Charu", null, null),
];

function renderResults(onBackfillEvaluations = vi.fn()) {
  render(
    <TestResultsTab
      assessmentId="assessment-1"
      slotId="slot-1"
      candidates={candidates}
      backfillPending={false}
      backfillError=""
      backfillResult={null}
      onBackfillEvaluations={onBackfillEvaluations}
    />,
  );
  return onBackfillEvaluations;
}

describe("TestResultsTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("orders the leaderboard and backfills only unevaluated submissions", () => {
    const onBackfill = renderResults();
    const rows = within(
      screen.getByRole("table", { name: "Candidate evaluation leaderboard" }),
    ).getAllByRole("row");

    expect(rows[1]).toHaveTextContent("#1");
    expect(rows[1]).toHaveTextContent("Asha");
    expect(rows[2]).toHaveTextContent("#2");
    expect(rows[2]).toHaveTextContent("Bina");
    expect(screen.getByText("83%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Evaluate Previous" }));
    expect(onBackfill).toHaveBeenCalledWith(["candidate-3"]);
  });

  it("opens scorecards and downloads candidate and test reports", async () => {
    fetchScorecardMock.mockResolvedValue({
      candidate_name: "Asha",
    } as CandidateEvaluationSummary);
    renderResults();

    fireEvent.click(screen.getByRole("button", { name: "Asha" }));
    await waitFor(() => expect(screen.getByTestId("scorecard")).toHaveTextContent("Asha"));
    expect(fetchScorecardMock).toHaveBeenCalledWith(
      "recruiter-token",
      "assessment-1",
      "candidate-1",
      expect.any(AbortSignal),
    );

    fireEvent.click(screen.getAllByRole("button", { name: "PDF" })[0]);
    await waitFor(() =>
      expect(downloadCandidateMock).toHaveBeenCalledWith(
        "recruiter-token",
        "assessment-1",
        "candidate-1",
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Download Test PDF" }));
    await waitFor(() =>
      expect(downloadTestMock).toHaveBeenCalledWith(
        "recruiter-token",
        "assessment-1",
        "slot-1",
      ),
    );
  });
});
