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
  QuestionDraftRefinementRequest,
  QuestionDraftRefinementResponse,
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

function completedContextTestCases(
  testCases: QuestionCreatePayload["sample_test_cases"],
) {
  return testCases.filter((testCase) => testCase.input.trim().length > 0);
}

function sanitizeAIDraftRequest(
  payload: QuestionAIDraftRequest,
): QuestionAIDraftRequest {
  const currentDraft = payload.current_draft;
  return {
    ...payload,
    target_language: payload.target_language?.trim() || undefined,
    current_draft: currentDraft
      ? {
          ...currentDraft,
          sample_test_cases: completedContextTestCases(
            currentDraft.sample_test_cases,
          ),
          hidden_test_cases: completedContextTestCases(
            currentDraft.hidden_test_cases,
          ),
        }
      : undefined,
  };
}

function errorMessageFromUnknown(error: unknown, fallback: string) {
  return error instanceof Error && error.message.trim()
    ? error.message
    : fallback;
}

function errorMessageFromDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object" || !("msg" in item)) {
          return null;
        }
        return typeof item.msg === "string" ? item.msg : null;
      })
      .filter((message): message is string => Boolean(message));
    return messages.length ? messages.join("; ") : null;
  }

  return null;
}

async function streamResponseErrorMessage(response: Response): Promise<string> {
  const fallback = response.statusText
    ? `Question generation stream failed (${response.status} ${response.statusText}).`
    : `Question generation stream failed with status ${response.status}.`;

  try {
    const text = await response.text();
    if (!text.trim()) {
      return fallback;
    }

    try {
      const body = JSON.parse(text) as { detail?: unknown };
      return errorMessageFromDetail(body.detail) || text;
    } catch {
      return text;
    }
  } catch {
    return fallback;
  }
}

async function generateQuestionBankDraftFallback(
  idToken: string,
  payload: QuestionAIDraftRequest,
  onProgress: (event: QuestionAIDraftProgressEvent) => void,
  streamFailureMessage: string,
): Promise<QuestionAIDraftResponse> {
  onProgress({
    type: "node_start",
    scope: payload.generation_scope,
    message:
      "Live streaming was unavailable, so CAP is generating the draft without live progress.",
    current_node: "non_streaming_generation",
    next_node: null,
    progress: 5,
  });

  try {
    const response = await generateQuestionBankDraft(idToken, payload);
    onProgress({
      type: "complete",
      scope: payload.generation_scope,
      message: "Question draft generated.",
      current_node: "non_streaming_generation",
      next_node: "END",
      progress: 100,
      response,
    });
    return response;
  } catch (error) {
    throw new Error(
      errorMessageFromUnknown(error, streamFailureMessage || "Question generation failed."),
    );
  }
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
  const sanitizedPayload = sanitizeAIDraftRequest(payload);
  const response = await coreApiClient.post<QuestionAIDraftResponse>(
    "/question-bank/questions/ai-draft",
    sanitizedPayload,
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
  signal?: AbortSignal,
): Promise<QuestionAIDraftResponse> {
  const sanitizedPayload = sanitizeAIDraftRequest(payload);
  let response: Response;
  try {
    response = await fetch(
      `${coreApiClient.defaults.baseURL || ""}/question-bank/questions/ai-draft/stream`,
      {
        method: "POST",
        headers: {
          ...authHeader(idToken),
          Accept: "text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(sanitizedPayload),
        credentials: "include",
        signal,
      },
    );
  } catch (error) {
    return generateQuestionBankDraftFallback(
      idToken,
      sanitizedPayload,
      onProgress,
      errorMessageFromUnknown(error, "Unable to connect to the question stream."),
    );
  }

  if (!response.ok) {
    const message = await streamResponseErrorMessage(response);
    if (response.status >= 400 && response.status < 500) {
      throw new Error(message);
    }
    return generateQuestionBankDraftFallback(
      idToken,
      sanitizedPayload,
      onProgress,
      message,
    );
  }

  if (!response.body) {
    return generateQuestionBankDraftFallback(
      idToken,
      sanitizedPayload,
      onProgress,
      "The browser could not read the question generation stream.",
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: QuestionAIDraftResponse | null = null;

  function handleFrame(frame: string) {
    const dataLine = frame
      .split("\n")
      .find((line) => line.startsWith("data: "));
    if (!dataLine) {
      return;
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

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      handleFrame(frame);
    }
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    handleFrame(buffer);
  }

  if (!finalResponse) {
    throw new Error("Question generation stream ended before returning a draft.");
  }
  return finalResponse;
}

export async function validateQuestionBankDraft(
  idToken: string,
  payload: QuestionDraftValidationRequest,
  signal?: AbortSignal,
): Promise<QuestionDraftValidationResponse> {
  const response = await coreApiClient.post<QuestionDraftValidationResponse>(
    "/question-bank/questions/validate-draft",
    payload,
    {
      headers: authHeader(idToken),
      signal,
    },
  );
  return response.data;
}

export async function refineQuestionBankTestCases(
  idToken: string,
  payload: QuestionDraftRefinementRequest,
  signal?: AbortSignal,
): Promise<QuestionDraftRefinementResponse> {
  const response = await coreApiClient.post<QuestionDraftRefinementResponse>(
    "/question-bank/questions/refine-test-cases",
    payload,
    {
      headers: authHeader(idToken),
      signal,
    },
  );
  return response.data;
}

export async function refineQuestionBankSolution(
  idToken: string,
  payload: QuestionDraftRefinementRequest,
  signal?: AbortSignal,
): Promise<QuestionDraftRefinementResponse> {
  const response = await coreApiClient.post<QuestionDraftRefinementResponse>(
    "/question-bank/questions/refine-solution",
    payload,
    {
      headers: authHeader(idToken),
      signal,
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
