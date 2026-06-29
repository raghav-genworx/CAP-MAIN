import { beforeEach, describe, expect, it, vi } from "vitest";

import { coreApiClient } from "../../../lib/axios";
import {
  refineQuestionBankSolution,
  refineQuestionBankTestCases,
} from "./questionBankService";
import type { QuestionDraftValidationRequest } from "../types/QuestionBank";

vi.mock("../../../lib/axios", () => ({
  coreApiClient: {
    post: vi.fn(),
  },
}));

const postMock = vi.mocked(coreApiClient.post);
const payload = {
  draft: {
    title: "Add two values",
    problem_statement: "Read two values and print their arithmetic sum.",
    difficulty: "easy",
    topics: [],
    tags: [],
    category: "arrays",
    constraints: "-1000 <= a, b <= 1000",
    input_format: "Two integers",
    input_explanation: "",
    output_format: "One integer",
    output_explanation: "",
    sample_test_cases: [],
    hidden_test_cases: [],
    reference_solution: "print(0)",
    reference_language: "python",
    supported_languages: ["python"],
    candidate_solve_time_minutes: 15,
    execution_time_limit_seconds: 2,
    memory_limit_mb: 256,
    metadata_status: "pending",
    difficulty_source: "legacy",
    validation_report: null,
    validation_status: "not_run",
    validation_updated_at: null,
    reference_solutions: {},
    solution_approach: "",
    time_complexity: "",
    space_complexity: "",
    status: "draft",
    creation_mode: "ai_assisted",
  },
} satisfies QuestionDraftValidationRequest;

describe("question refinement API", () => {
  beforeEach(() => postMock.mockReset());

  it("sends existing testcases to the dedicated testcase repair endpoint", async () => {
    postMock.mockResolvedValue({ data: { summary: "repaired" } });

    await refineQuestionBankTestCases("firebase-token", payload);

    expect(postMock).toHaveBeenCalledWith(
      "/question-bank/questions/refine-test-cases",
      payload,
      { headers: { Authorization: "Bearer firebase-token" } },
    );
  });

  it("sends the current draft to the dedicated solution repair endpoint", async () => {
    postMock.mockResolvedValue({ data: { summary: "repaired" } });

    await refineQuestionBankSolution("firebase-token", payload);

    expect(postMock).toHaveBeenCalledWith(
      "/question-bank/questions/refine-solution",
      payload,
      { headers: { Authorization: "Bearer firebase-token" } },
    );
  });
});
