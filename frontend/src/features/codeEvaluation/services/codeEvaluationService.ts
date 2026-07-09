import { coreApiClient } from "../../../lib/axios";
import type {
  AssessmentEvaluationDashboard,
  CandidateEvaluationReport,
  CandidateEvaluationSummary,
  EvaluationBackfillResponse,
  RetryEvaluationResponse,
} from "../types/EvaluationResult";

export async function fetchAssessmentEvaluationDashboard(
  idToken: string,
  assessmentId: string,
): Promise<AssessmentEvaluationDashboard> {
  const response = await coreApiClient.get<AssessmentEvaluationDashboard>(
    `/assessments/${assessmentId}/evaluations/dashboard`,
    { headers: authHeader(idToken) },
  );
  return response.data;
}

export async function backfillAssessmentEvaluations(
  idToken: string,
  assessmentId: string,
): Promise<EvaluationBackfillResponse> {
  const response = await coreApiClient.post<EvaluationBackfillResponse>(
    `/assessments/${assessmentId}/evaluations/backfill`,
    {},
    {
      headers: {
        Authorization: `Bearer ${idToken}`,
      },
    },
  );
  return response.data;
}

export async function retryEvaluationJob(
  idToken: string,
  assessmentId: string,
  jobId: string,
): Promise<RetryEvaluationResponse> {
  const response = await coreApiClient.post<RetryEvaluationResponse>(
    `/assessments/${assessmentId}/evaluations/jobs/${jobId}/retry`,
    {},
    { headers: authHeader(idToken) },
  );
  return response.data;
}

export async function fetchCandidateEvaluationReport(
  idToken: string,
  assessmentId: string,
  candidateAssessmentId: string,
  signal?: AbortSignal,
): Promise<CandidateEvaluationSummary> {
  const response = await coreApiClient.get<{
    candidate: CandidateEvaluationSummary;
  }>(
    `/assessments/${assessmentId}/evaluations/reports/candidates/`
      + candidateAssessmentId,
    {
      headers: authHeader(idToken),
      signal,
    },
  );
  return response.data.candidate;
}

export async function fetchCandidateScorecardReport(
  idToken: string,
  assessmentId: string,
  candidateAssessmentId: string,
  signal?: AbortSignal,
): Promise<CandidateEvaluationReport> {
  const response = await coreApiClient.get<CandidateEvaluationReport>(
    `/assessments/${assessmentId}/evaluations/reports/candidates/`
      + candidateAssessmentId,
    { headers: authHeader(idToken), signal },
  );
  return response.data;
}

export async function downloadAssessmentEvaluationReport(
  idToken: string,
  assessmentId: string,
): Promise<void> {
  await downloadReport(
    idToken,
    `/assessments/${assessmentId}/evaluations/reports/download`,
    `assessment-${assessmentId}.pdf`,
  );
}

export async function downloadCandidateEvaluationReport(
  idToken: string,
  assessmentId: string,
  candidateAssessmentId: string,
): Promise<void> {
  await downloadReport(
    idToken,
    `/assessments/${assessmentId}/evaluations/reports/candidates/`
      + `${candidateAssessmentId}/download`,
    `candidate-${candidateAssessmentId}.pdf`,
  );
}

export async function downloadTestEvaluationReport(
  idToken: string,
  assessmentId: string,
  slotId: string,
): Promise<void> {
  await downloadReport(
    idToken,
    `/assessments/${assessmentId}/evaluations/reports/tests/${slotId}/download`,
    `test-${slotId}.pdf`,
  );
}

function authHeader(idToken: string) {
  return { Authorization: `Bearer ${idToken}` };
}

async function downloadReport(
  idToken: string,
  path: string,
  fallbackFilename: string,
): Promise<void> {
  const response = await coreApiClient.get<Blob>(path, {
    headers: authHeader(idToken),
    responseType: "blob",
  });
  const disposition = String(response.headers["content-disposition"] ?? "");
  const filename =
    /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? fallbackFilename;
  const objectUrl = URL.createObjectURL(response.data);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
}
