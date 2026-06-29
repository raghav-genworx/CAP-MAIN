import { beforeEach, describe, expect, it, vi } from "vitest";

import { coreApiClient } from "../../../lib/axios";
import {
  downloadCandidateEvaluationReport,
  downloadTestEvaluationReport,
  fetchAssessmentEvaluationDashboard,
  fetchCandidateEvaluationReport,
} from "./codeEvaluationService";

vi.mock("../../../lib/axios", () => ({
  coreApiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const getMock = vi.mocked(coreApiClient.get);

describe("codeEvaluationService", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it("loads dashboards through the authenticated core ownership boundary", async () => {
    const dashboard = { overview: { assessment_id: "assessment-1" } };
    getMock.mockResolvedValueOnce({ data: dashboard });

    const result = await fetchAssessmentEvaluationDashboard(
      "firebase-token",
      "assessment-1",
    );

    expect(result).toBe(dashboard);
    expect(getMock).toHaveBeenCalledWith(
      "/assessments/assessment-1/evaluations/dashboard",
      { headers: { Authorization: "Bearer firebase-token" } },
    );
  });

  it("returns the candidate from the protected scorecard envelope", async () => {
    const candidate = { candidate_assessment_id: "candidate-1" };
    const controller = new AbortController();
    getMock.mockResolvedValueOnce({ data: { candidate } });

    const result = await fetchCandidateEvaluationReport(
      "firebase-token",
      "assessment-1",
      "candidate-1",
      controller.signal,
    );

    expect(result).toBe(candidate);
    expect(getMock).toHaveBeenCalledWith(
      "/assessments/assessment-1/evaluations/reports/candidates/candidate-1",
      {
        headers: { Authorization: "Bearer firebase-token" },
        signal: controller.signal,
      },
    );
  });

  it("downloads protected PDFs and releases the temporary object URL", async () => {
    const pdf = new Blob(["pdf"], { type: "application/pdf" });
    const createObjectUrl = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:scorecard");
    const revokeObjectUrl = vi
      .spyOn(URL, "revokeObjectURL")
      .mockImplementation(() => undefined);
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    getMock.mockResolvedValueOnce({
      data: pdf,
      headers: {
        "content-disposition": 'attachment; filename="candidate-scorecard.pdf"',
      },
    });

    await downloadCandidateEvaluationReport(
      "firebase-token",
      "assessment-1",
      "candidate-1",
    );

    expect(getMock).toHaveBeenCalledWith(
      "/assessments/assessment-1/evaluations/reports/candidates/"
        + "candidate-1/download",
      {
        headers: { Authorization: "Bearer firebase-token" },
        responseType: "blob",
      },
    );
    expect(createObjectUrl).toHaveBeenCalledWith(pdf);
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:scorecard");
  });

  it("downloads a report scoped to the selected scheduled test", async () => {
    const pdf = new Blob(["pdf"], { type: "application/pdf" });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:test-report");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    getMock.mockResolvedValueOnce({ data: pdf, headers: {} });

    await downloadTestEvaluationReport(
      "firebase-token",
      "assessment-1",
      "slot-1",
    );

    expect(getMock).toHaveBeenCalledWith(
      "/assessments/assessment-1/evaluations/reports/tests/slot-1/download",
      {
        headers: { Authorization: "Bearer firebase-token" },
        responseType: "blob",
      },
    );
  });
});
