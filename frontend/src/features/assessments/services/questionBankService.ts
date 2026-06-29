import { coreApiClient } from "../../../lib/axios";
import type {
  DifficultyLevel,
  QuestionAIDraftRequest,
  QuestionAIDraftProgressEvent,
  QuestionAIDraftResponse,
  QuestionBulkImportRequest,
  QuestionBulkImportResponse,
  QuestionCreatePayload,
  QuestionDraftValidationRequest,
  QuestionDraftValidationResponse,
  QuestionGroupCreatePayload,
  QuestionGroupListResponse,
  QuestionGroupRecord,
  QuestionGroupStatus,
  QuestionGroupUpdatePayload,
  QuestionListResponse,
  QuestionRecord,
  QuestionUpdatePayload,
  QuestionStatus,
} from "../types/QuestionBank";

interface QuestionBankFilters {
  search?: string;
  difficulty?: DifficultyLevel | "";
  status?: QuestionStatus | "";
  tag?: string;
}

interface QuestionGroupFilters {
  search?: string;
  status?: QuestionGroupStatus | "";
}

function authHeader(idToken: string) {
  return {
    Authorization: `Bearer ${idToken}`,
  };
}

export async function fetchQuestionBankQuestions(
  idToken: string,
  filters: QuestionBankFilters,
): Promise<QuestionListResponse> {
  const response = await coreApiClient.get<QuestionListResponse>(
    "/question-bank/questions",
    {
      headers: authHeader(idToken),
      params: {
        search: filters.search || undefined,
        difficulty: filters.difficulty || undefined,
        status: filters.status || undefined,
        tag: filters.tag || undefined,
      },
    },
  );
  return response.data;
}

export async function createQuestionBankQuestion(
  idToken: string,
  payload: QuestionCreatePayload,
): Promise<QuestionRecord> {
  const response = await coreApiClient.post<QuestionRecord>(
    "/question-bank/questions",
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function bulkImportQuestionBankQuestions(
  idToken: string,
  payload: QuestionBulkImportRequest,
): Promise<QuestionBulkImportResponse> {
  const response = await coreApiClient.post<QuestionBulkImportResponse>(
    "/question-bank/questions/bulk-import",
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function updateQuestionBankQuestion(
  idToken: string,
  questionId: string,
  payload: QuestionUpdatePayload,
): Promise<QuestionRecord> {
  const response = await coreApiClient.patch<QuestionRecord>(
    `/question-bank/questions/${questionId}`,
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function deleteQuestionBankQuestion(
  idToken: string,
  questionId: string,
): Promise<void> {
  await coreApiClient.delete(`/question-bank/questions/${questionId}`, {
    headers: authHeader(idToken),
  });
}

export async function generateQuestionBankDraft(
  idToken: string,
  payload: QuestionAIDraftRequest,
): Promise<QuestionAIDraftResponse> {
  const response = await coreApiClient.post<QuestionAIDraftResponse>(
    "/question-bank/questions/ai-draft",
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function streamQuestionBankDraft(
  idToken: string,
  payload: QuestionAIDraftRequest,
  onProgress: (event: QuestionAIDraftProgressEvent) => void,
): Promise<QuestionAIDraftResponse> {
  const response = await fetch(
    `${coreApiClient.defaults.baseURL || ""}/question-bank/questions/ai-draft/stream`,
    {
      method: "POST",
      headers: {
        ...authHeader(idToken),
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      credentials: "include",
    },
  );
  if (!response.ok || !response.body) {
    throw new Error("Unable to stream question generation.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: QuestionAIDraftResponse | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const dataLine = frame
        .split("\n")
        .find((line) => line.startsWith("data: "));
      if (!dataLine) {
        continue;
      }
      const progressEvent = JSON.parse(
        dataLine.slice(6),
      ) as QuestionAIDraftProgressEvent;
      onProgress(progressEvent);
      if (progressEvent.type === "error") {
        throw new Error(progressEvent.message);
      }
      if (progressEvent.type === "complete" && progressEvent.response) {
        finalResponse = progressEvent.response;
      }
    }
  }

  if (!finalResponse) {
    throw new Error("Question generation stream ended before returning a draft.");
  }
  return finalResponse;
}

export async function validateQuestionBankDraft(
  idToken: string,
  payload: QuestionDraftValidationRequest,
): Promise<QuestionDraftValidationResponse> {
  const response = await coreApiClient.post<QuestionDraftValidationResponse>(
    "/question-bank/questions/validate-draft",
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function fetchQuestionGroups(
  idToken: string,
  filters: QuestionGroupFilters,
): Promise<QuestionGroupListResponse> {
  const response = await coreApiClient.get<QuestionGroupListResponse>(
    "/question-bank/groups",
    {
      headers: authHeader(idToken),
      params: {
        search: filters.search || undefined,
        status: filters.status || undefined,
      },
    },
  );
  return response.data;
}

export async function createQuestionGroup(
  idToken: string,
  payload: QuestionGroupCreatePayload,
): Promise<QuestionGroupRecord> {
  const response = await coreApiClient.post<QuestionGroupRecord>(
    "/question-bank/groups",
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function updateQuestionGroup(
  idToken: string,
  groupId: string,
  payload: QuestionGroupUpdatePayload,
): Promise<QuestionGroupRecord> {
  const response = await coreApiClient.patch<QuestionGroupRecord>(
    `/question-bank/groups/${groupId}`,
    payload,
    {
      headers: authHeader(idToken),
    },
  );
  return response.data;
}

export async function deleteQuestionGroup(
  idToken: string,
  groupId: string,
): Promise<void> {
  await coreApiClient.delete(`/question-bank/groups/${groupId}`, {
    headers: authHeader(idToken),
  });
}
