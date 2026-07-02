import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CandidateAssessmentPage } from "./CandidateAssessmentPage";
import {
  fetchCandidateAssessment,
  runCandidateHiddenCheck,
  runCandidateSample,
  saveCandidateCheckpoint,
  submitCandidateAssessment,
} from "../services/candidatePortalService";
import {
  readCandidateSessionToken,
  readSubmissionResult,
  saveCandidateSessionToken,
} from "../utils/sessionStorage";
import type { CandidateAssessmentPortal } from "../types/CandidatePortal";

vi.mock("@monaco-editor/react", () => ({
  default: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (value: string) => void;
  }) => (
    <textarea
      aria-label="Code editor"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));

vi.mock("../services/candidatePortalService", () => ({
  fetchCandidateAssessment: vi.fn(),
  runCandidateHiddenCheck: vi.fn(),
  runCandidateSample: vi.fn(),
  saveCandidateCheckpoint: vi.fn(),
  submitCandidateAssessment: vi.fn(),
}));

const fetchAssessmentMock = vi.mocked(fetchCandidateAssessment);
const saveCheckpointMock = vi.mocked(saveCandidateCheckpoint);
const runSampleMock = vi.mocked(runCandidateSample);
const runHiddenMock = vi.mocked(runCandidateHiddenCheck);
const submitAssessmentMock = vi.mocked(submitCandidateAssessment);

const assessment: CandidateAssessmentPortal = {
  candidate_name: "Asha Rao",
  candidate_email: "asha@example.com",
  candidate_assessment_id: "candidate-assessment-1",
  assessment_id: "assessment-1",
  assessment_title: "Backend Engineering Assessment",
  slot_id: "slot-1",
  slot_title: "June Hiring Window",
  instructions: "Complete every question.",
  duration_minutes: 60,
  allow_resume: true,
  proctoring_mode: "basic",
  hidden_feedback_mode: "summary",
  max_hidden_checks: 2,
  hidden_check_cooldown_seconds: 5,
  started_at: "2026-06-27T08:00:00Z",
  deadline_at: new Date(Date.now() + 1_200_000).toISOString(),
  submitted_at: null,
  status: "in_progress",
  current_question_order: 1,
  time_remaining_seconds: 1_200,
  supported_languages: ["python"],
  questions: [
    {
      id: "question-1",
      title: "Array Sum",
      difficulty: "easy",
      problem_statement: "Print the sum of the supplied values.",
      constraints: "1 <= n <= 1000",
      input_format: "A line of integers.",
      output_format: "One integer.",
      sample_test_cases: [{ input: "1 2", expected_output: "3" }],
      supported_languages: ["python"],
      question_order: 1,
      marks: 10,
      is_mandatory: true,
    },
    {
      id: "question-2",
      title: "Reverse Text",
      difficulty: "easy",
      problem_statement: "Reverse the supplied text.",
      constraints: "1 <= length <= 1000",
      input_format: "One line.",
      output_format: "The reversed line.",
      sample_test_cases: [{ input: "cap", expected_output: "pac" }],
      supported_languages: ["python"],
      question_order: 2,
      marks: 10,
      is_mandatory: true,
    },
  ],
  drafts: [],
};

function renderCandidatePage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const router = createMemoryRouter(
    [
      { path: "/candidate/portal", element: <CandidateAssessmentPage /> },
      { path: "/candidate/submitted", element: <h1>Submission route</h1> },
    ],
    { initialEntries: ["/candidate/portal"] },
  );
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("CandidateAssessmentPage journey", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    saveCandidateSessionToken("candidate-session-token");
    Object.defineProperty(document.documentElement, "requestFullscreen", {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    });
    fetchAssessmentMock.mockResolvedValue(assessment);
    saveCheckpointMock.mockResolvedValue({
      question_id: "question-1",
      saved_at: "2026-06-27T09:00:00Z",
      status: "draft",
    });
    runSampleMock.mockResolvedValue({
      question_id: "question-1",
      passed_count: 1,
      total_count: 1,
      results: [
        {
          index: 1,
          input: "1 2",
          expected_output: "3",
          actual_output: "3",
          status: "Accepted",
          passed: true,
          stderr: "",
          compile_output: "",
          message: "",
          execution_time: "0.01",
          memory_kb: 1024,
          token: "public-sample-result",
        },
      ],
    });
    runHiddenMock.mockResolvedValue({
      question_id: "question-1",
      passed_count: 1,
      total_count: 1,
      remaining_attempts: null,
      cooldown_remaining_seconds: 5,
      results: [
        {
          index: 1,
          status: "Accepted",
          passed: true,
          execution_time: "0.01",
          error_type: "",
        },
      ],
    });
    submitAssessmentMock.mockResolvedValue({
      candidate_assessment_id: "candidate-assessment-1",
      status: "submitted",
      submitted_at: "2026-06-27T09:05:00Z",
      pending_evaluation: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("saves, tests, reviews, and submits the active assessment", async () => {
    renderCandidatePage();

    expect(
      await screen.findByRole("heading", { name: "Array Sum" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Code editor"), {
      target: { value: "print(sum(map(int, input().split())))" },
    });
    expect(
      screen.getByRole("button", { name: /Testcase Results/ }),
    ).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(screen.getByRole("button", { name: "Save Progress" }));
    await waitFor(() =>
      expect(saveCheckpointMock).toHaveBeenCalledWith(
        "candidate-session-token",
        {
          question_id: "question-1",
          source_code: "print(sum(map(int, input().split())))",
          language: "python",
          current_question_order: 1,
        },
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Run Test" }));
    expect(
      await screen.findAllByText("1/1 sample cases passed"),
    ).not.toHaveLength(0);
    expect(screen.getByText("TC 1 · Passed")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Testcase Results/ }),
    ).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(screen.getByRole("button", { name: "Submit Question" }));
    expect(
      await screen.findAllByText("1/1 hidden test cases passed"),
    ).not.toHaveLength(0);
    expect(screen.getByText("TC 1 · Passed")).toBeInTheDocument();
    expect(
      await screen.findByText("This question is marked submitted."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Submit again in 5s" }),
    ).toBeDisabled();
    expect(runHiddenMock).toHaveBeenCalledWith("candidate-session-token", {
      question_id: "question-1",
      source_code: "print(sum(map(int, input().split())))",
      language: "python",
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Move to next question" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Reverse Text" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Submit Assessment" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Your answers before final submission"))
      .toBeInTheDocument();
    expect(within(dialog).getByText("Attempted").parentElement).toHaveTextContent(
      "1/2",
    );
    expect(within(dialog).getByText(/including 1 mandatory question/))
      .toBeInTheDocument();
    expect(within(dialog).getByText("print(sum(map(int, input().split())))"))
      .toBeInTheDocument();

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Submit Assessment" }),
    );

    expect(
      await screen.findByRole("heading", { name: "Submission route" }),
    ).toBeInTheDocument();
    expect(submitAssessmentMock).toHaveBeenCalledWith(
      "candidate-session-token",
      {
        answers: [
          {
            question_id: "question-1",
            source_code: "print(sum(map(int, input().split())))",
            language: "python",
          },
          {
            question_id: "question-2",
            source_code: "",
            language: "python",
          },
        ],
        auto_submit: false,
        submission_tag: "",
        submission_message: "",
      },
    );
    expect(readCandidateSessionToken()).toBeNull();
    expect(readSubmissionResult()).toMatchObject({
      candidate_assessment_id: "candidate-assessment-1",
      status: "submitted",
      pending_evaluation: true,
      auto: false,
    });
  });

  it("checkpoints the current answer before switching questions", async () => {
    renderCandidatePage();

    await screen.findByRole("heading", { name: "Array Sum" });
    fireEvent.change(screen.getByLabelText("Code editor"), {
      target: { value: "print(3)" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Question 2Reverse Text/ }),
    );

    await waitFor(() =>
      expect(saveCheckpointMock).toHaveBeenCalledWith(
        "candidate-session-token",
        expect.objectContaining({
          question_id: "question-1",
          source_code: "print(3)",
        }),
      ),
    );
    expect(
      await screen.findByRole("heading", { name: "Reverse Text" }),
    ).toBeInTheDocument();
  });

  it("auto-submits exactly once when the synchronized timer expires", async () => {
    vi.useFakeTimers();
    fetchAssessmentMock.mockResolvedValue({
      ...assessment,
      time_remaining_seconds: 1,
      deadline_at: new Date(Date.now() + 1_000).toISOString(),
    });
    renderCandidatePage();

    await vi.waitFor(() =>
      expect(screen.getByRole("heading", { name: "Array Sum" })).toBeInTheDocument(),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_100);
    });

    await vi.waitFor(() => expect(submitAssessmentMock).toHaveBeenCalledOnce());
    expect(submitAssessmentMock).toHaveBeenCalledWith(
      "candidate-session-token",
      expect.objectContaining({
        auto_submit: true,
        submission_tag: "timer_expired",
        submission_message: "Assessment auto-submitted because the timer reached zero.",
      }),
    );
    expect(readCandidateSessionToken()).toBeNull();
  });

  it("blocks clipboard actions and closes a strict test after fullscreen exit", async () => {
    fetchAssessmentMock.mockResolvedValue({
      ...assessment,
      proctoring_mode: "strict",
    });
    renderCandidatePage();

    await screen.findByRole("heading", { name: "Array Sum" });
    await waitFor(() =>
      expect(document.documentElement.requestFullscreen).toHaveBeenCalledOnce(),
    );

    const pasteEvent = new Event("paste", { bubbles: true, cancelable: true });
    document.dispatchEvent(pasteEvent);
    expect(pasteEvent.defaultPrevented).toBe(true);
    expect(
      await screen.findByText(
        "Copy, cut, and paste are disabled for this strictly monitored assessment.",
      ),
    ).toBeInTheDocument();

    document.dispatchEvent(new Event("fullscreenchange"));
    await waitFor(() => expect(submitAssessmentMock).toHaveBeenCalledOnce());
    expect(submitAssessmentMock).toHaveBeenCalledWith(
      "candidate-session-token",
      expect.objectContaining({
        auto_submit: true,
        submission_tag: "fullscreen_exit",
        submission_message:
          "Assessment closed because strict fullscreen mode was exited.",
      }),
    );
  });
});
