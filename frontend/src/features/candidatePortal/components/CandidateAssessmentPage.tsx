import { useMutation, useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

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
import { CandidatePageShell } from "./CandidatePageShell";
import { CandidateAssessmentHeader } from "./assessment/CandidateAssessmentHeader";
import { CandidateEditorPanel } from "./assessment/CandidateEditorPanel";
import { CandidateFinalSubmitDialog } from "./assessment/CandidateFinalSubmitDialog";
import { CandidateProblemPanel } from "./assessment/CandidateProblemPanel";
import { CandidateQuestionNavigator } from "./assessment/CandidateQuestionNavigator";
import { CandidateResultsPanel } from "./assessment/CandidateResultsPanel";
import {
  CandidateFullscreenGate,
  CandidatePausedNotice,
  CandidateProctoringNotice,
} from "./assessment/CandidateSecurityNotice";
import type {
  QuestionProgress,
  QuestionProgressStatus,
  RunResultCase,
  RunResultState,
  SaveState,
} from "./assessment/types";

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

/** Normalise a sample-run case. Sample cases may show inputs and outputs. */
function toSampleCase(item: CandidateExecutionCaseResult): RunResultCase {
  return {
    index: item.index,
    passed: item.passed,
    status: item.status,
    executionTime: item.execution_time,
    errorType: item.passed ? "" : item.status || "Execution failed",
    input: item.input,
    expectedOutput: item.expected_output,
    actualOutput: item.actual_output,
    stderr: item.stderr,
    compileOutput: item.compile_output,
    checkerMessage: item.checker_message || item.message,
    memoryKb: item.memory_kb,
  };
}

export function CandidateAssessmentPage() {
  const navigate = useNavigate();
  const [sessionToken, setSessionToken] = useState(readCandidateSessionToken);
  const [sessionWarning, setSessionWarning] = useState("");
  const [selectedQuestionId, setSelectedQuestionId] = useState<string>("");
  const [drafts, setDrafts] = useState<Record<string, DraftState>>({});
  const [runResult, setRunResult] = useState<RunResultState | null>(null);
  const [runAnnouncement, setRunAnnouncement] = useState("");
  const [hiddenCheckCooldownSeconds, setHiddenCheckCooldownSeconds] = useState(0);
  const [hiddenAttemptsRemaining, setHiddenAttemptsRemaining] = useState<
    Record<string, number>
  >({});
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
  const [saveError, setSaveError] = useState("");
  const [versionConflict, setVersionConflict] = useState("");
  const [autosaveBusy, setAutosaveBusy] = useState(false);
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
          "A monitoring event could not be synchronized. Check your connection.",
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
            setVersionConflict(
              `Question ${question.question_order} changed in another tab. Reload this page before saving it.`,
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
      summary: `${saved.passed_count || 0} of ${saved.total_count || results.length} sample cases passed`,
      cases: results.map(toSampleCase),
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
  const totalDurationSeconds = (assessmentQuery.data?.duration_minutes || 0) * 60;
  const requiresEndConfirmation =
    totalDurationSeconds > 0 &&
    displayRemainingSeconds > Math.floor(totalDurationSeconds * 0.5);

  const questionProgress = useMemo<QuestionProgress[]>(() => {
    const assessment = assessmentQuery.data;
    if (!assessment) {
      return [];
    }
    return assessment.questions.map((question) => {
      const draft = drafts[question.id];
      const serverDraft = assessment.drafts.find(
        (item) => item.question_id === question.id,
      );
      const sourceCode = draft?.source_code ?? serverDraft?.draft_code ?? "";
      const isAttempted = sourceCode.trim().length > 0;
      const isSubmitted =
        submittedQuestionIds.has(question.id) ||
        Boolean(serverDraft?.submitted_at) ||
        serverDraft?.status === "submitted";
      const outcome = questionOutcomes[question.id];
      let status: QuestionProgressStatus = "not_started";
      if (isSubmitted) {
        status =
          outcome === "passed"
            ? "passed"
            : outcome === "failed"
              ? "needs_attention"
              : "submitted";
      } else if (isAttempted) {
        status = "in_progress";
      }
      return { question, status, isAttempted, isSubmitted };
    });
  }, [assessmentQuery.data, drafts, questionOutcomes, submittedQuestionIds]);

  const attemptedCount = questionProgress.filter((item) => item.isAttempted).length;
  const submittedCount = questionProgress.filter((item) => item.isSubmitted).length;
  const unansweredCount = questionProgress.filter((item) => !item.isAttempted).length;
  const mandatoryUnansweredCount = questionProgress.filter(
    (item) => item.question.is_mandatory && !item.isAttempted,
  ).length;

  const revealTestCaseResults = useCallback(
    async (
      kind: "sample" | "hidden",
      finalSummary: string,
      cases: RunResultCase[],
    ) => {
      setRunResult({
        kind,
        summary: `0 of ${cases.length} test cases completed`,
        cases: [],
      });
      for (let index = 0; index < cases.length; index += 1) {
        await new Promise((resolve) =>
          window.setTimeout(resolve, TEST_RESULT_REVEAL_INTERVAL_MS),
        );
        setRunResult({
          kind,
          summary: `${index + 1} of ${cases.length} test cases completed`,
          cases: cases.slice(0, index + 1),
        });
      }
      setRunResult({ kind, summary: finalSummary, cases });
      setRunAnnouncement(finalSummary);
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
      setSaveError("");
    },
    onError: (error: unknown) => {
      setSaveError(mutationError(error) || "Your work could not be saved.");
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
      setRunAnnouncement("Running sample tests.");
      setRunResult({
        kind: "sample",
        summary: "Running sample tests…",
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
      void revealTestCaseResults(
        "sample",
        `${data.passed_count} of ${data.total_count} sample cases passed`,
        data.results.map(toSampleCase),
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
      setRunAnnouncement("Running hidden tests for this question.");
      setRunResult({
        kind: "hidden",
        summary: "Running hidden tests…",
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
      if (typeof data.remaining_attempts === "number") {
        const remaining = data.remaining_attempts;
        setHiddenAttemptsRemaining((current) => ({
          ...current,
          [variables.questionId]: remaining,
        }));
      }
      // Hidden cases intentionally expose only index, status, timing, and the
      // error category. Inputs, expected output, and actual output stay hidden.
      const cases: RunResultCase[] = data.results.map((item) => ({
        index: item.index,
        passed: item.passed,
        status: item.status,
        executionTime: item.execution_time,
        errorType: item.error_type,
      }));
      void revealTestCaseResults(
        "hidden",
        `${data.passed_count} of ${data.total_count} hidden test cases passed`,
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
      const assessment = assessmentQuery.data;
      if (!assessment || !sessionToken) {
        throw new Error("Assessment session is not available.");
      }
      const answers = assessment.questions.map((question) => ({
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
        // Locally captured display fields for the completion receipt. The
        // session token is cleared immediately after, so they cannot be
        // re-fetched.
        candidate_name: assessment.candidate_name,
        assessment_title: assessment.assessment_title,
        slot_title: assessment.slot_title,
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
    // Failures surface through `checkpointMutation.error` and the save state.
    void checkpointMutation
      .mutateAsync({
        questionId: selectedQuestion.id,
        sourceCode: selectedDraft.source_code,
        language: selectedDraft.language,
        currentQuestionOrder: selectedQuestion.question_order,
      })
      .catch(() => undefined);
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

  const moveToQuestion = useCallback(
    (questionId: string) => {
      saveSelectedQuestion();
      setRunResult(null);
      setRunAnnouncement("");
      setResultsExpanded(false);
      setSelectedQuestionId(questionId);
    },
    [saveSelectedQuestion],
  );

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

  function reviewQuestion(questionId: string) {
    setShowSubmitAssessmentDialog(false);
    moveToQuestion(questionId);
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
      setAutosaveBusy(true);
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
          setSaveError("");
        })
        .catch((error: unknown) => {
          setSaveError(
            error instanceof Error
              ? error.message
              : "Autosave failed. We will keep retrying.",
          );
        })
        .finally(() => {
          autosaveInFlightRef.current = false;
          setAutosaveBusy(false);
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
    setHiddenAttemptsRemaining((current) => {
      const next = { ...current };
      let changed = false;
      assessment.drafts.forEach((draft) => {
        const remaining = draft.hidden_check_result.remaining_attempts;
        if (typeof remaining === "number" && next[draft.question_id] === undefined) {
          next[draft.question_id] = remaining;
          changed = true;
        }
      });
      return changed ? next : current;
    });
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
          `Leaving the assessment was recorded. Warning ${next} of ${TAB_SWITCH_LIMIT}. Your assessment is submitted automatically after ${TAB_SWITCH_LIMIT} warnings.`,
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
              `Focus left the assessment window. Warning ${next} of ${TAB_SWITCH_LIMIT}.`,
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
          ? "Copy, cut, and paste are turned off for this assessment."
          : "Clipboard activity was recorded.",
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

  if (assessmentQuery.isError && !assessmentQuery.data) {
    return (
      <CandidatePageShell>
        <Card className="cap-panel cap-panel-narrow" aria-labelledby="cap-ws-error">
          <div className="cap-panel-intro">
            <h1 id="cap-ws-error">We could not load your assessment</h1>
            <p role="alert">
              {mutationError(assessmentQuery.error) ||
                "Your assessment could not be loaded right now."}
            </p>
          </div>
          <p className="cap-muted">
            Your saved work is not lost. Check your connection and try again.
          </p>
          <div className="cap-actions">
            <button
              type="button"
              className="button button-primary cap-btn"
              onClick={() => void assessmentQuery.refetch()}
              disabled={assessmentQuery.isFetching}
            >
              {assessmentQuery.isFetching ? "Retrying…" : "Try again"}
            </button>
          </div>
        </Card>
      </CandidatePageShell>
    );
  }

  if (!assessmentQuery.data || !selectedQuestion || !selectedDraft) {
    return (
      <CandidatePageShell>
        <Card className="cap-panel cap-panel-narrow" aria-labelledby="cap-ws-loading">
          <div className="cap-panel-intro">
            <h1 id="cap-ws-loading">Preparing your workspace</h1>
            <p role="status">
              Loading your questions, saved work, and timer. This takes a moment.
            </p>
          </div>
          <div className="cap-skeleton-stack" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        </Card>
      </CandidatePageShell>
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
  const isTestRunning = sampleMutation.isPending || hiddenCheckMutation.isPending;
  const saveState: SaveState = versionConflict
    ? { kind: "conflict", message: versionConflict }
    : checkpointMutation.isPending || autosaveBusy
      ? { kind: "saving" }
      : saveError
        ? { kind: "error", message: saveError }
        : lastSavedAt
          ? { kind: "saved", at: lastSavedAt }
          : { kind: "idle" };
  const resultErrors = [
    mutationError(checkpointMutation.error),
    mutationError(sampleMutation.error),
    mutationError(hiddenCheckMutation.error),
  ].filter(Boolean);
  const selectedAttemptsRemaining =
    selectedQuestion.id in hiddenAttemptsRemaining
      ? hiddenAttemptsRemaining[selectedQuestion.id]
      : null;

  return (
    <div className="cap-root cap-workspace">
      <CandidateAssessmentHeader
        assessmentTitle={assessment.assessment_title}
        candidateName={assessment.candidate_name}
        questionPosition={selectedQuestion.question_order}
        questionCount={assessment.questions.length}
        remainingSeconds={displayRemainingSeconds}
        saveState={saveState}
        showWarnings={assessment.proctoring_mode !== "none"}
        warningCount={tabSwitchWarnings}
        warningLimit={TAB_SWITCH_LIMIT}
        onFinish={requestFinalSubmit}
        finishDisabled={submitMutation.isPending}
      />

      <p className="sr-only" role="status" aria-live="polite">
        {runAnnouncement}
      </p>

      {sessionWarning || versionConflict || saveError || proctorMessage ? (
        <div className="cap-banners" role="status" aria-live="polite">
          {sessionWarning ? <p className="cap-banner">{sessionWarning}</p> : null}
          {versionConflict ? (
            <p className="cap-banner is-danger">{versionConflict}</p>
          ) : null}
          {saveError ? <p className="cap-banner is-warning">{saveError}</p> : null}
          {proctorMessage ? (
            <p className="cap-banner is-warning">{proctorMessage}</p>
          ) : null}
        </div>
      ) : null}

      <p className="cap-mobile-note">
        <Info size={14} aria-hidden="true" />
        <span>
          Coding assessments work best on a desktop or laptop. Everything here
          still works on a small screen, but the editor is easier to use on a
          larger one.
        </span>
      </p>

      <div className="cap-workspace-body">
        <CandidateQuestionNavigator
          items={questionProgress}
          selectedQuestionId={selectedQuestion.id}
          onSelect={moveToQuestion}
        />

        <main className="cap-panels">
          <CandidateProblemPanel question={selectedQuestion} />

          <div className="cap-editor-stack">
            <CandidateEditorPanel
              question={selectedQuestion}
              language={selectedDraft.language}
              sourceCode={selectedDraft.source_code}
              saveState={saveState}
              isSubmitted={isSelectedQuestionSubmitted}
              isPaused={isPaused}
              isSaving={checkpointMutation.isPending}
              isRunningSample={sampleMutation.isPending}
              isCheckingHidden={hiddenCheckMutation.isPending}
              actionsDisabled={isActionBusy}
              hiddenCooldownSeconds={hiddenCheckCooldownSeconds}
              hiddenAttemptsRemaining={selectedAttemptsRemaining}
              nextQuestionTitle={nextQuestion?.title || null}
              onLanguageChange={(language) =>
                setDrafts((current) => ({
                  ...current,
                  [selectedQuestion.id]: {
                    ...current[selectedQuestion.id],
                    language,
                  },
                }))
              }
              onCodeChange={(sourceCode) =>
                setDrafts((current) => ({
                  ...current,
                  [selectedQuestion.id]: {
                    ...current[selectedQuestion.id],
                    source_code: sourceCode,
                  },
                }))
              }
              onSave={saveSelectedQuestion}
              onRunSample={() =>
                void sampleMutation
                  .mutateAsync({
                    questionId: selectedQuestion.id,
                    sourceCode: selectedDraft.source_code,
                    language: selectedDraft.language,
                  })
                  .catch(() => undefined)
              }
              onSubmitQuestion={() => void submitSelectedQuestion().catch(() => undefined)}
              onNextQuestion={() => {
                if (nextQuestion) {
                  moveToQuestion(nextQuestion.id);
                }
              }}
            />

            <CandidateResultsPanel
              expanded={resultsExpanded}
              onToggle={() => setResultsExpanded((current) => !current)}
              result={runResult}
              isRunning={isTestRunning}
              runLabel={
                sampleMutation.isPending
                  ? "Running sample tests…"
                  : "Running hidden tests…"
              }
              errors={resultErrors}
            />
          </div>
        </main>
      </div>

      <CandidateProctoringNotice
        mode={assessment.proctoring_mode}
        warningCount={tabSwitchWarnings}
        warningLimit={TAB_SWITCH_LIMIT}
      />

      {isPaused ? <CandidatePausedNotice /> : null}

      {fullscreenPromptVisible ? (
        <CandidateFullscreenGate
          onEnterFullscreen={() =>
            void document.documentElement
              .requestFullscreen()
              .then(() => {
                hasEnteredFullscreenRef.current = true;
                setFullscreenPromptVisible(false);
              })
              .catch(() =>
                setProctorMessage(
                  "Your browser blocked fullscreen. Select Enter fullscreen again to continue.",
                ),
              )
          }
        />
      ) : null}

      {showSubmitAssessmentDialog ? (
        <CandidateFinalSubmitDialog
          items={questionProgress}
          attemptedCount={attemptedCount}
          submittedCount={submittedCount}
          unansweredCount={unansweredCount}
          mandatoryUnansweredCount={mandatoryUnansweredCount}
          remainingSeconds={displayRemainingSeconds}
          requiresEndConfirmation={requiresEndConfirmation}
          confirmationValue={finalSubmitConfirmation}
          onConfirmationChange={setFinalSubmitConfirmation}
          isSubmitting={submitMutation.isPending}
          errorMessage={mutationError(submitMutation.error)}
          onClose={() => setShowSubmitAssessmentDialog(false)}
          onSubmit={confirmFinalSubmit}
          onReview={reviewQuestion}
        />
      ) : null}
    </div>
  );
}
