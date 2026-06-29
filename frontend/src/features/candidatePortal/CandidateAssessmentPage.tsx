import { useMutation, useQuery } from "@tanstack/react-query";
import Editor from "@monaco-editor/react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Code2,
  EyeOff,
  Play,
  Save,
  Send,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import {
  fetchCandidateAssessment,
  runCandidateHiddenCheck,
  runCandidateSample,
  saveCandidateCheckpoint,
  submitCandidateAssessment,
} from "./services/candidatePortalService";
import {
  clearCandidateSessionToken,
  readCandidateSessionToken,
  saveSubmissionResult,
} from "./sessionStorage";
import type {
  CandidateAssessmentPortal,
  CandidateExecutionCaseResult,
  CandidateSampleRunResponse,
} from "./types/CandidatePortal";

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

type RunResultState =
  | {
      kind: "sample";
      summary: string;
      cases: CandidateExecutionCaseResult[];
    }
  | {
      kind: "hidden";
      summary: string;
      cases: [];
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
  const sessionToken = readCandidateSessionToken();
  const [selectedQuestionId, setSelectedQuestionId] = useState<string>("");
  const [drafts, setDrafts] = useState<Record<string, DraftState>>({});
  const [runResult, setRunResult] = useState<RunResultState>(null);
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
  const [displayRemainingSeconds, setDisplayRemainingSeconds] = useState(0);
  const [tabSwitchWarnings, setTabSwitchWarnings] = useState(0);
  const [proctorMessage, setProctorMessage] = useState("");
  const [submittedQuestionIds, setSubmittedQuestionIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [showSubmitAssessmentDialog, setShowSubmitAssessmentDialog] =
    useState(false);
  const [finalSubmitConfirmation, setFinalSubmitConfirmation] = useState("");
  const [fullscreenPromptVisible, setFullscreenPromptVisible] = useState(false);
  const [questionTimeSpentSeconds, setQuestionTimeSpentSeconds] = useState<
    Record<string, number>
  >({});
  const submitOnceRef = useRef(false);
  const fullscreenAttemptedRef = useRef(false);
  const hasReceivedPositiveTimerRef = useRef(false);
  const latestDraftsRef = useRef<Record<string, DraftState>>({});
  const timerSyncRef = useRef({
    serverRemainingSeconds: 0,
    syncedAtMs: Date.now(),
  });

  const assessmentQuery = useQuery({
    queryKey: ["candidate-assessment", sessionToken],
    queryFn: async () => fetchCandidateAssessment(sessionToken || ""),
    enabled: Boolean(sessionToken),
    refetchInterval: 15000,
  });

  latestDraftsRef.current = drafts;

  useEffect(() => {
    if (!sessionToken) {
      navigate("/candidate/submitted", { replace: true });
    }
  }, [navigate, sessionToken]);

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
        }
      });
      return next;
    });
  }, [assessmentQuery.data, selectedQuestionId]);

  useEffect(() => {
    const assessmentId = assessmentQuery.data?.candidate_assessment_id;
    if (!assessmentId) {
      return;
    }
    const storageKey = `candidate-question-time-${assessmentId}`;
    try {
      const stored = window.sessionStorage.getItem(storageKey);
      if (stored) {
        setQuestionTimeSpentSeconds(JSON.parse(stored) as Record<string, number>);
      }
    } catch {
      setQuestionTimeSpentSeconds({});
    }
  }, [assessmentQuery.data?.candidate_assessment_id]);

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
  const totalMarks =
    assessmentQuery.data?.questions.reduce((sum, question) => sum + question.marks, 0) ||
    0;
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
      }),
    onSuccess: (data) => {
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
    }) =>
      runCandidateSample(sessionToken || "", {
        question_id: questionId,
        source_code: sourceCode,
        language,
      }),
    onSuccess: (data: CandidateSampleRunResponse) => {
      setRunResult({
        kind: "sample",
        summary: `${data.passed_count}/${data.total_count} sample cases passed`,
        cases: data.results,
      });
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
    }) =>
      runCandidateHiddenCheck(sessionToken || "", {
        question_id: questionId,
        source_code: sourceCode,
        language,
      }),
    onSuccess: (data) => {
      setRunResult({
        kind: "hidden",
        summary:
          data.remaining_attempts === null
            ? `${data.passed_count}/${data.total_count} hidden checks passed. Unlimited attempts enabled.`
            : `${data.passed_count}/${data.total_count} hidden checks passed. ${data.remaining_attempts} attempts remaining.`,
        cases: [],
      });
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
    setSubmittedQuestionIds((current) => {
      const next = new Set(current);
      next.add(selectedQuestion.id);
      return next;
    });
  }, [checkpointMutation, selectedDraft, selectedQuestion]);

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
    const elapsedSeconds = Math.floor(
      (Date.now() - timerSyncRef.current.syncedAtMs) / 1000,
    );
    return Math.max(
      0,
      timerSyncRef.current.serverRemainingSeconds - elapsedSeconds,
    );
  }, []);

  useEffect(() => {
    if (!assessmentQuery.data || !selectedQuestion || !selectedDraft) {
      return;
    }
    const interval = window.setInterval(() => {
      saveSelectedQuestion();
    }, 15000);
    return () => window.clearInterval(interval);
  }, [assessmentQuery.data, saveSelectedQuestion, selectedDraft, selectedQuestion]);

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
    window.sessionStorage.setItem(
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
      .filter((draft) => draft.submitted_at || draft.status === "submitted")
      .map((draft) => draft.question_id);
    if (!serverSubmittedIds.length) {
      return;
    }
    setSubmittedQuestionIds((current) => {
      const next = new Set(current);
      serverSubmittedIds.forEach((questionId) => next.add(questionId));
      return next;
    });
  }, [assessmentQuery.data]);

  useEffect(() => {
    if (!assessmentQuery.data || fullscreenAttemptedRef.current) {
      return;
    }
    fullscreenAttemptedRef.current = true;
    if (document.fullscreenElement) {
      setFullscreenPromptVisible(false);
      return;
    }
    void document.documentElement
      .requestFullscreen()
      .then(() => setFullscreenPromptVisible(false))
      .catch(() => setFullscreenPromptVisible(true));
  }, [assessmentQuery.data]);

  useEffect(() => {
    const serverRemainingSeconds = deriveRemainingSeconds(assessmentQuery.data);
    if (serverRemainingSeconds > 0) {
      hasReceivedPositiveTimerRef.current = true;
    }
    timerSyncRef.current = {
      serverRemainingSeconds,
      syncedAtMs: Date.now(),
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
    if (!assessmentQuery.data) {
      return;
    }

    let countedHiddenState = document.visibilityState === "hidden";

    function recordTabSwitchWarning() {
      if (submitOnceRef.current) {
        return;
      }
      setTabSwitchWarnings((current) => {
        const next = Math.min(current + 1, TAB_SWITCH_LIMIT);
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
          recordTabSwitchWarning();
        }
        return;
      }
      countedHiddenState = false;
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [assessmentQuery.data, submitAutomatically]);

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
  const warningsRemaining = Math.max(0, TAB_SWITCH_LIMIT - tabSwitchWarnings);
  const isActionBusy =
    checkpointMutation.isPending ||
    sampleMutation.isPending ||
    hiddenCheckMutation.isPending ||
    submitMutation.isPending;
  const isSelectedQuestionSubmitted = submittedQuestionIds.has(selectedQuestion.id);
  const remainingQuestionCount = Math.max(
    0,
    assessment.questions.length - answeredQuestionCount,
  );
  const currentQuestionTimeSeconds =
    questionTimeSpentSeconds[selectedQuestion.id] || 0;
  const currentQuestionHasCode = selectedDraft.source_code.trim().length > 0;
  const currentQuestionNextStep = isSelectedQuestionSubmitted
    ? "Review or move to the next question"
    : currentQuestionHasCode
      ? "Run test, then submit this question"
      : "Read the problem and start coding";

  return (
    <main className="candidate-portal candidate-portal-pro">
      <aside className="candidate-questions-panel">
        <div className="candidate-sidebar-header">
          <span className="candidate-kicker">Live Assessment</span>
          <h2>{assessment.assessment_title}</h2>
          <p>{assessment.slot_title}</p>
        </div>

        <div
          className={`candidate-timer ${
            displayRemainingSeconds <= 300 ? "is-critical" : ""
          }`}
        >
          <span>Time remaining</span>
          <strong>{formatRemainingTime(displayRemainingSeconds)}</strong>
          <small>
            <Clock3 size={14} aria-hidden="true" />
            Synced every 15 seconds
          </small>
        </div>

        <div className="candidate-proctor-card">
          <span>
            <EyeOff size={15} aria-hidden="true" />
            Tab switch lock
          </span>
          <strong>
            {tabSwitchWarnings}/{TAB_SWITCH_LIMIT} warnings
          </strong>
          <p>
            {warningsRemaining
              ? `${warningsRemaining} warning${warningsRemaining === 1 ? "" : "s"} remaining before auto-submit.`
              : "Auto-submit in progress."}
          </p>
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

        <div className="candidate-sidebar-checklist">
          <span>Recommended flow</span>
          <ol>
            <li className="is-complete">Read question</li>
            <li className={currentQuestionHasCode ? "is-complete" : ""}>Write code</li>
            <li className={runResult ? "is-complete" : ""}>Run test</li>
            <li className={isSelectedQuestionSubmitted ? "is-complete" : ""}>
              Submit question
            </li>
          </ol>
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
                } ${submittedQuestionIds.has(question.id) ? "is-submitted" : ""}`}
                onClick={() => {
                  saveSelectedQuestion();
                  setRunResult(null);
                  setSelectedQuestionId(question.id);
                }}
              >
                <span>Question {question.question_order}</span>
                <strong>{question.title}</strong>
                <em>
                  {submittedQuestionIds.has(question.id)
                    ? "Question submitted"
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
        {proctorMessage ? (
          <div
            className={`candidate-proctor-alert ${
              tabSwitchWarnings >= TAB_SWITCH_LIMIT ? "is-locked" : ""
            }`}
          >
            <AlertTriangle size={18} aria-hidden="true" />
            <div>
              <strong>
                {tabSwitchWarnings >= TAB_SWITCH_LIMIT
                  ? "Assessment auto-submitted"
                  : "Proctoring warning"}
              </strong>
              <p>{proctorMessage}</p>
            </div>
          </div>
        ) : null}

        {fullscreenPromptVisible ? (
          <div className="candidate-fullscreen-prompt">
            <ShieldCheck size={18} aria-hidden="true" />
            <div>
              <strong>Fullscreen keeps your assessment focused</strong>
              <p>Your browser blocked automatic fullscreen. Enter fullscreen before continuing.</p>
            </div>
            <Button
              type="button"
              variant="secondary"
              onClick={() =>
                void document.documentElement
                  .requestFullscreen()
                  .then(() => setFullscreenPromptVisible(false))
              }
            >
              Enter Fullscreen
            </Button>
          </div>
        ) : null}

        <div className="candidate-topbar">
          <div>
            <span className="candidate-kicker">Candidate</span>
            <strong>{assessment.candidate_name}</strong>
            <p>{assessment.candidate_email}</p>
          </div>
          <div>
            <span>Deadline</span>
            <strong>{formatDateTime(assessment.deadline_at)}</strong>
          </div>
          <div>
            <span>Total marks</span>
            <strong>{totalMarks}</strong>
          </div>
          <div>
            <span>Questions submitted</span>
            <strong>
              {submittedQuestionCount}/{assessment.questions.length}
            </strong>
          </div>
        </div>

        <Card className="candidate-submit-strip">
          <div>
            <span className="candidate-kicker">Assessment Completion</span>
            <h2>Submit the whole assessment only when you are finished.</h2>
            <p>
              Progress: {answeredQuestionCount}/{assessment.questions.length} questions
              attempted · {submittedQuestionCount}/{assessment.questions.length} questions
              submitted · {formatRemainingTime(displayRemainingSeconds)} remaining
            </p>
          </div>
          <div className="candidate-submit-strip-progress" aria-hidden="true">
            <span style={{ width: `${progressPercent}%` }} />
          </div>
          <Button
            type="button"
            onClick={requestFinalSubmit}
            disabled={submitMutation.isPending}
          >
            <Send size={16} aria-hidden="true" />
            Submit Assessment
          </Button>
        </Card>

        <div className="candidate-guidance-grid">
          <div>
            <span>Current question</span>
            <strong>
              Q{selectedQuestion.question_order}. {selectedQuestion.title}
            </strong>
            <p>{currentQuestionNextStep}</p>
          </div>
          <div>
            <span>Time on this question</span>
            <strong>{formatRemainingTime(currentQuestionTimeSeconds)}</strong>
            <p>Tracked while this question is open and visible.</p>
          </div>
          <div>
            <span>Questions remaining</span>
            <strong>{remainingQuestionCount}</strong>
            <p>
              {submittedQuestionCount}/{assessment.questions.length} marked submitted.
            </p>
          </div>
        </div>

        <div className="candidate-workbench">
          <Card className="candidate-problem-card">
            <div className="candidate-problem-header">
              <div>
                <span className="candidate-kicker">
                  {selectedQuestion.difficulty} · {selectedQuestion.marks} marks
                </span>
                <h1>{selectedQuestion.title}</h1>
              </div>
              {selectedQuestion.is_mandatory ? <span className="status-badge status-info">mandatory</span> : null}
            </div>

            <section className="candidate-problem-section">
              <h3>Problem</h3>
              <p>{selectedQuestion.problem_statement}</p>
            </section>
            <section className="candidate-problem-section">
              <h3>Input Format</h3>
              <p>{selectedQuestion.input_format || "Input format is included in the problem statement."}</p>
            </section>
            <section className="candidate-problem-section">
              <h3>Output Format</h3>
              <p>{selectedQuestion.output_format || "Print the required answer only."}</p>
            </section>
            <section className="candidate-problem-section">
              <h3>Constraints</h3>
              <p>{selectedQuestion.constraints || "Use an efficient approach for the stated limits."}</p>
            </section>

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
                height="520px"
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

            <div className="assessment-actions-row candidate-action-row">
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
                disabled={checkpointMutation.isPending || !selectedDraft.source_code.trim()}
                onClick={() => void submitSelectedQuestion()}
              >
                <CheckCircle2 size={16} aria-hidden="true" />
                {checkpointMutation.isPending ? "Submitting..." : "Submit Question"}
              </Button>
              {assessment.hidden_feedback_mode === "summary" ? (
                <Button
                  type="button"
                  variant="secondary"
                  disabled={isActionBusy || !selectedDraft.source_code.trim()}
                  onClick={() =>
                    void hiddenCheckMutation.mutateAsync({
                      questionId: selectedQuestion.id,
                      sourceCode: selectedDraft.source_code,
                      language: selectedDraft.language,
                    })
                  }
                >
                  <ShieldCheck size={16} aria-hidden="true" />
                  {hiddenCheckMutation.isPending ? "Checking..." : "Hidden Summary"}
                </Button>
              ) : null}
            </div>

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
                            Test {testCase.index} {testCase.passed ? "passed" : "failed"}
                          </span>
                        </div>
                        <pre>{testCase.actual_output || testCase.stderr || testCase.compile_output || "No output"}</pre>
                      </article>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

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
