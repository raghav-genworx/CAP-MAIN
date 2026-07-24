import { coreApiClient } from "../../../lib/axios";
import type {
  Assessment,
  AssessmentCreatePayload,
  AssessmentListResponse,
  AssessmentQuestionsPayload,
  AssessmentSlot,
  AssessmentSlotActionPayload,
  AssessmentSlotCreatePayload,
  AssessmentSlotListResponse,
  AssessmentSlotUpdatePayload,
  CandidateImportPayload,
  CandidateImportResponse,
  EvaluationBackfillPayload,
  EvaluationBackfillResponse,
  InviteDispatchPayload,
  InviteDispatchResponse,
  MonitoringResponse,
  SlotCandidateListResponse,
} from "../types/Assessment";

function authHeader(idToken: string) {
  return {
    Authorization: `Bearer ${idToken}`,
  };
}

export async function fetchAssessments(
  idToken: string,
): Promise<AssessmentListResponse> {
  const response = await coreApiClient.get<AssessmentListResponse>("/assessments", {
    headers: authHeader(idToken),
  });
  return response.data;
}

export async function createAssessment(
  idToken: string,
  payload: AssessmentCreatePayload,
): Promise<Assessment> {
  const response = await coreApiClient.post<Assessment>("/assessments", payload, {
    headers: authHeader(idToken),
  });
  return response.data;
}

export async function updateAssessment(
  idToken: string,
  assessmentId: string,
  payload: Partial<AssessmentCreatePayload>,
): Promise<Assessment> {
  const response = await coreApiClient.patch<Assessment>(
    `/assessments/${assessmentId}`,
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function deleteAssessment(
  idToken: string,
  assessmentId: string,
): Promise<void> {
  await coreApiClient.delete(`/assessments/${assessmentId}`, {
    headers: authHeader(idToken),
  });
}

export async function setAssessmentQuestions(
  idToken: string,
  assessmentId: string,
  payload: AssessmentQuestionsPayload,
): Promise<Assessment> {
  const response = await coreApiClient.post<Assessment>(
    `/assessments/${assessmentId}/questions`,
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function fetchAssessmentSlots(
  idToken: string,
  assessmentId: string,
): Promise<AssessmentSlotListResponse> {
  const response = await coreApiClient.get<AssessmentSlotListResponse>(
    `/assessments/${assessmentId}/slots`,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function createAssessmentSlot(
  idToken: string,
  assessmentId: string,
  payload: AssessmentSlotCreatePayload,
): Promise<AssessmentSlot> {
  const response = await coreApiClient.post<AssessmentSlot>(
    `/assessments/${assessmentId}/slots`,
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function updateAssessmentSlot(
  idToken: string,
  slotId: string,
  payload: AssessmentSlotUpdatePayload,
): Promise<AssessmentSlot> {
  const response = await coreApiClient.patch<AssessmentSlot>(
    `/assessments/slots/${slotId}`,
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function controlAssessmentSlot(
  idToken: string,
  slotId: string,
  payload: AssessmentSlotActionPayload,
): Promise<AssessmentSlot> {
  const response = await coreApiClient.post<AssessmentSlot>(
    `/assessments/slots/${slotId}/actions`,
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function importSlotCandidates(
  idToken: string,
  slotId: string,
  payload: CandidateImportPayload,
): Promise<CandidateImportResponse> {
  const response = await coreApiClient.post<CandidateImportResponse>(
    `/assessments/slots/${slotId}/candidates/import`,
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function fetchSlotCandidates(
  idToken: string,
  slotId: string,
): Promise<SlotCandidateListResponse> {
  const response = await coreApiClient.get<SlotCandidateListResponse>(
    `/assessments/slots/${slotId}/candidates`,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function backfillAssessmentEvaluations(
  idToken: string,
  assessmentId: string,
  payload: EvaluationBackfillPayload = {},
): Promise<EvaluationBackfillResponse> {
  const response = await coreApiClient.post<EvaluationBackfillResponse>(
    `/assessments/${assessmentId}/evaluations/backfill`,
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function sendSlotInvites(
  idToken: string,
  slotId: string,
  payload: InviteDispatchPayload = {},
): Promise<InviteDispatchResponse> {
  const response = await coreApiClient.post<InviteDispatchResponse>(
    `/assessments/slots/${slotId}/invites/send`,
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function resendCandidateInvite(
  idToken: string,
  candidateAssessmentId: string,
): Promise<InviteDispatchResponse> {
  const response = await coreApiClient.post<InviteDispatchResponse>(
    `/assessments/candidate-assessments/${candidateAssessmentId}/invite/resend`,
    {},
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function fetchSlotMonitoring(
  idToken: string,
  slotId: string,
): Promise<MonitoringResponse> {
  const response = await coreApiClient.get<MonitoringResponse>(
    `/assessments/slots/${slotId}/monitoring`,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function streamSlotMonitoring(
  idToken: string,
  slotId: string,
  onMonitoring: (payload: MonitoringResponse) => void,
  onOpen: () => void,
  signal?: AbortSignal,
): Promise<void> {
  const baseUrl = String(coreApiClient.defaults.baseURL || "").replace(/\/$/, "");
  const response = await fetch(
    `${baseUrl}/assessments/slots/${encodeURIComponent(slotId)}/monitoring/stream`,
    {
      method: "GET",
      headers: {
        ...authHeader(idToken),
        Accept: "text/event-stream",
        "Cache-Control": "no-cache",
      },
      cache: "no-store",
      credentials: "include",
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(`Monitoring stream failed with status ${response.status}.`);
  }
  if (!response.headers.get("content-type")?.includes("text/event-stream")) {
    throw new Error("Monitoring endpoint did not return an event stream.");
  }
  if (!response.body) {
    throw new Error("The browser could not read the monitoring stream.");
  }

  onOpen();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function handleFrame(frame: string) {
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of frame.replace(/\r/g, "").split("\n")) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (eventName !== "monitoring" || dataLines.length === 0) {
      return;
    }
    onMonitoring(JSON.parse(dataLines.join("\n")) as MonitoringResponse);
  }

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      frames.forEach(handleFrame);
    }
    buffer += decoder.decode();
    if (buffer.trim()) {
      handleFrame(buffer);
    }
  } finally {
    reader.releaseLock();
  }
}
