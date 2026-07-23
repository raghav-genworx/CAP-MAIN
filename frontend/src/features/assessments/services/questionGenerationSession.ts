import type {
  QuestionAIDraftProgressEvent,
  QuestionAIDraftResponse,
  QuestionCreatePayload,
  QuestionGenerationSettings,
} from "../types/QuestionBank";

export type QuestionGenerationSettingsSnapshot = Omit<
  QuestionGenerationSettings,
  "topics" | "supported_languages"
> & {
  topics_text: string;
};

export interface QuestionGenerationSession {
  id: string;
  ownerId: string;
  questionId: string | null;
  scope: string;
  status: "running" | "completed" | "failed";
  baseDraft: QuestionCreatePayload;
  settings: QuestionGenerationSettingsSnapshot;
  events: QuestionAIDraftProgressEvent[];
  response: QuestionAIDraftResponse | null;
  error: string;
}

type Listener = (session: QuestionGenerationSession | null) => void;

let currentSession: QuestionGenerationSession | null = null;
const listeners = new Set<Listener>();

function publish() {
  listeners.forEach((listener) => listener(currentSession));
}

export function getQuestionGenerationSession() {
  return currentSession;
}

export function subscribeQuestionGenerationSession(listener: Listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function startQuestionGenerationSession(input: {
  ownerId: string;
  questionId: string | null;
  scope: string;
  baseDraft: QuestionCreatePayload;
  settings: QuestionGenerationSettingsSnapshot;
  initialEvent: QuestionAIDraftProgressEvent;
}) {
  if (currentSession) {
    throw new Error(
      currentSession.status === "running"
        ? "Another question generation is already running. Return to that question to view its live progress."
        : "A completed question generation is waiting to be restored. Return to that question before starting another run.",
    );
  }
  currentSession = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    ownerId: input.ownerId,
    questionId: input.questionId,
    scope: input.scope,
    status: "running",
    baseDraft: structuredClone(input.baseDraft),
    settings: structuredClone(input.settings),
    events: [input.initialEvent],
    response: null,
    error: "",
  };
  publish();
  return currentSession.id;
}

export function appendQuestionGenerationProgress(
  sessionId: string,
  event: QuestionAIDraftProgressEvent,
) {
  if (!currentSession || currentSession.id !== sessionId) {
    return;
  }
  currentSession = {
    ...currentSession,
    events: [...currentSession.events.slice(-119), event],
  };
  publish();
}

export function completeQuestionGenerationSession(
  sessionId: string,
  response: QuestionAIDraftResponse,
) {
  if (!currentSession || currentSession.id !== sessionId) {
    return;
  }
  currentSession = { ...currentSession, status: "completed", response };
  publish();
}

export function failQuestionGenerationSession(sessionId: string, error: string) {
  if (!currentSession || currentSession.id !== sessionId) {
    return;
  }
  currentSession = { ...currentSession, status: "failed", error };
  publish();
}

export function clearQuestionGenerationSession(sessionId: string) {
  if (!currentSession || currentSession.id !== sessionId) {
    return;
  }
  currentSession = null;
  publish();
}
