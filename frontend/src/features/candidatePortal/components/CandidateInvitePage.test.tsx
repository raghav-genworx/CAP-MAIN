import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CandidateInvitePage } from "./CandidateInvitePage";
import {
  startCandidateAssessment,
  verifyInvite,
} from "../services/candidatePortalService";

vi.mock("../services/candidatePortalService", () => ({
  startCandidateAssessment: vi.fn(),
  verifyInvite: vi.fn(),
}));

const verifyInviteMock = vi.mocked(verifyInvite);
const startCandidateAssessmentMock = vi.mocked(startCandidateAssessment);

function renderInvitePage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const router = createMemoryRouter(
    [
      {
        path: "/candidate/invite/:token",
        element: <CandidateInvitePage />,
      },
      {
        path: "/candidate/portal",
        element: <h1>Portal loaded</h1>,
      },
    ],
    { initialEntries: ["/candidate/invite/secure-invite-token"] },
  );

  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function inviteResponse(canStart = true) {
  const now = Date.now();
  return {
    candidate_name: "Asha Rao",
    candidate_email: "asha@example.com",
    assessment_id: "assessment-1",
    assessment_title: "Backend Engineering Assessment",
    slot_id: "slot-1",
    slot_title: "June Hiring Window",
    instructions: "Complete both coding questions before the window closes.",
    duration_minutes: 90,
    start_at: new Date(now - 60_000).toISOString(),
    end_at: new Date(now + 3_600_000).toISOString(),
    allow_resume: true,
    status: canStart ? ("not_started" as const) : ("submitted" as const),
    can_start: canStart,
  };
}

describe("CandidateInvitePage", () => {
  beforeEach(() => {
    sessionStorage.clear();
    verifyInviteMock.mockResolvedValue(inviteResponse());
    startCandidateAssessmentMock.mockResolvedValue({
      session_token: "candidate-session-token",
      expires_at: new Date(Date.now() + 3_600_000).toISOString(),
      candidate_assessment_id: "candidate-assessment-1",
      status: "in_progress",
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("starts a verified invite and opens the assessment portal", async () => {
    sessionStorage.setItem("cap_candidate_submission_result", "stale-receipt");
    renderInvitePage();

    expect(await screen.findByRole("heading", { name: "Welcome, Asha Rao" })).toBeInTheDocument();
    expect(screen.getByText("Backend Engineering Assessment")).toBeInTheDocument();
    expect(screen.getByText(/Active now/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Start Assessment" }));

    expect(await screen.findByRole("heading", { name: "Portal loaded" })).toBeInTheDocument();
    expect(startCandidateAssessmentMock).toHaveBeenCalledWith("secure-invite-token");
    expect(sessionStorage.getItem("cap_candidate_session_token")).toBe(
      "candidate-session-token",
    );
    expect(sessionStorage.getItem("cap_candidate_submission_result")).toBeNull();
  });

  it("keeps an unavailable assessment disabled with a clear explanation", async () => {
    verifyInviteMock.mockResolvedValue(inviteResponse(false));
    renderInvitePage();

    expect(await screen.findByText(/not open right now or has already been submitted/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start Assessment" })).toBeDisabled();
    expect(startCandidateAssessmentMock).not.toHaveBeenCalled();
  });
});
