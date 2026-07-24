import { useMutation, useQuery } from "@tanstack/react-query";
import Editor from "@monaco-editor/react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Code2,
  LoaderCircle,
  Play,
  Save,
  Send,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { ApiError } from "../../../lib/axios";
import {
  fetchCandidateAssessment,
  recordCandidateProctorEvent,
  runCandidateHiddenCheck,
  runCandidateSample,
  saveCandidateCheckpoint,
  startCandidateAssessment,
  submitCandidateAssessment,
} from "../services/candidatePortalService";
import {
  clearCandidateSessionToken,
  readCandidateInviteToken,
  readCandidateSessionToken,
  saveCandidateSessionToken,
  saveSubmissionResult,
} from "../utils/sessionStorage";
import type {
  CandidateAssessmentPortal,
  CandidateExecutionCaseResult,
  CandidateSampleRunResponse,
} from "../types/CandidatePortal";

interface DraftState {
  language: string;
  source_code: string;
}

const TAB_SWITCH_LIMIT = 3;
const TAB_SWITCH_TAG = "tab_switch_lock";
const TAB_SWITCH_MESSAGE =
  "Assessment auto-submitted after 3 tab-switch warnings.";
const TIMER_EXPIRED_TAG = "timer_expired";
const TIMER_EXPIRED_MESSAGE =
  "Assessment auto-submitted because the timer reached zero.";
const FULLSCREEN_EXIT_TAG = "fullscreen_exit";
const FULLSCREEN_EXIT_MESSAGE =
  "Assessment closed because strict fullscreen mode was exited.";
const HIDDEN_CHECK_COOLDOWN_SECONDS = 5;
const TEST_RESULT_REVEAL_INTERVAL_MS = 100;
const CANDIDATE_ANSWER_VALIDATION_LABELS = {
  exact: "Exact output",
  unordered: "Order flexible",
  floating: "Numeric tolerance",
  multiple_valid: "Multiple answers",
  constructive: "Any valid construction",
} as const;

interface RunResultCase {
  index: number;
  passed: boolean;
  status: string;
  executionTime: string;
  detail: string;
  expectedOutput?: string;
  actualOutput?: string;
  errorType: string;
}

type RunResultState =
  | {
      kind: "sample";
      summary: string;
      cases: RunResultCase[];
    }
  | {
      kind: "hidden";
      summary: string;
      cases: RunResultCase[];
    }
  | null;

function formatRemainingTime(seconds: number) {
  const safeSeconds = Math.max(0, seconds);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const remainder = safeSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  }
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

function formatDateTime(value: string | null) {
  if (!value) {
    return "Not available";
  }
  return new Date(value).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function deriveRemainingSeconds(assessment: CandidateAssessmentPortal | undefined) {
  if (!assessment) {
    return 0;
  }
  if (assessment.time_remaining_seconds > 0) {
    return assessment.time_remaining_seconds;
  }
  if (!assessment.deadline_at) {
    return 0;
  }
  return Math.max(
    0,
    Math.floor((new Date(assessment.deadline_at).getTime() - Date.now()) / 1000),
  );
}

function mutationError(error: unknown) {
  return error instanceof Error ? error.message : "";
}

function formatSpecLines(value: string, fallback: string) {
  const rawLines = (value.trim() || fallback)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  return rawLines.map((line) => line.replace(/^[-*•]\s*/, ""));
}

function CandidateSpecSection({
  title,
  value,
  fallback,
  forceList = false,
}: {
  title: string;
  value: string;
  fallback: string;
  forceList?: boolean;
}) {
  const lines = formatSpecLines(value, fallback);
  return (
    <section className="candidate-problem-section candidate-spec-section">
      <h3>{title}</h3>
      {forceList || lines.length > 1 ? (
        <ul>
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : (
        <p>{lines[0]}</p>
      )}
    </section>
  );
}

function monacoLanguage(language: string) {
  const normalized = language.trim().toLowerCase();
  const languageMap: Record<string, string> = {
    "c++": "cpp",
    cplusplus: "cpp",
    cpp: "cpp",
    c: "c",
    csharp: "csharp",
    "c#": "csharp",
    java: "java",
    javascript: "javascript",
    js: "javascript",
    python: "python",
    python3: "python",
    py: "python",
    typescript: "typescript",
    ts: "typescript",
  };
  return languageMap[normalized] || normalized || "plaintext";
}

export function CandidateAssessmentPage() {
  const navigate = useNavigate();
  const [sessionToken, setSessionToken] = useState(readCandidateSessionToken);
  const [sessionWarning, setSessionWarning] = useState("");
  const [selectedQuestionId, setSelectedQuestionId] = useState<string>("");
  const [drafts, setDrafts] = useState<Record<string, DraftState>>({});
  const [runResult, setRunResult] = useState<RunResultState>(null);
  const [hiddenCheckCooldownSeconds, setHiddenCheckCooldownSeconds] = useState(0);
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
  const [displayRemainingSeconds, setDisplayRemainingSeconds] = useState(0);
  const [tabSwitchWarnings, setTabSwitchWarnings] = useState(0);
  const [proctorMessage, setProctorMessage] = useState("");
  const [resultsExpanded, setResultsExpanded] = useState(false);
  const [submittedQuestionIds, setSubmittedQuestionIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [questionOutcomes, setQuestionOutcomes] = useState<
    Record<string, "passed" | "failed">
  >({});
  const [showSubmitAssessmentDialog, setShowSubmitAssessmentDialog] =
    useState(false);
  const [finalSubmitConfirmation, setFinalSubmitConfirmation] = useState("");
  const [fullscreenPromptVisible, setFullscreenPromptVisible] = useState(false);
  const [questionTimeSpentSeconds, setQuestionTimeSpentSeconds] = useState<
    Record<string, number>
  >({});
  const submitOnceRef = useRef(false);
  const fullscreenAttemptedRef = useRef(false);
  const hasEnteredFullscreenRef = useRef(false);
  const tabSwitchCountRef = useRef(0);
  const clipboardCountRef = useRef(0);
  const fullscreenExitCountRef = useRef(0);
  const questionTimeSpentRef = useRef<Record<string, number>>({});
  const evidenceAssignmentRef = useRef("");
  const hasReceivedPositiveTimerRef = useRef(false);
  const latestDraftsRef = useRef<Record<string, DraftState>>({});
  const draftVersionsRef = useRef<Record<string, number>>({});
  const selectedQuestionIdRef = useRef("");
  const assessmentQuestionsRef = useRef<CandidateAssessmentPortal["questions"]>([]);
  const autosaveInFlightRef = useRef(false);
  const restoredResultQuestionRef = useRef("");
  const timerSyncRef = useRef({
    serverRemainingSeconds: 0,
    syncedAtMs: Date.now(),
    paused: false,
  });

  const assessmentQuery = useQuery({
    queryKey: ["candidate-assessment", sessionToken],
    queryFn: async () => {
      try {
        return await fetchCandidateAssessment(sessionToken || "");
      } catch (error) {
        const inviteToken = readCandidateInviteToken();
        if (!(error instanceof ApiError) || error.status !== 401 || !inviteToken) {
          throw error;
        }
        setSessionWarning("Your session expired. Reconnecting to your saved assessment...");
        const refreshed = await startCandidateAssessment(inviteToken);
        saveCandidateSessionToken(refreshed.session_token);
        setSessionToken(refreshed.session_token);
        const assessment = await fetchCandidateAssessment(refreshed.session_token);
        setSessionWarning("Session restored. Your saved work is available.");
        return assessment;
      }
    },
    enabled: Boolean(sessionToken),
    refetchInterval: 15000,
  });

  latestDraftsRef.current = drafts;
  selectedQuestionIdRef.current = selectedQuestionId;
  assessmentQuestionsRef.current = assessmentQuery.data?.questions || [];
  questionTimeSpentRef.current = questionTimeSpentSeconds;

  const persistProctorEvent = useCallback(
    async (
      eventType: "tab_hidden" | "window_blur" | "clipboard" | "fullscreen_exit",
    ) => {
      if (!sessionToken) {
        return null;
      }
      const eventId =
        typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      try {
        const totals = await recordCandidateProctorEvent(sessionToken, {
          client_event_id: eventId,
          event_type: eventType,
          occurred_at: new Date().toISOString(),
        });
        tabSwitchCountRef.current = totals.tab_switch_count;
        clipboardCountRef.current = totals.copy_paste_count;
        fullscreenExitCountRef.current = totals.fullscreen_exit_count;
        setTabSwitchWarnings(Math.min(totals.tab_switch_count, TAB_SWITCH_LIMIT));
        return totals;
      } catch {
        setProctorMessage(
          "A proctoring event could not be synchronized. Check your connection.",
        );
        return null;
      }
    },
    [sessionToken],
  );

  useEffect(() => {
    if (!sessionToken) {
      navigate("/candidate/submitted", { replace: true });
    }
  }, [navigate, sessionToken]);

  useEffect(() => {
    if (hiddenCheckCooldownSeconds <= 0) {
      return;
    }
    const timer = window.setTimeout(() => {
      setHiddenCheckCooldownSeconds((current) => Math.max(0, current - 1));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [hiddenCheckCooldownSeconds]);

  useEffect(() => {
    const assessment = assessmentQuery.data;
    if (!assessment) {
      return;
    }
    if (!selectedQuestionId && assessment.questions.length) {
      const currentQuestion =
        assessment.questions.find(
          (question) => question.question_order === assessment.current_question_order,
        ) || assessment.questions[0];
      setSelectedQuestionId(currentQuestion.id);
    }
    setDrafts((current) => {
      const next = { ...current };
      assessment.questions.forEach((question) => {
        const savedDraft = assessment.drafts.find(
          (draft) => draft.question_id === question.id,
        );
        if (!next[question.id]) {
          next[question.id] = {
            language:
              savedDraft?.source_language ||
              question.supported_languages[0] ||
              "python",
            source_code: savedDraft?.draft_code || "",
          };
          draftVersionsRef.current[question.id] = savedDraft?.version || 0;
        } else if (
          savedDraft &&
          savedDraft.version > (draftVersionsRef.current[question.id] || 0)
        ) {
          if (next[question.id].source_code === savedDraft.draft_code) {
            draftVersionsRef.current[question.id] = savedDraft.version;
          } else {
            setSessionWarning(
              `Question ${question.question_order} changed in another tab. Reload before saving it.`,
            );
          }
        }
      });
      return next;
    });
  }, [assessmentQuery.data, selectedQuestionId]);

  useEffect(() => {
    const assessment = assessmentQuery.data;
    const assessmentId = assessment?.candidate_assessment_id;
    if (!assessmentId || evidenceAssignmentRef.current === assessmentId) {
      return;
    }
    evidenceAssignmentRef.current = assessmentId;
    tabSwitchCountRef.current = assessment.tab_switch_count || 0;
    clipboardCountRef.current = assessment.copy_paste_count || 0;
    fullscreenExitCountRef.current = assessment.fullscreen_exit_count || 0;
    setTabSwitchWarnings(Math.min(assessment.tab_switch_count || 0, TAB_SWITCH_LIMIT));
    const storageKey = `candidate-question-time-${assessmentId}`;
    let storedTimes: Record<string, number> = {};
    try {
      const stored = window.localStorage.getItem(storageKey);
      if (stored) {
        storedTimes = JSON.parse(stored) as Record<string, number>;
      }
    } catch {
      storedTimes = {};
    }
    const mergedTimes = { ...assessment.question_time_seconds };
    Object.entries(storedTimes).forEach(([questionId, seconds]) => {
      mergedTimes[questionId] = Math.max(mergedTimes[questionId] || 0, seconds);
    });
    questionTimeSpentRef.current = mergedTimes;
    setQuestionTimeSpentSeconds(mergedTimes);
  }, [assessmentQuery.data]);

  useEffect(() => {
    if (!selectedQuestionId || restoredResultQuestionRef.current === selectedQuestionId) {
      return;
    }
    restoredResultQuestionRef.current = selectedQuestionId;
    const saved = assessmentQuery.data?.drafts.find(
      (draft) => draft.question_id === selectedQuestionId,
    )?.sample_run_result;
    if (!saved?.results?.length) {
      setRunResult(null);
      return;
    }
    const results = saved.results as CandidateExecutionCaseResult[];
    setRunResult({
      kind: "sample",
      summary: `${saved.passed_count || 0}/${saved.total_count || results.length} sample cases passed`,
      cases: results.map((item) => ({
        index: item.index,
        passed: item.passed,
        status: item.status,
        executionTime: item.execution_time,
        detail:
          item.actual_output ||
          item.stderr ||
          item.compile_output ||
          item.checker_message ||
          item.message,
        expectedOutput: item.expected_output,
        actualOutput: item.actual_output,
        errorType: item.passed ? "" : item.status || "Execution failed",
      })),
    });
    setResultsExpanded(true);
  }, [assessmentQuery.data?.drafts, selectedQuestionId]);

  const selectedQuestion = useMemo(
    () =>
      assessmentQuery.data?.questions.find((question) => question.id === selectedQuestionId) ||
      assessmentQuery.data?.questions[0] ||
      null,
    [assessmentQuery.data?.questions, selectedQuestionId],
  );
  const selectedDraft = selectedQuestion ? drafts[selectedQuestion.id] : null;
  const attemptedQuestionIds = useMemo(
    () =>
      new Set(
        Object.entries(drafts)
          .filter(([, draft]) => draft.source_code.trim().length > 0)
          .map(([questionId]) => questionId),
      ),
    [drafts],
  );
  const submittedQuestionCount = submittedQuestionIds.size;
  const answeredQuestionCount = attemptedQuestionIds.size;
  const progressPercent = Math.round(
    (answeredQuestionCount / Math.max(assessmentQuery.data?.questions.length || 1, 1)) *
      100,
  );
  const totalDurationSeconds = (assessmentQuery.data?.duration_minutes || 0) * 60;
  const timeTakenSeconds =
    totalDurationSeconds > 0
      ? Math.max(0, totalDurationSeconds - displayRemainingSeconds)
      : assessmentQuery.data?.started_at
        ? Math.max(
            0,
            Math.floor(
              (Date.now() - new Date(assessmentQuery.data.started_at).getTime()) /
                1000,
            ),
          )
        : 0;
  const trackedQuestionTimeSeconds = Object.values(questionTimeSpentSeconds).reduce(
    (sum, value) => sum + value,
    0,
  );
  const requiresEndConfirmation =
    totalDurationSeconds > 0 &&
    displayRemainingSeconds > Math.floor(totalDurationSeconds * 0.5);
  const questionSubmissionSummary =
    assessmentQuery.data?.questions.map((question) => {
      const draft = drafts[question.id];
      const serverDraft = assessmentQuery.data?.drafts.find(
        (item) => item.question_id === question.id,
      );
      const sourceCode = draft?.source_code || serverDraft?.draft_code || "";
      const lineCount = sourceCode.trim()
        ? sourceCode.trim().split(/\r?\n/).length
        : 0;
      const isSubmitted =
        submittedQuestionIds.has(question.id) ||
        Boolean(serverDraft?.submitted_at) ||
        serverDraft?.status === "submitted";
      const currentSampleCases =
        runResult?.kind === "sample" && question.id === selectedQuestion?.id
          ? runResult.cases
          : [];
      const samplePassed = currentSampleCases.filter((item) => item.passed).length;
      const sampleTotal = currentSampleCases.length;
      const answerSignal = !sourceCode.trim()
        ? 0
        : isSubmitted
          ? sampleTotal
            ? Math.min(100, 70 + Math.round((samplePassed / sampleTotal) * 30))
            : 82
          : sampleTotal
            ? Math.min(88, 45 + Math.round((samplePassed / sampleTotal) * 35))
            : Math.min(75, 35 + Math.min(lineCount, 40));

      return {
        question,
        sourceCode,
        lineCount,
        timeSpentSeconds: questionTimeSpentSeconds[question.id] || 0,
        language:
          draft?.language ||
          serverDraft?.source_language ||
          question.supported_languages[0] ||
          "python",
        isAttempted: sourceCode.trim().length > 0,
        isSubmitted,
        lastSavedAt: serverDraft?.last_saved_at || null,
        submittedAt: serverDraft?.submitted_at || null,
        samplePassed,
        sampleTotal,
        answerSignal,
      };
    }) || [];
  const mandatoryUnansweredCount = questionSubmissionSummary.filter(
    (item) => item.question.is_mandatory && !item.isAttempted,
  ).length;
  const unansweredCount = questionSubmissionSummary.filter(
    (item) => !item.isAttempted,
  ).length;

  const revealTestCaseResults = useCallback(
    async (
      kind: "sample" | "hidden",
      finalSummary: string,
      cases: RunResultCase[],
    ) => {
      setRunResult({
        kind,
        summary: `0/${cases.length} test cases completed`,
        cases: [],
      });
      for (let index = 0; index < cases.length; index += 1) {
        await new Promise((resolve) =>
          window.setTimeout(resolve, TEST_RESULT_REVEAL_INTERVAL_MS),
        );
        setRunResult({
          kind,
          summary: `${index + 1}/${cases.length} test cases completed`,
          cases: cases.slice(0, index + 1),
        });
      }
      setRunResult({ kind, summary: finalSummary, cases });
    },
    [],
  );

  const checkpointMutation = useMutation({
    mutationFn: async ({
      questionId,
      sourceCode,
      language,
      currentQuestionOrder,
    }: {
      questionId: string;
      sourceCode: string;
      language: string;
      currentQuestionOrder: number;
    }) =>
      saveCandidateCheckpoint(sessionToken || "", {
        question_id: questionId,
        source_code: sourceCode,
        language,
        current_question_order: currentQuestionOrder,
        tab_switch_count: tabSwitchCountRef.current,
        copy_paste_count: clipboardCountRef.current,
        fullscreen_exit_count: fullscreenExitCountRef.current,
        question_time_seconds: questionTimeSpentRef.current,
        base_version: draftVersionsRef.current[questionId] || 0,
      }),
    onSuccess: (data, variables) => {
      draftVersionsRef.current[variables.questionId] = data.version;
      setLastSavedAt(data.saved_at);
    },
  });

  const sampleMutation = useMutation({
    mutationFn: async ({
      questionId,
      sourceCode,
      language,
    }: {
      questionId: string;
      sourceCode: string;
      language: string;
    }) => {
      setResultsExpanded(true);
      setRunResult({
        kind: "sample",
        summary: "Executing sample test cases...",
        cases: [],
      });
      return runCandidateSample(sessionToken || "", {
        question_id: questionId,
        source_code: sourceCode,
        language,
        base_version: draftVersionsRef.current[questionId] || 0,
      });
    },
    onSuccess: (data: CandidateSampleRunResponse, variables) => {
      draftVersionsRef.current[variables.questionId] = data.version;
      const cases = data.results.map((item: CandidateExecutionCaseResult) => ({
          index: item.index,
          passed: item.passed,
          status: item.status,
          executionTime: item.execution_time,
          detail:
            item.actual_output ||
            item.stderr ||
            item.compile_output ||
            item.checker_message ||
            item.message,
          expectedOutput: item.expected_output,
          actualOutput: item.actual_output,
          errorType: item.passed ? "" : item.status || "Execution failed",
        }));
      void revealTestCaseResults(
        "sample",
        `${data.passed_count}/${data.total_count} sample cases passed`,
        cases,
      );
    },
  });

  const hiddenCheckMutation = useMutation({
    mutationFn: async ({
      questionId,
      sourceCode,
      language,
    }: {
      questionId: string;
      sourceCode: string;
      language: string;
    }) => {
      setResultsExpanded(true);
      setRunResult({
        kind: "hidden",
        summary: "Executing hidden test cases...",
        cases: [],
      });
      return runCandidateHiddenCheck(sessionToken || "", {
        question_id: questionId,
        source_code: sourceCode,
        language,
        base_version: draftVersionsRef.current[questionId] || 0,
      });
    },
    onSuccess: (data, variables) => {
      draftVersionsRef.current[variables.questionId] = data.version;
      setHiddenCheckCooldownSeconds(
        data.cooldown_remaining_seconds || HIDDEN_CHECK_COOLDOWN_SECONDS,
      );
      const cases = data.results.map((item) => ({
          index: item.index,
          passed: item.passed,
          status: item.status,
          executionTime: item.execution_time,
          detail: "",
          errorType: item.error_type,
        }));
      void revealTestCaseResults(
        "hidden",
        `${data.passed_count}/${data.total_count} hidden test cases passed`,
        cases,
      );
      setQuestionOutcomes((current) => ({
        ...current,
        [variables.questionId]:
          data.total_count > 0 && data.passed_count === data.total_count
            ? "passed"
            : "failed",
      }));
    },
  });

  const submitMutation = useMutation({
    mutationFn: async ({
      auto,
      submissionTag,
      submissionMessage,
    }: {
      auto: boolean;
      submissionTag?: string;
      submissionMessage?: string;
    }) => {
      if (!assessmentQuery.data || !sessionToken) {
        throw new Error("Assessment session is not available.");
      }
      const answers = assessmentQuery.data.questions.map((question) => ({
        question_id: question.id,
        source_code: latestDraftsRef.current[question.id]?.source_code || "",
        language:
          latestDraftsRef.current[question.id]?.language ||
          question.supported_languages[0] ||
          "python",
      }));
      const response = await submitCandidateAssessment(sessionToken, {
        answers,
        auto_submit: auto,
        submission_tag: submissionTag || "",
        submission_message: submissionMessage || "",
        tab_switch_count: tabSwitchCountRef.current,
        copy_paste_count: clipboardCountRef.current,
        fullscreen_exit_count: fullscreenExitCountRef.current,
        question_time_seconds: questionTimeSpentRef.current,
      });
      return {
        ...response,
        auto,
        submission_tag: response.submission_tag || submissionTag || "",
        submission_message: response.submission_message || submissionMessage || "",
      };
    },
    onSuccess: (response) => {
      saveSubmissionResult(response);
      clearCandidateSessionToken();
      navigate("/candidate/submitted");
    },
  });

  const submitAutomatically = useCallback(
    (submissionTag: string, submissionMessage: string) => {
      if (submitOnceRef.current || submitMutation.isPending) {
        return;
      }
      submitOnceRef.current = true;
      setProctorMessage(submissionMessage);
      submitMutation.mutate({
        auto: true,
        submissionTag,
        submissionMessage,
      });
    },
    [submitMutation],
  );

  const saveSelectedQuestion = useCallback(() => {
    if (!selectedQuestion || !selectedDraft) {
      return;
    }
    void checkpointMutation.mutateAsync({
      questionId: selectedQuestion.id,
      sourceCode: selectedDraft.source_code,
      language: selectedDraft.language,
      currentQuestionOrder: selectedQuestion.question_order,
    });
  }, [checkpointMutation, selectedDraft, selectedQuestion]);

  const submitSelectedQuestion = useCallback(async () => {
    if (!selectedQuestion || !selectedDraft) {
      return;
    }
    await checkpointMutation.mutateAsync({
      questionId: selectedQuestion.id,
      sourceCode: selectedDraft.source_code,
      language: selectedDraft.language,
      currentQuestionOrder: selectedQuestion.question_order,
    });
    await hiddenCheckMutation.mutateAsync({
      questionId: selectedQuestion.id,
      sourceCode: selectedDraft.source_code,
      language: selectedDraft.language,
    });
    setSubmittedQuestionIds((current) => {
      const next = new Set(current);
      next.add(selectedQuestion.id);
      return next;
    });
  }, [checkpointMutation, hiddenCheckMutation, selectedDraft, selectedQuestion]);

  function moveToQuestion(questionId: string) {
    saveSelectedQuestion();
    setRunResult(null);
    setResultsExpanded(false);
    setSelectedQuestionId(questionId);
  }

  function requestFinalSubmit() {
    setFinalSubmitConfirmation("");
    setShowSubmitAssessmentDialog(true);
  }

  function confirmFinalSubmit() {
    if (
      requiresEndConfirmation &&
      finalSubmitConfirmation.trim().toLowerCase() !== "end"
    ) {
      return;
    }
    submitMutation.mutate({ auto: false });
  }

  const syncedRemainingSeconds = useCallback(() => {
    if (timerSyncRef.current.paused) {
      return timerSyncRef.current.serverRemainingSeconds;
    }
    const elapsedSeconds = Math.floor(
      (Date.now() - timerSyncRef.current.syncedAtMs) / 1000,
    );
    return Math.max(
      0,
      timerSyncRef.current.serverRemainingSeconds - elapsedSeconds,
    );
  }, []);

  const autosaveAssessmentId = assessmentQuery.data?.candidate_assessment_id;
  const autosaveSlotStatus = assessmentQuery.data?.slot_status;
  useEffect(() => {
    if (!autosaveAssessmentId || autosaveSlotStatus === "paused") {
      return;
    }
    const interval = window.setInterval(() => {
      const questionId = selectedQuestionIdRef.current;
      const draft = latestDraftsRef.current[questionId];
      const question = assessmentQuestionsRef.current.find((item) => item.id === questionId);
      if (!sessionToken || !draft || !question || autosaveInFlightRef.current) {
        return;
      }
      autosaveInFlightRef.current = true;
      void saveCandidateCheckpoint(sessionToken, {
        question_id: questionId,
        source_code: draft.source_code,
        language: draft.language,
        current_question_order: question.question_order,
        base_version: draftVersionsRef.current[questionId] || 0,
        tab_switch_count: tabSwitchCountRef.current,
        copy_paste_count: clipboardCountRef.current,
        fullscreen_exit_count: fullscreenExitCountRef.current,
        question_time_seconds: questionTimeSpentRef.current,
      })
        .then((result) => {
          draftVersionsRef.current[questionId] = result.version;
          setLastSavedAt(result.saved_at);
        })
        .catch((error: unknown) => {
          setSessionWarning(
            error instanceof Error ? error.message : "Autosave failed. Please retry.",
          );
        })
        .finally(() => {
          autosaveInFlightRef.current = false;
        });
    }, 15000);
    return () => window.clearInterval(interval);
  }, [autosaveAssessmentId, autosaveSlotStatus, sessionToken]);

  useEffect(() => {
    if (!assessmentQuery.data || !selectedQuestionId || submitMutation.isPending) {
      return;
    }
    const interval = window.setInterval(() => {
      if (document.visibilityState === "hidden") {
        return;
      }
      setQuestionTimeSpentSeconds((current) => ({
        ...current,
        [selectedQuestionId]: (current[selectedQuestionId] || 0) + 1,
      }));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [assessmentQuery.data, selectedQuestionId, submitMutation.isPending]);

  useEffect(() => {
    const assessmentId = assessmentQuery.data?.candidate_assessment_id;
    if (!assessmentId) {
      return;
    }
    window.localStorage.setItem(
      `candidate-question-time-${assessmentId}`,
      JSON.stringify(questionTimeSpentSeconds),
    );
  }, [assessmentQuery.data?.candidate_assessment_id, questionTimeSpentSeconds]);

  useEffect(() => {
    const assessment = assessmentQuery.data;
    if (!assessment) {
      return;
    }
    const serverSubmittedIds = assessment.drafts
      .filter(
        (draft) =>
          draft.submitted_at ||
          draft.status === "submitted" ||
          Number(draft.hidden_check_result.total_count || 0) > 0,
      )
      .map((draft) => draft.question_id);
    if (!serverSubmittedIds.length) {
      return;
    }
    setSubmittedQuestionIds((current) => {
      const next = new Set(current);
      serverSubmittedIds.forEach((questionId) => next.add(questionId));
      return next;
    });
    setQuestionOutcomes((current) => {
      const next = { ...current };
      assessment.drafts.forEach((draft) => {
        const check = draft.hidden_check_result;
        const finalResult = draft.submission_result;
        const total = Number(finalResult.total_count || check.total_count || 0);
        const passed = Number(finalResult.passed_count || check.passed_count || 0);
        if (total > 0) {
          next[draft.question_id] = passed === total ? "passed" : "failed";
        }
      });
      return next;
    });
  }, [assessmentQuery.data]);

  useEffect(() => {
    const assessment = assessmentQuery.data;
    if (
      !assessment ||
      assessment.proctoring_mode !== "strict" ||
      fullscreenAttemptedRef.current
    ) {
      return;
    }
    fullscreenAttemptedRef.current = true;
    if (document.fullscreenElement) {
      hasEnteredFullscreenRef.current = true;
      setFullscreenPromptVisible(false);
      return;
    }
    setFullscreenPromptVisible(true);
  }, [assessmentQuery.data]);

  useEffect(() => {
    if (assessmentQuery.data?.proctoring_mode !== "strict") {
      return;
    }

    async function handleFullscreenChange() {
      if (document.fullscreenElement) {
        hasEnteredFullscreenRef.current = true;
        setFullscreenPromptVisible(false);
        return;
      }
      if (hasEnteredFullscreenRef.current) {
        await persistProctorEvent("fullscreen_exit");
        submitAutomatically(FULLSCREEN_EXIT_TAG, FULLSCREEN_EXIT_MESSAGE);
      } else {
        setFullscreenPromptVisible(true);
      }
    }

    const onFullscreenChange = () => void handleFullscreenChange();
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () =>
      document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, [assessmentQuery.data?.proctoring_mode, persistProctorEvent, submitAutomatically]);

  useEffect(() => {
    if (!proctorMessage || submitMutation.isPending) {
      return;
    }
    const timeout = window.setTimeout(() => setProctorMessage(""), 6000);
    return () => window.clearTimeout(timeout);
  }, [proctorMessage, submitMutation.isPending]);

  useEffect(() => {
    const serverRemainingSeconds = deriveRemainingSeconds(assessmentQuery.data);
    if (serverRemainingSeconds > 0) {
      hasReceivedPositiveTimerRef.current = true;
    }
    timerSyncRef.current = {
      serverRemainingSeconds,
      syncedAtMs: Date.now(),
      paused: assessmentQuery.data?.slot_status === "paused",
    };
    setDisplayRemainingSeconds(Math.max(0, serverRemainingSeconds));
  }, [assessmentQuery.data]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setDisplayRemainingSeconds(syncedRemainingSeconds());
    }, 1000);
    return () => window.clearInterval(interval);
  }, [syncedRemainingSeconds]);

  useEffect(() => {
    if (
      !assessmentQuery.data ||
      submitOnceRef.current ||
      !hasReceivedPositiveTimerRef.current
    ) {
      return;
    }
    if (syncedRemainingSeconds() <= 0) {
      submitAutomatically(TIMER_EXPIRED_TAG, TIMER_EXPIRED_MESSAGE);
    }
  }, [
    assessmentQuery.data,
    displayRemainingSeconds,
    submitAutomatically,
    syncedRemainingSeconds,
  ]);

  useEffect(() => {
    if (
      !assessmentQuery.data ||
      assessmentQuery.data.proctoring_mode === "none"
    ) {
      return;
    }

    let countedHiddenState = document.visibilityState === "hidden";

    async function recordTabSwitchWarning(eventType: "tab_hidden" | "window_blur") {
      if (submitOnceRef.current) {
        return;
      }
      const totals = await persistProctorEvent(eventType);
      if (!totals) {
        return;
      }
      setTabSwitchWarnings(() => {
        const next = Math.min(totals.tab_switch_count, TAB_SWITCH_LIMIT);
        if (next >= TAB_SWITCH_LIMIT) {
          submitAutomatically(TAB_SWITCH_TAG, TAB_SWITCH_MESSAGE);
          return next;
        }
        setProctorMessage(
          `Tab switch detected. Warning ${next}/${TAB_SWITCH_LIMIT}. Your assessment will auto-submit after ${TAB_SWITCH_LIMIT} warnings.`,
        );
        return next;
      });
    }

    function handleVisibilityChange() {
      if (document.visibilityState === "hidden") {
        if (!countedHiddenState) {
          countedHiddenState = true;
          void recordTabSwitchWarning("tab_hidden");
        }
        return;
      }
      countedHiddenState = false;
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [assessmentQuery.data, persistProctorEvent, submitAutomatically]);

  useEffect(() => {
    if (!assessmentQuery.data || assessmentQuery.data.proctoring_mode === "none") {
      return;
    }
    let lostFocus = false;
    const handleBlur = () => {
      if (document.visibilityState === "visible" && !lostFocus) {
        lostFocus = true;
        void persistProctorEvent("window_blur").then((totals) => {
          if (!totals) return;
          const next = Math.min(totals.tab_switch_count, TAB_SWITCH_LIMIT);
          setTabSwitchWarnings(next);
          if (next >= TAB_SWITCH_LIMIT) {
            submitAutomatically(TAB_SWITCH_TAG, TAB_SWITCH_MESSAGE);
          } else {
            setProctorMessage(
              `Window focus lost. Warning ${next}/${TAB_SWITCH_LIMIT}.`,
            );
          }
        });
      }
    };
    const handleFocus = () => {
      lostFocus = false;
    };
    window.addEventListener("blur", handleBlur);
    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener("blur", handleBlur);
      window.removeEventListener("focus", handleFocus);
    };
  }, [assessmentQuery.data, persistProctorEvent, submitAutomatically]);

  useEffect(() => {
    const mode = assessmentQuery.data?.proctoring_mode;
    if (!mode || mode === "none") {
      return;
    }

    function handleClipboard(event: ClipboardEvent) {
      void persistProctorEvent("clipboard");
      if (mode === "strict") {
        event.preventDefault();
      }
      setProctorMessage(
        mode === "strict"
          ? "Copy, cut, and paste are disabled for this strictly monitored assessment."
          : "Clipboard activity detected and recorded by assessment monitoring.",
      );
    }

    document.addEventListener("copy", handleClipboard, true);
    document.addEventListener("cut", handleClipboard, true);
    document.addEventListener("paste", handleClipboard, true);
    return () => {
      document.removeEventListener("copy", handleClipboard, true);
      document.removeEventListener("cut", handleClipboard, true);
      document.removeEventListener("paste", handleClipboard, true);
    };
  }, [assessmentQuery.data?.proctoring_mode, persistProctorEvent]);

  if (!assessmentQuery.data || !selectedQuestion || !selectedDraft) {
    return (
      <main className="candidate-shell candidate-shell-branded">
        <Card className="candidate-card candidate-status-card">
          <span className="candidate-kicker">Assessment Portal</span>
          <h1>Preparing your workspace</h1>
          <p>We are loading your questions, saved drafts, and timer.</p>
        </Card>
      </main>
    );
  }

  const assessment = assessmentQuery.data;
  const isPaused = assessment.slot_status === "paused";
  const isActionBusy =
    isPaused ||
    checkpointMutation.isPending ||
    sampleMutation.isPending ||
    hiddenCheckMutation.isPending ||
    submitMutation.isPending;
  const isSelectedQuestionSubmitted = submittedQuestionIds.has(selectedQuestion.id);
  const selectedQuestionIndex = assessment.questions.findIndex(
    (question) => question.id === selectedQuestion.id,
  );
  const nextQuestion =
    selectedQuestionIndex >= 0
      ? assessment.questions[selectedQuestionIndex + 1] || null
      : null;
  const warningTooltip =
    proctorMessage ||
    (assessment.proctoring_mode === "none"
      ? "No proctoring warnings are active."
      : `${tabSwitchWarnings}/${TAB_SWITCH_LIMIT} tab-switch warnings recorded. The assessment auto-submits at ${TAB_SWITCH_LIMIT}.`);
  const isTestRunning = sampleMutation.isPending || hiddenCheckMutation.isPending;
  const resultTone = isTestRunning
    ? "is-running"
    : runResult?.cases.length
      ? runResult.cases.every((testCase) => testCase.passed)
        ? "is-passed"
        : "is-failed"
      : "is-idle";

  return (
    <main className="candidate-portal candidate-portal-pro">
      <aside className="candidate-questions-panel">
        <div className="candidate-sidebar-header">
          <span className="candidate-kicker">Live Assessment</span>
          <h2>{assessment.assessment_title}</h2>
          <p>{assessment.slot_title}</p>
        </div>

        <div className="candidate-progress">
          <span>
            {attemptedQuestionIds.size}/{assessment.questions.length} questions touched
          </span>
          <div>
            <span
              style={{
                width: `${Math.round(
                  (attemptedQuestionIds.size / Math.max(assessment.questions.length, 1)) *
                    100,
                )}%`,
              }}
            />
          </div>
        </div>

        <div className="candidate-question-nav">
          {assessment.questions.map((question) => {
            const isAttempted = attemptedQuestionIds.has(question.id);
            return (
              <button
                key={question.id}
                type="button"
                className={`candidate-question-button ${
                  selectedQuestion.id === question.id ? "is-selected" : ""
                } ${
                  submittedQuestionIds.has(question.id)
                    ? `is-submitted is-${questionOutcomes[question.id] || "failed"}`
                    : ""
                }`}
                onClick={() => moveToQuestion(question.id)}
              >
                <span>Question {question.question_order}</span>
                <strong>{question.title}</strong>
                <em>
                  {submittedQuestionIds.has(question.id)
                    ? questionOutcomes[question.id] === "passed"
                      ? "Submitted - passed"
                      : "Submitted - needs work"
                    : isAttempted
                      ? "Draft saved locally"
                      : "Not attempted"}
                </em>
              </button>
            );
          })}
        </div>
      </aside>

      <section className="candidate-workspace">
        {sessionWarning ? (
          <span className="candidate-proctor-live-message" role="status">
            {sessionWarning}
          </span>
        ) : null}
        {proctorMessage ? (
          <span className="candidate-proctor-live-message" role="status">
            {proctorMessage}
          </span>
        ) : null}

        {isPaused ? (
          <div className="candidate-security-gate" role="status">
            <div className="candidate-fullscreen-prompt">
              <Clock3 size={18} aria-hidden="true" />
              <div>
                <strong>Assessment paused</strong>
                <p>Your timer is frozen. Work can resume when the recruiter continues the slot.</p>
              </div>
            </div>
          </div>
        ) : null}

        {fullscreenPromptVisible ? (
          <div className="candidate-security-gate" role="dialog" aria-modal="true">
            <div className="candidate-fullscreen-prompt">
            <ShieldCheck size={18} aria-hidden="true" />
            <div>
              <strong>Strict fullscreen is required</strong>
              <p>This assessment cannot continue outside fullscreen mode.</p>
            </div>
            <Button
              type="button"
              variant="secondary"
              onClick={() =>
                void document.documentElement
                  .requestFullscreen()
                  .then(() => {
                    hasEnteredFullscreenRef.current = true;
                    setFullscreenPromptVisible(false);
                  })
              }
            >
              Enter Fullscreen
            </Button>
            </div>
          </div>
        ) : null}

        <div className="candidate-topbar">
          <div className="candidate-topbar-question">
            <span>
              Question {selectedQuestion.question_order} of {assessment.questions.length}
            </span>
            <strong>{selectedQuestion.title}</strong>
          </div>
          <div className="candidate-topbar-person">
            <span>Candidate</span>
            <strong>{assessment.candidate_name}</strong>
          </div>
          <div
            className={`candidate-topbar-timer ${
              displayRemainingSeconds <= 300 ? "is-critical" : ""
            }`}
          >
            <Clock3 size={18} aria-hidden="true" />
            <div>
              <span>Time remaining</span>
              <strong>{formatRemainingTime(displayRemainingSeconds)}</strong>
            </div>
          </div>
          <button
            type="button"
            className={`candidate-warning-counter ${
              tabSwitchWarnings ? "has-warnings" : ""
            }`}
            aria-label={`Proctoring warnings: ${tabSwitchWarnings}`}
            data-tooltip={warningTooltip}
          >
            <AlertTriangle size={18} aria-hidden="true" />
            <strong>{tabSwitchWarnings}</strong>
          </button>
          <Button
            type="button"
            className="candidate-topbar-submit"
            onClick={requestFinalSubmit}
            disabled={submitMutation.isPending}
          >
            <Send size={16} aria-hidden="true" />
            Submit Assessment
          </Button>
        </div>

        <div className="candidate-workbench">
          <Card className="candidate-problem-card">
            <div className="candidate-problem-scroll">
              <div className="candidate-problem-header">
                <div>
                  <span className="candidate-kicker">
                    {selectedQuestion.difficulty} · {selectedQuestion.marks} marks
                  </span>
                  <h1>{selectedQuestion.title}</h1>
                </div>
                <div className="candidate-problem-badges">
                  <span
                    className={`candidate-answer-checker ${
                      selectedQuestion.answer_validation_mode !== "exact"
                        ? "is-highlighted"
                        : ""
                    }`}
                    title={selectedQuestion.output_checker_explanation}
                  >
                    <CheckCircle2 size={14} aria-hidden="true" />
                    {
                      CANDIDATE_ANSWER_VALIDATION_LABELS[
                        selectedQuestion.answer_validation_mode
                      ]
                    }
                  </span>
                  {selectedQuestion.is_mandatory ? (
                    <span className="status-badge status-info">mandatory</span>
                  ) : null}
                </div>
              </div>

              <section className="candidate-problem-section">
                <h3>Problem</h3>
                <p>{selectedQuestion.problem_statement}</p>
              </section>
              <CandidateSpecSection
                title="Input Format"
                value={selectedQuestion.input_format}
                fallback="Input format is included in the problem statement."
              />
              <CandidateSpecSection
                title="Output Format"
                value={selectedQuestion.output_format}
                fallback="Print the required answer only."
              />
              <CandidateSpecSection
                title="Constraints"
                value={selectedQuestion.constraints}
                fallback="Use an efficient approach for the stated limits."
                forceList
              />

              <div className="candidate-sample-grid">
                {selectedQuestion.sample_test_cases.map((testCase, index) => (
                  <article key={`${selectedQuestion.id}-${index}`}>
                    <strong>Sample {index + 1}</strong>
                    <span>Input</span>
                    <pre>{testCase.input}</pre>
                    <span>Expected Output</span>
                    <pre>{testCase.expected_output}</pre>
                  </article>
                ))}
              </div>
            </div>
          </Card>

          <Card className="candidate-editor-card">
            <div className="candidate-editor-header">
              <div>
                <span className="candidate-kicker">
                  <Code2 size={14} aria-hidden="true" />
                  Code workspace
                </span>
                <h2>Solution editor</h2>
                <p>
                  {checkpointMutation.isPending
                    ? "Saving..."
                    : lastSavedAt
                      ? `Last saved ${formatDateTime(lastSavedAt)}`
                      : "Autosaves every 15 seconds"}
                </p>
              </div>
              <label className="field">
                <span>Language</span>
                <select
                  value={selectedDraft.language}
                  onChange={(event) =>
                    setDrafts((current) => ({
                      ...current,
                      [selectedQuestion.id]: {
                        ...current[selectedQuestion.id],
                        language: event.target.value,
                      },
                    }))
                  }
                >
                  {selectedQuestion.supported_languages.map((language) => (
                    <option key={language} value={language}>
                      {language}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {isSelectedQuestionSubmitted ? (
              <div className="candidate-question-submitted-note">
                <CheckCircle2 size={18} aria-hidden="true" />
                <div>
                  <strong>This question is marked submitted.</strong>
                  <p>You can still edit and resubmit before final assessment submission.</p>
                </div>
              </div>
            ) : null}

            <div className="candidate-monaco-shell">
              <Editor
                height="100%"
                language={monacoLanguage(selectedDraft.language)}
                theme="vs-dark"
                value={selectedDraft.source_code}
                loading={
                  <div className="candidate-editor-loading">Loading editor...</div>
                }
                options={{
                  automaticLayout: true,
                  fontFamily:
                    '"SFMono-Regular", Consolas, "Liberation Mono", monospace',
                  fontSize: 14,
                  minimap: { enabled: false },
                  padding: { top: 16, bottom: 16 },
                  scrollBeyondLastLine: false,
                  tabSize: 2,
                  wordWrap: "on",
                }}
                onChange={(value) =>
                  setDrafts((current) => ({
                    ...current,
                    [selectedQuestion.id]: {
                      ...current[selectedQuestion.id],
                      source_code: value || "",
                    },
                  }))
                }
              />
            </div>

            <div
              className="assessment-actions-row candidate-action-row"
              role="toolbar"
              aria-label="Code actions"
            >
              <div className="candidate-action-context" aria-live="polite">
                <span className={`candidate-action-state ${isActionBusy ? "is-busy" : ""}`}>
                  {isActionBusy ? (
                    <LoaderCircle size={15} aria-hidden="true" />
                  ) : (
                    <Code2 size={15} aria-hidden="true" />
                  )}
                  {sampleMutation.isPending
                    ? "Running sample tests"
                    : hiddenCheckMutation.isPending
                      ? "Checking hidden tests"
                      : checkpointMutation.isPending
                        ? "Saving solution"
                        : "Editor ready"}
                </span>
                <small>Run before submitting to verify sample cases.</small>
              </div>
              <div className="candidate-action-buttons">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={saveSelectedQuestion}
                  disabled={checkpointMutation.isPending}
                >
                  <Save size={16} aria-hidden="true" />
                  {checkpointMutation.isPending ? "Saving..." : "Save Progress"}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={isActionBusy || !selectedDraft.source_code.trim()}
                  onClick={() =>
                    void sampleMutation.mutateAsync({
                      questionId: selectedQuestion.id,
                      sourceCode: selectedDraft.source_code,
                      language: selectedDraft.language,
                    })
                  }
                >
                  <Play size={16} aria-hidden="true" />
                  {sampleMutation.isPending ? "Running..." : "Run Test"}
                </Button>
                <Button
                  type="button"
                  className="candidate-submit-question"
                  disabled={
                    isActionBusy ||
                    hiddenCheckCooldownSeconds > 0 ||
                    !selectedDraft.source_code.trim()
                  }
                  onClick={() => void submitSelectedQuestion()}
                >
                  <CheckCircle2 size={16} aria-hidden="true" />
                  {hiddenCheckMutation.isPending
                    ? "Evaluating..."
                    : checkpointMutation.isPending
                      ? "Saving..."
                      : hiddenCheckCooldownSeconds > 0
                        ? `Submit again in ${hiddenCheckCooldownSeconds}s`
                        : "Submit Question"}
                </Button>
                {isSelectedQuestionSubmitted && nextQuestion ? (
                  <Button
                    type="button"
                    className="candidate-next-question"
                    onClick={() => moveToQuestion(nextQuestion.id)}
                  >
                    Move to next question
                    <ChevronRight size={16} aria-hidden="true" />
                  </Button>
                ) : null}
              </div>
            </div>

            <section
              className={`candidate-results-drawer ${resultsExpanded ? "is-expanded" : ""} ${resultTone}`}
              aria-label="Test case results"
            >
              <div className="candidate-results-handle">
                <button
                  type="button"
                  className="candidate-results-toggle"
                  aria-expanded={resultsExpanded}
                  onClick={() => setResultsExpanded((current) => !current)}
                >
                  <span>
                    <i className="candidate-results-indicator" aria-hidden="true" />
                    Testcase Results
                    {runResult ? <small>{runResult.summary}</small> : null}
                  </span>
                  <ChevronDown size={18} aria-hidden="true" />
                </button>
              </div>

              {resultsExpanded ? (
                <div className="candidate-results-content">
                  {runResult ? (
                    <div className="candidate-run-result">
                      <strong>{runResult.summary}</strong>
                      {runResult.cases.length ? (
                        <div className="candidate-result-cases">
                          {runResult.cases.map((testCase) => (
                            <article
                              key={testCase.index}
                              className={testCase.passed ? "is-passed" : "is-failed"}
                            >
                              <div className="candidate-case-status">
                                {testCase.passed ? (
                                  <CheckCircle2 size={18} aria-hidden="true" />
                                ) : (
                                  <XCircle size={18} aria-hidden="true" />
                                )}
                                <span>
                                  TC {testCase.index} · {testCase.passed ? "Passed" : "Failed"}
                                </span>
                                <time>
                                  {testCase.executionTime
                                    ? `${testCase.executionTime}s`
                                    : "Time unavailable"}
                                </time>
                              </div>
                              {testCase.passed ? (
                                <p>Executed successfully</p>
                              ) : (
                                <p>{testCase.errorType || testCase.status || "Execution failed"}</p>
                              )}
                              {runResult.kind === "sample" && testCase.detail ? (
                                <div className="candidate-result-output-grid">
                                  <div>
                                    <span>Expected</span>
                                    <pre>{testCase.expectedOutput || "(empty)"}</pre>
                                  </div>
                                  <div>
                                    <span>Actual</span>
                                    <pre>{testCase.actualOutput || testCase.detail || "(empty)"}</pre>
                                  </div>
                                </div>
                              ) : null}
                            </article>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="candidate-results-empty">
                      <Play size={20} aria-hidden="true" />
                      <div>
                        <strong>No testcase run yet</strong>
                        <p>Run the code or submit this question to view results here.</p>
                      </div>
                    </div>
                  )}

                  {mutationError(checkpointMutation.error) ? (
                    <p className="form-error">{mutationError(checkpointMutation.error)}</p>
                  ) : null}
                  {mutationError(sampleMutation.error) ? (
                    <p className="form-error">{mutationError(sampleMutation.error)}</p>
                  ) : null}
                  {mutationError(hiddenCheckMutation.error) ? (
                    <p className="form-error">{mutationError(hiddenCheckMutation.error)}</p>
                  ) : null}
                  {mutationError(submitMutation.error) ? (
                    <p className="form-error">{mutationError(submitMutation.error)}</p>
                  ) : null}
                </div>
              ) : null}
            </section>
          </Card>
        </div>

        {showSubmitAssessmentDialog ? (
          <div className="dialog-backdrop">
            <div className="candidate-final-submit-modal" role="dialog" aria-modal="true">
              <span className="candidate-kicker">Final Submission</span>
              <h2>Review your assessment progress</h2>
              <p>
                Once submitted, your assessment will be completed and you cannot continue editing.
              </p>
              <div className="candidate-final-progress-grid">
                <div>
                  <span>Attempted</span>
                  <strong>
                    {answeredQuestionCount}/{assessment.questions.length}
                  </strong>
                </div>
                <div>
                  <span>Question submitted</span>
                  <strong>
                    {submittedQuestionCount}/{assessment.questions.length}
                  </strong>
                </div>
                <div>
                  <span>Time remaining</span>
                  <strong>{formatRemainingTime(displayRemainingSeconds)}</strong>
                </div>
                <div>
                  <span>Time taken</span>
                  <strong>{formatRemainingTime(timeTakenSeconds)}</strong>
                </div>
                <div>
                  <span>Tracked question time</span>
                  <strong>{formatRemainingTime(trackedQuestionTimeSeconds)}</strong>
                </div>
              </div>
              <div className="candidate-final-progress-bar">
                <span style={{ width: `${progressPercent}%` }} />
              </div>
              {unansweredCount || mandatoryUnansweredCount ? (
                <div className="candidate-final-warning">
                  <AlertTriangle size={18} aria-hidden="true" />
                  <div>
                    <strong>Review before submitting</strong>
                    <p>
                      {unansweredCount} question{unansweredCount === 1 ? "" : "s"} still
                      unanswered
                      {mandatoryUnansweredCount
                        ? `, including ${mandatoryUnansweredCount} mandatory question${
                            mandatoryUnansweredCount === 1 ? "" : "s"
                          }`
                        : ""}
                      .
                    </p>
                  </div>
                </div>
              ) : null}
              <div className="candidate-final-question-summary">
                <div className="candidate-final-summary-heading">
                  <div>
                    <span className="candidate-kicker">Question Review</span>
                    <h3>Your answers before final submission</h3>
                  </div>
                  <p>
                    The understanding signal is an answer-completion estimate from
                    code presence, saved/submitted state, and visible sample test
                    results.
                  </p>
                </div>
                {questionSubmissionSummary.map((item) => (
                  <article key={item.question.id} className="candidate-final-question-card">
                    <div className="candidate-final-question-head">
                      <div>
                        <span>
                          Question {item.question.question_order} · {item.question.marks} marks
                        </span>
                        <strong>{item.question.title}</strong>
                      </div>
                      <span
                        className={`status-badge ${
                          item.isSubmitted
                            ? "status-success"
                            : item.isAttempted
                              ? "status-warning"
                              : "status-danger"
                        }`}
                      >
                        {item.isSubmitted
                          ? "submitted"
                          : item.isAttempted
                            ? "draft"
                            : "unanswered"}
                      </span>
                    </div>
                    <div className="candidate-final-question-meta">
                      <span>{item.language}</span>
                      <span>Time spent {formatRemainingTime(item.timeSpentSeconds)}</span>
                      <span>{item.lineCount} code lines</span>
                      <span>
                        {item.sampleTotal
                          ? `${item.samplePassed}/${item.sampleTotal} visible tests passed`
                          : "No visible test run in this review"}
                      </span>
                      <span>
                        {item.submittedAt
                          ? `Submitted ${formatDateTime(item.submittedAt)}`
                          : item.lastSavedAt
                            ? `Saved ${formatDateTime(item.lastSavedAt)}`
                            : "Not saved yet"}
                      </span>
                    </div>
                    <div className="candidate-understanding-meter">
                      <div>
                        <span style={{ width: `${item.answerSignal}%` }} />
                      </div>
                      <strong>{item.answerSignal}% answer signal</strong>
                    </div>
                    <pre className="candidate-final-code-preview">
                      {item.sourceCode.trim() || "No code answered for this question."}
                    </pre>
                  </article>
                ))}
              </div>
              {requiresEndConfirmation ? (
                <label className="field candidate-end-confirmation">
                  <span>More than 50% of your time is still remaining.</span>
                  <small>Type end to confirm early final submission.</small>
                  <input
                    value={finalSubmitConfirmation}
                    onChange={(event) => setFinalSubmitConfirmation(event.target.value)}
                    placeholder="Type end"
                  />
                </label>
              ) : null}
              <div className="confirm-dialog-actions">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setShowSubmitAssessmentDialog(false)}
                >
                  Continue Test
                </Button>
                <Button
                  type="button"
                  disabled={
                    submitMutation.isPending ||
                    (requiresEndConfirmation &&
                      finalSubmitConfirmation.trim().toLowerCase() !== "end")
                  }
                  onClick={confirmFinalSubmit}
                >
                  {submitMutation.isPending ? "Submitting..." : "Submit Assessment"}
                </Button>
              </div>
            </div>
          </div>
        ) : null}
      </section>
    </main>
  );
}
