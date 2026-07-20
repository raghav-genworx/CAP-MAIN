import { coreApiClient } from "../../../lib/axios";
import type {
  CandidateAssessmentPortal,
  CandidateCheckpointPayload,
  CandidateCheckpointResponse,
  CandidateCodeRunPayload,
  CandidateHiddenCheckResponse,
  CandidateInviteVerificationResponse,
  CandidateProctorEventResponse,
  CandidateSampleRunResponse,
  CandidateStartResponse,
  CandidateSubmitPayload,
  CandidateSubmitResponse,
} from "../types/CandidatePortal";

function candidateAuthHeader(sessionToken: string) {
  return {
    Authorization: `Bearer ${sessionToken}`,
  };
}

export async function verifyInvite(
  token: string,
): Promise<CandidateInviteVerificationResponse> {
  const response = await coreApiClient.post<CandidateInviteVerificationResponse>(
    "/candidate/verify-invite",
    { token },
  );
  return response.data;
}

export async function startCandidateAssessment(
  token: string,
): Promise<CandidateStartResponse> {
  const response = await coreApiClient.post<CandidateStartResponse>(
    "/candidate/start",
    { token },
  );
  return response.data;
}

export async function fetchCandidateAssessment(
  sessionToken: string,
): Promise<CandidateAssessmentPortal> {
  const response = await coreApiClient.get<CandidateAssessmentPortal>(
    "/candidate/assessment",
    {
      headers: candidateAuthHeader(sessionToken),
    },
  );
  return response.data;
}

export async function saveCandidateCheckpoint(
  sessionToken: string,
  payload: CandidateCheckpointPayload,
): Promise<CandidateCheckpointResponse> {
  const response = await coreApiClient.post<CandidateCheckpointResponse>(
    "/candidate/checkpoint",
    payload,
    {
      headers: candidateAuthHeader(sessionToken),
    },
  );
  return response.data;
}

export async function recordCandidateProctorEvent(
  sessionToken: string,
  payload: {
    client_event_id: string;
    event_type: "tab_hidden" | "window_blur" | "clipboard" | "fullscreen_exit";
    occurred_at: string;
  },
): Promise<CandidateProctorEventResponse> {
  const response = await coreApiClient.post<CandidateProctorEventResponse>(
    "/candidate/proctoring-events",
    payload,
    { headers: candidateAuthHeader(sessionToken) },
  );
  return response.data;
}

export async function runCandidateSample(
  sessionToken: string,
  payload: CandidateCodeRunPayload,
): Promise<CandidateSampleRunResponse> {
  const response = await coreApiClient.post<CandidateSampleRunResponse>(
    "/candidate/run-sample",
    payload,
    {
      headers: candidateAuthHeader(sessionToken),
    },
  );
  return response.data;
}

export async function runCandidateHiddenCheck(
  sessionToken: string,
  payload: CandidateCodeRunPayload,
): Promise<CandidateHiddenCheckResponse> {
  const response = await coreApiClient.post<CandidateHiddenCheckResponse>(
    "/candidate/hidden-check",
    payload,
    {
      headers: candidateAuthHeader(sessionToken),
    },
  );
  return response.data;
}

export async function submitCandidateAssessment(
  sessionToken: string,
  payload: CandidateSubmitPayload,
): Promise<CandidateSubmitResponse> {
  const response = await coreApiClient.post<CandidateSubmitResponse>(
    "/candidate/submit",
    payload,
    {
      headers: candidateAuthHeader(sessionToken),
    },
  );
  return response.data;
}
