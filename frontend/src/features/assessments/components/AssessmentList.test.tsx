import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Assessment, AssessmentSlot } from "../types/Assessment";
import { AssessmentList } from "./AssessmentList";

const slot: AssessmentSlot = {
  id: "slot-1",
  assessment_id: "assessment-1",
  recruiter_uid: "recruiter-1",
  title: "June hiring window",
  instructions_override: "",
  start_at: "2026-06-28T09:00:00Z",
  end_at: "2026-06-28T11:00:00Z",
  timezone_name: "Asia/Kolkata",
  timezone_offset_minutes: 330,
  status: "active",
  effective_status: "active",
  seconds_until_start: 0,
  accepting_closes_in_seconds: 3600,
  is_accepting_responses: true,
  paused_at: null,
  total_paused_seconds: 0,
  candidate_count: 8,
  submitted_count: 3,
  created_at: "2026-06-27T08:00:00Z",
  updated_at: "2026-06-28T08:00:00Z",
};

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
  question_count: 4,
  slots: [slot],
  test_count: 1,
  scheduled_test_count: 0,
  live_test_count: 1,
  created_at: "2026-06-27T08:00:00Z",
  updated_at: "2026-06-28T08:00:00Z",
};

describe("AssessmentList", () => {
  it("renders loading and empty states without showing a stale table", () => {
    const { rerender } = render(
      <AssessmentList
        assessments={[]}
        loading
        onAddNew={vi.fn()}
        onOpen={vi.fn()}
      />,
    );

    expect(screen.getByText("Loading assessments...")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    rerender(
      <AssessmentList
        assessments={[]}
        loading={false}
        onAddNew={vi.fn()}
        onOpen={vi.fn()}
      />,
    );

    expect(
      screen.getByText("No assessments yet. Create one to start scheduling tests."),
    ).toBeInTheDocument();
  });

  it("opens creation and assessment navigation through explicit controls", () => {
    const onAddNew = vi.fn();
    const onOpen = vi.fn();
    render(
      <AssessmentList
        assessments={[assessment]}
        loading={false}
        onAddNew={onAddNew}
        onOpen={onOpen}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Add New Assessment" }));
    expect(onAddNew).toHaveBeenCalledOnce();

    const assessmentRow = screen.getByRole("button", {
      name: "Open Backend Engineering Assessment",
    });
    fireEvent.keyDown(assessmentRow, { key: "Enter" });
    expect(onOpen).toHaveBeenCalledWith("assessment-1");
  });

  it("expands visible tests without triggering assessment navigation", () => {
    const onOpen = vi.fn();
    render(
      <AssessmentList
        assessments={[assessment]}
        loading={false}
        onAddNew={vi.fn()}
        onOpen={onOpen}
      />,
    );

    const toggle = screen.getByRole("button", { name: "Show Tests" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);

    expect(onOpen).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Hide Tests" }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("June hiring window")).toBeInTheDocument();
    expect(screen.getByText("8 candidates")).toBeInTheDocument();
  });

  it("presents distinct tests and actions columns", () => {
    render(
      <AssessmentList
        assessments={[assessment]}
        loading={false}
        onAddNew={vi.fn()}
        onOpen={vi.fn()}
      />,
    );

    const headers = within(screen.getByRole("table")).getAllByRole("columnheader");
    expect(headers.map((header) => header.textContent)).toContain("Tests");
    expect(headers.map((header) => header.textContent)).toContain("Actions");
  });
});
