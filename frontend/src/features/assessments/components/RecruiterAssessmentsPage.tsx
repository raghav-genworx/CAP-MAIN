import { useEffect, useMemo, useState } from "react";
import {
  Archive,
  ArrowLeft,
  BarChart3,
  BadgeCheck,
  Check,
  Clock3,
  Code2,
  FileText,
  Gauge,
  ListChecks,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { useAuth } from "../../auth";
import { AssessmentEvaluationPanel } from "./AssessmentEvaluationPanel";
import { AssessmentList } from "./AssessmentList";
import { TestResultsTab } from "./TestResultsTab";
import {
  assessmentToPayload,
  buildAssessmentQuestionAssignments,
  buildCandidateCsv,
  calculateQuestionTemplateMarks,
  createEmptyAssessment,
  createQuestionBlueprint,
  errorMessage,
  formatCountdown,
  formatDateTime,
  formatDuration,
  reorderQuestionIds,
  statusTone,
  TIME_ZONE_OPTIONS,
  timezoneOffsetMinutesForLocalDateTime,
  toIsoDateTimeForTimezone,
  toTimezoneInputValue,
  type ManualCandidateRow,
} from "../utils/recruiterAssessmentViewModel";
import {
  useAssessmentSlots,
  useAssessments,
  useBackfillAssessmentEvaluations,
  useControlAssessmentSlot,
  useCreateAssessment,
  useCreateAssessmentSlot,
  useDeleteAssessment,
  useImportSlotCandidates,
  useResendCandidateInvite,
  useSendSlotInvites,
  useSetAssessmentQuestions,
  useSlotCandidates,
  useSlotMonitoring,
  useUpdateAssessment,
  useUpdateAssessmentSlot,
} from "../hooks/useAssessments";
import { useCreateQuestionGroup, useQuestionBank, useQuestionGroups } from "../hooks/useQuestionBank";
import type {
  Assessment,
  AssessmentCreatePayload,
  AssessmentQuestionAssignment,
  AssessmentSlot,
  AssessmentSlotActionPayload,
  AssessmentSlotUpdatePayload,
  CandidateAssessmentStatus,
  EvaluationBackfillResponse,
  MonitoringCandidate,
  SlotCandidate,
} from "../types/Assessment";
import type {
  DifficultyLevel,
  QuestionGroupCreatePayload,
  QuestionGroupRecord,
  QuestionRecord,
} from "../types/QuestionBank";

type RecruiterView = "list" | "create" | "assessment" | "test";
type AssessmentDetailMode = "tests" | "questions" | "evaluation";
type TestTab = "candidates" | "live" | "results";
type CandidateEntryMode = "csv" | "manual";
type QuestionSetMode = "select-questions" | "select-groups" | "custom";
type AssessmentCreateSection = "basics" | "questions" | "rules";

const ASSESSMENT_LANGUAGES = ["python", "java", "cpp", "c"] as const;
const QUESTION_DIFFICULTIES: DifficultyLevel[] = ["easy", "medium", "hard"];
const LANGUAGE_LABELS: Record<(typeof ASSESSMENT_LANGUAGES)[number], string> = {
  python: "Python",
  java: "Java",
  cpp: "C++",
  c: "C",
};

function addMinutesToLocalInput(value: string, minutes: number) {
  if (!value) return "";
  const [datePart, timePart] = value.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute] = timePart.split(":").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day, hour, minute + minutes));
  return shifted.toISOString().slice(0, 16);
}

function nextAvailableTimeInput(timezoneName: string, offsetMinutes: number) {
  const nextMinute = new Date(Math.ceil(Date.now() / 60_000) * 60_000);
  return toTimezoneInputValue(nextMinute.toISOString(), timezoneName, offsetMinutes);
}

function createManualCandidateRow(): ManualCandidateRow {
  return {
    row_id: `candidate-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    name: "",
    email: "",
    external_id: "",
  };
}

function StatusBadge({ value }: { value: string }) {
  return <span className={`status-badge status-${statusTone(value)}`}>{value}</span>;
}

function HealthDot({ status }: { status: string }) {
  return (
    <span
      aria-label={`${status} status`}
      className={`status-dot status-dot-${statusTone(status)}`}
    />
  );
}

function EmptyState({ label }: { label: string }) {
  return <p className="empty-state">{label}</p>;
}

export function RecruiterAssessmentsPage() {
  const { currentUser } = useAuth();
  const [view, setView] = useState<RecruiterView>("list");
  const [testTab, setTestTab] = useState<TestTab>("candidates");
  const [assessmentForm, setAssessmentForm] = useState<AssessmentCreatePayload>(
    createEmptyAssessment(),
  );
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<string | null>(
    null,
  );
  const [selectedSlotId, setSelectedSlotId] = useState<string | null>(null);
  const [slotForm, setSlotForm] = useState({
    title: "",
    start_at: "",
    end_at: "",
    duration_minutes: 60,
    timezone_name: "Asia/Kolkata",
    timezone_offset_minutes: 330,
    instructions_override: "",
    status: "scheduled" as const,
  });
  const [slotScheduleError, setSlotScheduleError] = useState("");
  const [warningToast, setWarningToast] = useState("");
  const [candidateCsv, setCandidateCsv] = useState("name,email,external_id\n");
  const [assessmentPageSuccessMessage, setAssessmentPageSuccessMessage] = useState("");
  const [questionSelection, setQuestionSelection] = useState<
    Record<string, AssessmentQuestionAssignment>
  >({});
  const [createQuestionIds, setCreateQuestionIds] = useState<string[]>([]);

  const assessmentsQuery = useAssessments(currentUser);
  const createAssessmentMutation = useCreateAssessment(currentUser);
  const updateAssessmentMutation = useUpdateAssessment(currentUser);
  const deleteAssessmentMutation = useDeleteAssessment(currentUser);
  const setQuestionsMutation = useSetAssessmentQuestions(currentUser);
  const createQuestionGroupMutation = useCreateQuestionGroup(currentUser);
  const slotsQuery = useAssessmentSlots(currentUser, selectedAssessmentId);
  const createSlotMutation = useCreateAssessmentSlot(currentUser);
  const updateSlotMutation = useUpdateAssessmentSlot(currentUser);
  const controlSlotMutation = useControlAssessmentSlot(currentUser);
  const importCandidatesMutation = useImportSlotCandidates(currentUser);
  const sendInvitesMutation = useSendSlotInvites(currentUser);
  const resendInviteMutation = useResendCandidateInvite(currentUser);
  const backfillEvaluationsMutation = useBackfillAssessmentEvaluations(currentUser);
  const candidatesQuery = useSlotCandidates(currentUser, selectedSlotId);
  const monitoringQuery = useSlotMonitoring(currentUser, selectedSlotId);
  const questionBankQuery = useQuestionBank(currentUser, {
    search: "",
    difficulty: "",
    status: "validated",
    tag: "",
  });
  const questionGroupsQuery = useQuestionGroups(currentUser, {
    search: "",
    status: "active",
  });

  const assessments = useMemo(
    () => assessmentsQuery.data?.items || [],
    [assessmentsQuery.data?.items],
  );
  const questionBankItems = useMemo(
    () => questionBankQuery.data?.items || [],
    [questionBankQuery.data?.items],
  );
  const questionById = useMemo(
    () => new Map(questionBankItems.map((question) => [question.id, question])),
    [questionBankItems],
  );
  const slots = useMemo(
    () => slotsQuery.data?.items || [],
    [slotsQuery.data?.items],
  );
  const candidates = candidatesQuery.data?.items || [];
  const monitoringItems = monitoringQuery.data?.items || [];
  const selectedAssessment = useMemo(
    () => assessments.find((item) => item.id === selectedAssessmentId) || null,
    [assessments, selectedAssessmentId],
  );
  const selectedSlot = useMemo(
    () => slots.find((item) => item.id === selectedSlotId) || null,
    [selectedSlotId, slots],
  );
  const submittedCount = monitoringItems.filter((item) =>
    ["submitted", "auto_submitted"].includes(item.status),
  ).length;
  const inProgressCount = monitoringItems.filter(
    (item) => item.status === "in_progress",
  ).length;
  const canArchive =
    Boolean(selectedAssessment) &&
    selectedAssessment?.status !== "archived";

  useEffect(() => {
    if (!selectedAssessment) {
      setQuestionSelection({});
      return;
    }
    const nextSelection: Record<string, AssessmentQuestionAssignment> = {};
    selectedAssessment.questions.forEach((question) => {
      nextSelection[question.question_id] = {
        question_id: question.question_id,
        question_order: question.question_order,
        marks: question.marks,
        is_mandatory: question.is_mandatory,
      };
    });
    setQuestionSelection(nextSelection);
  }, [selectedAssessment]);

  useEffect(() => {
    setSelectedSlotId(null);
    setTestTab("candidates");
  }, [selectedAssessmentId]);

  async function handleCreateAssessment() {
    const created = await createAssessmentMutation.mutateAsync(assessmentForm);
    if (createQuestionIds.length > 0) {
      await setQuestionsMutation.mutateAsync({
        assessmentId: created.id,
        payload: {
          questions: buildAssessmentQuestionAssignments(createQuestionIds, questionById),
        },
      });
    }
    setSelectedAssessmentId(created.id);
    setAssessmentForm(createEmptyAssessment());
    setCreateQuestionIds([]);
    setAssessmentPageSuccessMessage("Assessment created successfully.");
    setView("assessment");
  }

  async function handleArchiveAssessment() {
    if (!selectedAssessment) {
      return;
    }
    await updateAssessmentMutation.mutateAsync({
      assessmentId: selectedAssessment.id,
      payload: { status: "archived" },
    });
  }

  async function handleDeleteAssessment() {
    if (!selectedAssessment) {
      return;
    }
    await deleteAssessmentMutation.mutateAsync(selectedAssessment.id);
    setSelectedAssessmentId(null);
    setAssessmentPageSuccessMessage("Assessment deleted successfully.");
    setView("list");
  }

  async function handleUpdateAssessment(payload: Partial<AssessmentCreatePayload>) {
    if (!selectedAssessment) {
      return;
    }
    await updateAssessmentMutation.mutateAsync({
      assessmentId: selectedAssessment.id,
      payload,
    });
  }

  async function handleSaveQuestions() {
    if (!selectedAssessment) {
      return;
    }
    const questions = Object.values(questionSelection).sort(
      (left, right) => left.question_order - right.question_order,
    );
    const requiredCount = selectedAssessment.question_count_per_candidate;
    const blueprint = selectedAssessment.difficulty_blueprint || [];
    if (!selectedAssessment.shuffle_questions && questions.length !== requiredCount) {
      setWarningToast(`Same-set mode requires exactly ${requiredCount} questions.`);
      return;
    }
    const selectedDifficulties = questions.map(
      (item) => questionBankItems.find((question) => question.id === item.question_id)?.difficulty,
    );
    if (
      !selectedAssessment.shuffle_questions &&
      blueprint.some((difficulty, index) => selectedDifficulties[index] !== difficulty)
    ) {
      setWarningToast("Selected question order does not match the current difficulty template.");
      return;
    }
    if (selectedAssessment.shuffle_questions) {
      const hasEnough = QUESTION_DIFFICULTIES.every((difficulty) =>
        selectedDifficulties.filter((item) => item === difficulty).length >=
        blueprint.filter((item) => item === difficulty).length,
      );
      if (questions.length < requiredCount || !hasEnough) {
        setWarningToast("Randomized pool cannot satisfy the current difficulty template.");
        return;
      }
    }
    await setQuestionsMutation.mutateAsync({
      assessmentId: selectedAssessment.id,
      payload: { questions },
    });
  }

  async function handleCreateSlot() {
    if (!selectedAssessmentId) {
      return;
    }
    setSlotScheduleError("");
    let timezoneOffsetMinutes: number;
    let startAt: string;
    let endAt: string;
    try {
      timezoneOffsetMinutes = timezoneOffsetMinutesForLocalDateTime(
        slotForm.start_at || slotForm.end_at,
        slotForm.timezone_name,
        slotForm.timezone_offset_minutes,
      );
      startAt = toIsoDateTimeForTimezone(
        slotForm.start_at,
        slotForm.timezone_name,
        timezoneOffsetMinutes,
      );
      endAt = toIsoDateTimeForTimezone(
        slotForm.end_at,
        slotForm.timezone_name,
        timezoneOffsetMinutes,
      );
      if (new Date(startAt).getTime() < Date.now()) {
        throw new Error("Past times are unavailable. Choose a future start time.");
      }
      if (
        new Date(endAt).getTime() <
        new Date(startAt).getTime() + slotForm.duration_minutes * 60_000
      ) {
        throw new Error(
          `End time must be at least ${slotForm.duration_minutes} minutes after the start time.`,
        );
      }
    } catch (error) {
      const message = errorMessage(error) || "Choose a valid start and end time.";
      setSlotScheduleError(message);
      setWarningToast(message);
      return;
    }
    const created = await createSlotMutation.mutateAsync({
      assessmentId: selectedAssessmentId,
      payload: {
        ...slotForm,
        timezone_offset_minutes: timezoneOffsetMinutes,
        start_at: startAt,
        end_at: endAt,
      },
    });
    setSelectedSlotId(created.id);
    setSlotForm({
      title: "",
      start_at: "",
      end_at: "",
      duration_minutes: 60,
      timezone_name: "Asia/Kolkata",
      timezone_offset_minutes: 330,
      instructions_override: "",
      status: "scheduled",
    });
    setView("test");
  }

  async function handleImportCandidates(csvText = candidateCsv) {
    if (!selectedSlotId) {
      return;
    }
    await importCandidatesMutation.mutateAsync({
      slotId: selectedSlotId,
      payload: { csv_text: csvText },
    });
  }

  async function handleSendInvites(candidateAssessmentIds: string[] = []) {
    if (!selectedSlotId) {
      return;
    }
    await sendInvitesMutation.mutateAsync({
      slotId: selectedSlotId,
      payload: {
        candidate_assessment_ids: candidateAssessmentIds,
      },
    });
  }

  function openAssessment(assessmentId: string) {
    setSelectedAssessmentId(assessmentId);
    setView("assessment");
  }

  function openTest(slotId: string) {
    setSelectedSlotId(slotId);
    setTestTab("candidates");
    setView("test");
  }

  function toggleQuestion(questionId: string, checked: boolean) {
    setQuestionSelection((current) => {
      if (!checked) {
        const next = { ...current };
        delete next[questionId];
        return next;
      }
      const requiredCount = selectedAssessment?.question_count_per_candidate || 0;
      const question = questionById.get(questionId);
      const blueprint = selectedAssessment?.difficulty_blueprint || [];
      if (question && !blueprint.includes(question.difficulty)) {
        setWarningToast(
          `${question.difficulty} questions are not included in this assessment template.`,
        );
        return current;
      }
      if (
        selectedAssessment &&
        !selectedAssessment.shuffle_questions &&
        requiredCount > 0 &&
        Object.keys(current).length >= requiredCount
      ) {
        setWarningToast(
          `Same-set mode allows exactly ${requiredCount} questions. Remove one before adding another.`,
        );
        return current;
      }
      if (selectedAssessment && !selectedAssessment.shuffle_questions) {
        const expectedDifficulty = blueprint[Object.keys(current).length];
        if (question && expectedDifficulty && question.difficulty !== expectedDifficulty) {
          setWarningToast(
            `The next template slot requires a ${expectedDifficulty} question.`,
          );
          return current;
        }
      }
      return {
        ...current,
        [questionId]: {
          question_id: questionId,
          question_order: Object.keys(current).length + 1,
          marks: 10,
          is_mandatory: true,
        },
      };
    });
  }

  return (
    <main className="recruiter-assessments-page assessment-flow-page">
      {warningToast ? (
        <div className="question-flow-toast-stack" aria-live="assertive">
          <div className="question-flow-toast is-warning" role="alert">
            <div><strong>Question selection</strong><p>{warningToast}</p></div>
            <button type="button" className="question-flow-toast-dismiss" onClick={() => setWarningToast("")}>Close</button>
          </div>
        </div>
      ) : null}
      {view === "list" ? (
        <AssessmentList
          assessments={assessments}
          loading={assessmentsQuery.isLoading}
          onAddNew={() => setView("create")}
          onOpen={openAssessment}
        />
      ) : null}

      {view === "create" ? (
        <CreateAssessmentView
          assessmentForm={assessmentForm}
          questionBank={questionBankItems}
          questionGroups={questionGroupsQuery.data?.items || []}
          questionBankLoading={questionBankQuery.isLoading}
          questionGroupsLoading={questionGroupsQuery.isLoading}
          selectedQuestionIds={createQuestionIds}
          createGroupPending={createQuestionGroupMutation.isPending}
          createGroupError={errorMessage(createQuestionGroupMutation.error)}
          createPending={
            createAssessmentMutation.isPending || setQuestionsMutation.isPending
          }
          createError={
            errorMessage(createAssessmentMutation.error) ||
            errorMessage(setQuestionsMutation.error)
          }
          onBack={() => setView("list")}
          onCreate={() => void handleCreateAssessment()}
          onChange={setAssessmentForm}
          onChangeQuestions={setCreateQuestionIds}
          onCreateGroup={(payload) => createQuestionGroupMutation.mutateAsync(payload)}
        />
      ) : null}

      {view === "assessment" && selectedAssessment ? (
        <AssessmentDetailView
          assessment={selectedAssessment}
          slots={slots}
          slotsLoading={slotsQuery.isLoading}
          questionBank={questionBankQuery.data?.items || []}
          selectedQuestions={questionSelection}
          canArchive={canArchive}
          questionPending={setQuestionsMutation.isPending}
          questionError={errorMessage(setQuestionsMutation.error)}
          publishError={errorMessage(updateAssessmentMutation.error)}
          publishPending={updateAssessmentMutation.isPending}
          deletePending={deleteAssessmentMutation.isPending}
          deleteError={errorMessage(deleteAssessmentMutation.error)}
          assessmentUpdatePending={updateAssessmentMutation.isPending}
          slotForm={slotForm}
          slotPending={createSlotMutation.isPending}
          slotError={slotScheduleError || errorMessage(createSlotMutation.error)}
          successMessage={assessmentPageSuccessMessage}
          evaluationBackfillPending={backfillEvaluationsMutation.isPending}
          evaluationBackfillError={errorMessage(backfillEvaluationsMutation.error)}
          evaluationBackfillResult={backfillEvaluationsMutation.data ?? null}
          onBack={() => {
            setAssessmentPageSuccessMessage("");
            setView("list");
          }}
          onOpenTest={openTest}
          onArchive={() => void handleArchiveAssessment()}
          onDeleteAssessment={handleDeleteAssessment}
          onUpdateAssessment={handleUpdateAssessment}
          onSaveQuestions={handleSaveQuestions}
          onToggleQuestion={toggleQuestion}
          onUpdateQuestionSelection={setQuestionSelection}
          onChangeSlot={(nextSlotForm) => {
            setSlotScheduleError("");
            setSlotForm(nextSlotForm);
          }}
          onCreateSlot={handleCreateSlot}
          onBackfillEvaluations={() =>
            backfillEvaluationsMutation.mutateAsync({
              assessmentId: selectedAssessment.id,
              payload: { force: true },
            })
          }
        />
      ) : null}

      {view === "test" && selectedAssessment && selectedSlot ? (
        <TestDetailView
          assessment={selectedAssessment}
          slot={selectedSlot}
          tab={testTab}
          candidates={candidates}
          monitoringItems={monitoringItems}
          monitoringLoading={monitoringQuery.isLoading}
          submittedCount={submittedCount}
          inProgressCount={inProgressCount}
          candidateCsv={candidateCsv}
          importPending={importCandidatesMutation.isPending}
          invitePending={sendInvitesMutation.isPending}
          slotUpdatePending={updateSlotMutation.isPending || controlSlotMutation.isPending}
          importErrors={importCandidatesMutation.data?.errors || []}
          importError={errorMessage(importCandidatesMutation.error)}
          inviteError={errorMessage(sendInvitesMutation.error)}
          slotUpdateError={
            errorMessage(updateSlotMutation.error) ||
            errorMessage(controlSlotMutation.error)
          }
          evaluationBackfillPending={backfillEvaluationsMutation.isPending}
          evaluationBackfillError={errorMessage(backfillEvaluationsMutation.error)}
          evaluationBackfillResult={backfillEvaluationsMutation.data ?? null}
          resendPendingId={
            resendInviteMutation.variables &&
              typeof resendInviteMutation.variables === "string"
              ? resendInviteMutation.variables
              : null
          }
          onBack={() => setView("assessment")}
          onTabChange={setTestTab}
          onCsvChange={setCandidateCsv}
          onImport={(csvText) => void handleImportCandidates(csvText)}
          onSendInvites={(candidateAssessmentIds) =>
            void handleSendInvites(candidateAssessmentIds)
          }
          onUpdateSlot={(payload) =>
            updateSlotMutation.mutateAsync({
              slotId: selectedSlot.id,
              payload,
            })
          }
          onControlSlot={(payload) =>
            controlSlotMutation.mutateAsync({
              slotId: selectedSlot.id,
              payload,
            })
          }
          onBackfillEvaluations={(candidateAssessmentIds) =>
            backfillEvaluationsMutation.mutateAsync({
              assessmentId: selectedAssessment.id,
              payload: {
                force: true,
                candidate_assessment_ids: candidateAssessmentIds,
              },
            })
          }
          onResend={(candidateAssessmentId) =>
            void resendInviteMutation.mutateAsync(candidateAssessmentId)
          }
        />
      ) : null}
    </main>
  );
}

function MetricTile({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="assessment-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function CreateAssessmentView({
  assessmentForm,
  questionBank,
  questionGroups,
  questionBankLoading,
  questionGroupsLoading,
  selectedQuestionIds,
  createGroupPending,
  createGroupError,
  createPending,
  createError,
  onBack,
  onCreate,
  onChange,
  onChangeQuestions,
  onCreateGroup,
}: {
  assessmentForm: AssessmentCreatePayload;
  questionBank: QuestionRecord[];
  questionGroups: QuestionGroupRecord[];
  questionBankLoading: boolean;
  questionGroupsLoading: boolean;
  selectedQuestionIds: string[];
  createGroupPending: boolean;
  createGroupError: string;
  createPending: boolean;
  createError: string;
  onBack: () => void;
  onCreate: () => void;
  onChange: (payload: AssessmentCreatePayload) => void;
  onChangeQuestions: (questionIds: string[]) => void;
  onCreateGroup: (payload: QuestionGroupCreatePayload) => Promise<QuestionGroupRecord>;
}) {
  const scoringTotal =
    assessmentForm.test_case_score_weight +
    assessmentForm.coding_score_weight +
    assessmentForm.ai_score_weight;
  const [activeSection, setActiveSection] =
    useState<AssessmentCreateSection>("basics");
  const [questionSetMode, setQuestionSetMode] =
    useState<QuestionSetMode>("select-questions");
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [selectedImportGroupId, setSelectedImportGroupId] = useState("");
  const [customGroupName, setCustomGroupName] = useState("");
  const [customGroupDesc, setCustomGroupDesc] = useState("");
  const [groupSaveSuccess, setGroupSaveSuccess] = useState("");
  const [desiredQuestionCount, setDesiredQuestionCount] = useState(
    assessmentForm.question_count_per_candidate || 4,
  );
  const [difficultyBlueprint, setDifficultyBlueprint] = useState<DifficultyLevel[]>(
    () => assessmentForm.difficulty_blueprint.length
      ? assessmentForm.difficulty_blueprint
      : createQuestionBlueprint(assessmentForm.question_count_per_candidate || 4),
  );
  const [selectionWarning, setSelectionWarning] = useState("");
  const enabledPolicyCount = [
    assessmentForm.allow_resume,
    assessmentForm.shuffle_questions,
    assessmentForm.show_score_to_candidate,
    assessmentForm.hidden_feedback_mode === "summary",
  ].filter(Boolean).length;
  const scoringIsValid = scoringTotal === 100;
  const basicsReady =
    assessmentForm.title.trim().length >= 3 &&
    assessmentForm.passing_score >= 0 &&
    assessmentForm.passing_score <= 100;
  const questionById = useMemo(
    () => new Map(questionBank.map((question) => [question.id, question])),
    [questionBank],
  );
  const selectedGroup = questionGroups.find((group) => group.id === selectedGroupId);
  const selectedQuestionViews = selectedQuestionIds
    .map((questionId) => {
      const bankQuestion = questionById.get(questionId);
      if (bankQuestion) {
        return {
          id: bankQuestion.id,
          title: bankQuestion.title,
          difficulty: bankQuestion.difficulty,
          tags: bankQuestion.tags,
        };
      }
      const groupQuestion = selectedGroup?.questions.find(
        (question) => question.id === questionId,
      );
      return groupQuestion
        ? {
          id: groupQuestion.id,
          title: groupQuestion.title,
          difficulty: groupQuestion.difficulty,
          tags: [],
        }
        : null;
    })
    .filter((question): question is {
      id: string;
      title: string;
      difficulty: DifficultyLevel;
      tags: string[];
    } => Boolean(question));
  const blueprintMismatches = assessmentForm.shuffle_questions ? [] : selectedQuestionViews.filter((question, index) => {
    const expectedDifficulty = difficultyBlueprint[index];
    return expectedDifficulty && question.difficulty !== expectedDifficulty;
  });
  const blueprintCounts = difficultyBlueprint.reduce<Record<DifficultyLevel, number>>(
    (counts, difficulty) => ({ ...counts, [difficulty]: counts[difficulty] + 1 }),
    { easy: 0, medium: 0, hard: 0 },
  );
  const selectedDifficultyCounts = selectedQuestionViews.reduce<Record<DifficultyLevel, number>>(
    (counts, question) => ({
      ...counts,
      [question.difficulty]: counts[question.difficulty] + 1,
    }),
    { easy: 0, medium: 0, hard: 0 },
  );
  const randomPoolMatchesBlueprint = QUESTION_DIFFICULTIES.every(
    (difficulty) => selectedDifficultyCounts[difficulty] >= blueprintCounts[difficulty],
  );
  const templateMarks = calculateQuestionTemplateMarks(difficultyBlueprint);
  const questionSetReady = assessmentForm.shuffle_questions
    ? selectedQuestionIds.length >= desiredQuestionCount && randomPoolMatchesBlueprint
    : selectedQuestionIds.length === desiredQuestionCount && blueprintMismatches.length === 0;
  const rulesReady = scoringIsValid && assessmentForm.supported_languages.length > 0;
  const requiredMark = <em className="required-indicator" aria-hidden="true">*</em>;
  const sectionDefinitions = [
    {
      id: "basics" as const,
      label: "Basics",
      title: "Template details",
      description: "Name the assessment, set the time box, and add candidate-facing instructions.",
      meta: "Name, duration, pass mark",
      ready: basicsReady,
    },
    {
      id: "questions" as const,
      label: "Question set",
      title: "Choose the question set",
      description: "Build the pool, set the per-candidate count, and align it with the blueprint.",
      meta: `${selectedQuestionIds.length} in pool, ${desiredQuestionCount} per candidate`,
      ready: questionSetReady,
    },
    {
      id: "rules" as const,
      label: "Rules",
      title: "Finalize scoring and policy",
      description: "Balance the evaluation weights, languages, and candidate experience rules.",
      meta: "Scoring, languages, policy",
      ready: rulesReady,
    },
  ];
  const activeSectionIndex = sectionDefinitions.findIndex((section) => section.id === activeSection);
  const activeSectionDefinition =
    sectionDefinitions[activeSectionIndex] ?? sectionDefinitions[0];
  const canCreateAssessment =
    !createPending &&
    basicsReady &&
    questionSetReady &&
    rulesReady &&
    assessmentForm.title.trim().length > 0 &&
    scoringIsValid &&
    assessmentForm.supported_languages.length > 0;

  function sectionReady(section: AssessmentCreateSection) {
    return section === "basics"
      ? basicsReady
      : section === "questions"
        ? questionSetReady
        : rulesReady;
  }

  function sectionState(section: AssessmentCreateSection) {
    const done = sectionReady(section);
    if (activeSection === section) {
      return done ? "is-active is-complete" : "is-active is-needed";
    }
    return done ? "is-complete" : "is-needed";
  }

  function moveToSection(section: AssessmentCreateSection) {
    setActiveSection(section);
  }

  function goToPreviousSection() {
    if (activeSectionIndex <= 0) {
      return;
    }
    setActiveSection(sectionDefinitions[activeSectionIndex - 1].id);
  }

  function goToNextSection() {
    if (!sectionReady(activeSection) || activeSectionIndex >= sectionDefinitions.length - 1) {
      return;
    }
    setActiveSection(sectionDefinitions[activeSectionIndex + 1].id);
  }

  function toggleLanguage(language: string, checked: boolean) {
    const nextLanguages = checked
      ? [...assessmentForm.supported_languages, language]
      : assessmentForm.supported_languages.filter((item) => item !== language);
    onChange({
      ...assessmentForm,
      supported_languages: Array.from(new Set(nextLanguages)),
    });
  }

  function updateQuestionCount(count: number) {
    const safeCount = Math.max(1, Math.min(50, count || 1));
    setDesiredQuestionCount(safeCount);
    const nextBlueprint = Array.from(
      { length: safeCount },
      (_, index) => difficultyBlueprint[index] || "medium",
    );
    setDifficultyBlueprint(nextBlueprint);
    if (!assessmentForm.shuffle_questions && selectedQuestionIds.length > safeCount) {
      onChangeQuestions(selectedQuestionIds.slice(0, safeCount));
      setSelectionWarning(`Same-set mode keeps exactly ${safeCount} questions.`);
    }
    onChange({
      ...assessmentForm,
      question_count_per_candidate: safeCount,
      difficulty_blueprint: nextBlueprint,
    });
  }

  function applyGroupQuestions(group: QuestionGroupRecord) {
    const nextCount = Math.max(1, group.question_ids.length);
    const nextBlueprint = group.questions.length
      ? group.questions.map((question) => question.difficulty)
      : createQuestionBlueprint(group.question_ids.length);
    setDesiredQuestionCount(nextCount);
    setDifficultyBlueprint(nextBlueprint);
    onChange({
      ...assessmentForm,
      question_count_per_candidate: nextCount,
      difficulty_blueprint: nextBlueprint,
    });
    onChangeQuestions(group.question_ids);
  }

  function chooseGroup(groupId: string) {
    setSelectedGroupId(groupId);
    const group = questionGroups.find((item) => item.id === groupId);
    if (!group) {
      return;
    }
    applyGroupQuestions(group);
  }

  function handleImportFromGroup() {
    const group = questionGroups.find((item) => item.id === selectedImportGroupId);
    if (!group) {
      return;
    }
    const nextQuestionIds = Array.from(
      new Set([...selectedQuestionIds, ...group.question_ids]),
    );
    if (desiredQuestionCount > nextQuestionIds.length) {
      updateQuestionCount(nextQuestionIds.length);
    }
    onChangeQuestions(nextQuestionIds);
    setGroupSaveSuccess(`Imported ${group.name}.`);
  }

  async function handleCreateGroup() {
    if (!customGroupName.trim() || selectedQuestionIds.length === 0) {
      return;
    }
    const created = await onCreateGroup({
      name: customGroupName.trim(),
      description: customGroupDesc.trim(),
      question_ids: selectedQuestionIds,
      status: "active",
    });
    setSelectedGroupId(created.id);
    setGroupSaveSuccess(`Saved ${created.name} and applied it to this assessment.`);
  }

  function selectQuestion(questionId: string, checked: boolean) {
    if (checked) {
      if (selectedQuestionIds.includes(questionId)) {
        return;
      }
      const question = questionById.get(questionId);
      if (question && !difficultyBlueprint.includes(question.difficulty)) {
        setSelectionWarning(
          `${question.difficulty} questions are outside this template. Update the blueprint to use them.`,
        );
        return;
      }
      if (!assessmentForm.shuffle_questions && selectedQuestionIds.length >= desiredQuestionCount) {
        setSelectionWarning(
          `Same-set mode allows exactly ${desiredQuestionCount} questions. Remove one before adding another.`,
        );
        return;
      }
      const expectedDifficulty = difficultyBlueprint[selectedQuestionIds.length];
      if (
        !assessmentForm.shuffle_questions &&
        question &&
        expectedDifficulty &&
        question.difficulty !== expectedDifficulty
      ) {
        setSelectionWarning(
          `Question ${selectedQuestionIds.length + 1} must be ${expectedDifficulty}. Choose a matching question.`,
        );
        return;
      }
      onChangeQuestions([...selectedQuestionIds, questionId]);
      return;
    }
    onChangeQuestions(selectedQuestionIds.filter((item) => item !== questionId));
  }

  function changeBlueprint(index: number, difficulty: DifficultyLevel) {
    const nextBlueprint = difficultyBlueprint.map((item, itemIndex) =>
      itemIndex === index ? difficulty : item,
    );
    setDifficultyBlueprint(nextBlueprint);
    onChange({ ...assessmentForm, difficulty_blueprint: nextBlueprint });
  }

  function applyScoringPreset(
    testCaseWeight: number,
    codingWeight: number,
    aiWeight: number,
  ) {
    onChange({
      ...assessmentForm,
      test_case_score_weight: testCaseWeight,
      coding_score_weight: codingWeight,
      ai_score_weight: aiWeight,
    });
  }

  return (
    <section className="assessment-drilldown assessment-create-drilldown">
      {selectionWarning ? (
        <div className="question-flow-toast-stack" aria-live="assertive">
          <div className="question-flow-toast is-warning" role="alert">
            <div><strong>Question selection</strong><p>{selectionWarning}</p></div>
            <button type="button" className="question-flow-toast-dismiss" onClick={() => setSelectionWarning("")}>Close</button>
          </div>
        </div>
      ) : null}
      <button type="button" className="assessment-back-link" onClick={onBack}>
        <ArrowLeft size={16} />
        Back to assessments
      </button>

      <Card className="assessment-panel assessment-panel-wide assessment-create-panel">
        <div className="assessment-builder-wizard">
          <div className="assessment-builder-banner">
            <div className="assessment-builder-banner-copy">
              <span className="panel-eyebrow">New Assessment</span>
              <h2>Create assessment</h2>
              <p>Set the basics, choose the question set, and finish the scoring rules in three guided pages.</p>
            </div>
            <div className="assessment-builder-metrics" aria-label="Assessment setup summary">
              <span>
                <strong>{assessmentForm.question_count_per_candidate}</strong>
                Questions
              </span>
              <span>
                <strong>{assessmentForm.passing_score}%</strong>
                Passing
              </span>
              <span>
                <strong>{selectedQuestionIds.length}</strong>
                In pool
              </span>
              <span>
                <strong>{assessmentForm.supported_languages.length}</strong>
                Languages
              </span>
              <span>
                <strong>{enabledPolicyCount}</strong>
                Policies
              </span>
              <span>
                <strong>{assessmentForm.title.trim() ? "Drafting" : "Start"}</strong>
                Status
              </span>
            </div>
          </div>

          <div className="assessment-step-rail assessment-builder-rail" aria-label="Assessment creation steps">
            {sectionDefinitions.map((step, index) => (
              <button
                key={step.id}
                type="button"
                className={sectionState(step.id)}
                onClick={() => moveToSection(step.id)}
                aria-current={activeSection === step.id ? "step" : undefined}
              >
                <span>{index + 1}</span>
                <strong>{step.label}</strong>
                <em>{step.ready ? "Ready" : step.meta}</em>
              </button>
            ))}
          </div>

          <div className="assessment-builder-shell">
            <div className="assessment-builder-header">
              <div>
                <p>
                  Page {activeSectionIndex + 1} of {sectionDefinitions.length}
                </p>
                <h3>{activeSectionDefinition.title}</h3>
                <span>{activeSectionDefinition.description}</span>
              </div>
              <strong
                className={
                  sectionReady(activeSection)
                    ? "assessment-builder-status is-ready"
                    : "assessment-builder-status is-needed"
                }
              >
                {sectionReady(activeSection) ? "Ready to continue" : "Required fields pending"}
              </strong>
            </div>

            <p className="assessment-builder-required-note">
              Fields marked with {requiredMark} are required before you continue.
            </p>

            {activeSection === "basics" ? (
              <div className="assessment-form-stack assessment-form-pro assessment-create-form">
                <div className="question-status-strip" aria-label="Assessment basics readiness">
                  <span className={assessmentForm.title.trim().length >= 3 ? "is-ready" : "is-needed"}>
                    Title {assessmentForm.title.trim().length >= 3 ? "ready" : "needed"}
                  </span>
                  <span
                    className={
                      assessmentForm.passing_score >= 0 && assessmentForm.passing_score <= 100
                        ? "is-ready"
                        : "is-needed"
                    }
                  >
                    Passing score{" "}
                    {assessmentForm.passing_score >= 0 && assessmentForm.passing_score <= 100
                      ? "ready"
                      : "out of range"}
                  </span>
                </div>

                <div className="assessment-form-section assessment-section-pro assessment-builder-page-card">
                  <div className="assessment-section-heading">
                    <span className="assessment-section-icon">
                      <FileText size={18} />
                    </span>
                    <div>
                      <span className="panel-eyebrow">Basics</span>
                      <h3>Template details</h3>
                    </div>
                  </div>

                  <label className="field field-pro field-full">
                    <span>
                      Assessment title {requiredMark}
                    </span>
                    <input
                      placeholder="Backend Developer Screening"
                      value={assessmentForm.title}
                      onChange={(event) =>
                        onChange({ ...assessmentForm, title: event.target.value })
                      }
                    />
                  </label>

                  <div className="assessment-inline-fields">
                    <label className="field field-pro metric-field">
                      <span>
                        Passing score {requiredMark}
                      </span>
                      <div className="field-control-with-icon">
                        <Gauge size={16} />
                        <input
                          type="number"
                          min={0}
                          max={100}
                          value={assessmentForm.passing_score}
                          onChange={(event) =>
                            onChange({
                              ...assessmentForm,
                              passing_score: Number(event.target.value),
                            })
                          }
                        />
                        <em>%</em>
                      </div>
                    </label>
                  </div>

                  <div className="assessment-inline-fields">
                    <label className="field field-pro field-full">
                      <span>Description</span>
                      <textarea
                        placeholder="Role, level, skills, and what this assessment measures"
                        value={assessmentForm.description}
                        onChange={(event) =>
                          onChange({ ...assessmentForm, description: event.target.value })
                        }
                      />
                    </label>
                    <label className="field field-pro field-full">
                      <span>Candidate instructions</span>
                      <textarea
                        placeholder="Rules, allowed languages, timing expectations, and integrity notes"
                        value={assessmentForm.instructions}
                        onChange={(event) =>
                          onChange({ ...assessmentForm, instructions: event.target.value })
                        }
                      />
                    </label>
                  </div>
                </div>
              </div>
            ) : null}

            {activeSection === "questions" ? (
              <div className="assessment-form-stack assessment-form-pro assessment-create-form">
                <div className="question-status-strip" aria-label="Assessment question set readiness">
                  <span
                    className={
                      selectedQuestionIds.length >= desiredQuestionCount && selectedQuestionIds.length > 0
                        ? "is-ready"
                        : "is-needed"
                    }
                  >
                    Pool {selectedQuestionIds.length} / {desiredQuestionCount}
                  </span>
                  <span className={desiredQuestionCount > 0 ? "is-ready" : "is-needed"}>
                    Per candidate {desiredQuestionCount}
                  </span>
                  <span className={questionSetReady ? "is-ready" : "is-needed"}>
                    Delivery {assessmentForm.shuffle_questions ? "randomized" : "same set"}
                  </span>
                </div>

                <div className="assessment-form-section assessment-section-pro assessment-builder-page-card">
                  <div className="assessment-section-heading">
                    <span className="assessment-section-icon is-green">
                      <BadgeCheck size={18} />
                    </span>
                    <div>
                      <span className="panel-eyebrow">Question Set</span>
                      <h3>Choose the questions used by every test slot</h3>
                    </div>
                  </div>

                  <div className="question-set-mode-grid" role="tablist" aria-label="Question set source">
                    {[
                      {
                        mode: "select-questions" as const,
                        title: "Select Question",
                        copy: "Choose individual questions.",
                      },
                      {
                        mode: "select-groups" as const,
                        title: "Select Groups",
                        copy: "Use an existing group.",
                      },
                      {
                        mode: "custom" as const,
                        title: "Custom Group Composer",
                        copy: "Compose and save a group.",
                      },
                    ].map((option) => (
                      <button
                        key={option.mode}
                        type="button"
                        className={questionSetMode === option.mode ? "is-active" : ""}
                        onClick={() => {
                          setQuestionSetMode(option.mode);
                          setGroupSaveSuccess("");
                          if (option.mode === "select-questions") {
                            setSelectedGroupId("");
                          }
                        }}
                      >
                        <strong>{option.title}</strong>
                        <span>{option.copy}</span>
                      </button>
                    ))}
                  </div>

                  <div className="assessment-inline-fields">
                    <label className="field field-pro metric-field">
                      <span>
                        Questions per candidate {requiredMark}
                      </span>
                      <input
                        type="number"
                        min={1}
                        max={50}
                        value={desiredQuestionCount}
                        onChange={(event) => updateQuestionCount(Number(event.target.value))}
                      />
                    </label>
                    <div className="question-delivery-toggle" role="group" aria-label="Question delivery mode">
                      <button
                        type="button"
                        className={!assessmentForm.shuffle_questions ? "is-active" : ""}
                        onClick={() => {
                          const exactIds = selectedQuestionIds.slice(0, desiredQuestionCount);
                          if (selectedQuestionIds.length > desiredQuestionCount) {
                            onChangeQuestions(exactIds);
                            setSelectionWarning(`Same-set mode keeps exactly ${desiredQuestionCount} questions.`);
                          }
                          onChange({
                            ...assessmentForm,
                            shuffle_questions: false,
                          });
                        }}
                      >
                        <strong>Same set</strong>
                        <span>
                          Every candidate gets the first {desiredQuestionCount} selected questions.
                        </span>
                      </button>
                      <button
                        type="button"
                        className={assessmentForm.shuffle_questions ? "is-active" : ""}
                        onClick={() =>
                          onChange({
                            ...assessmentForm,
                            shuffle_questions: true,
                          })
                        }
                      >
                        <strong>Randomize set</strong>
                        <span>Pick {desiredQuestionCount} questions from the full selected pool.</span>
                      </button>
                    </div>
                  </div>

                  {questionSetMode === "custom" ? (
                    <div className="custom-group-composer-card">
                      <div className="question-set-subhead">
                        <strong>Custom group composer</strong>
                        <span>Save the selected questions as a reusable active group.</span>
                      </div>
                      <div className="assessment-inline-fields">
                        <label className="field field-pro">
                          <span>Group name</span>
                          <input
                            value={customGroupName}
                            onChange={(event) => setCustomGroupName(event.target.value)}
                            placeholder="Backend screening pack"
                          />
                        </label>
                        <label className="field field-pro">
                          <span>Import from existing group</span>
                          <div className="composer-import-row">
                            <select
                              value={selectedImportGroupId}
                              onChange={(event) => setSelectedImportGroupId(event.target.value)}
                            >
                              <option value="">Choose group</option>
                              {questionGroups.map((group) => (
                                <option key={group.id} value={group.id}>
                                  {group.name}
                                </option>
                              ))}
                            </select>
                            <Button
                              type="button"
                              variant="secondary"
                              disabled={!selectedImportGroupId}
                              onClick={handleImportFromGroup}
                            >
                              Import
                            </Button>
                          </div>
                        </label>
                      </div>
                      <label className="field field-pro">
                        <span>Description</span>
                        <textarea
                          value={customGroupDesc}
                          onChange={(event) => setCustomGroupDesc(event.target.value)}
                          placeholder="What role, difficulty, or hiring round this group is for"
                        />
                      </label>
                      <div className="assessment-actions-row">
                        <Button
                          type="button"
                          disabled={
                            createGroupPending ||
                            !customGroupName.trim() ||
                            selectedQuestionIds.length === 0
                          }
                          onClick={() => void handleCreateGroup()}
                        >
                          {createGroupPending ? "Saving..." : "Save Group & Apply"}
                        </Button>
                      </div>
                      {groupSaveSuccess ? <p className="helper-success">{groupSaveSuccess}</p> : null}
                      {createGroupError ? <p className="form-error">{createGroupError}</p> : null}
                    </div>
                  ) : null}

                  <div className="questions-composer-grid">
                    {questionSetMode === "select-groups" ? (
                      <div className="group-pick-grid group-picker-column">
                        {questionGroupsLoading ? (
                          <EmptyState label="Loading groups..." />
                        ) : questionGroups.length ? (
                          questionGroups.map((group) => (
                            <button
                              key={group.id}
                              type="button"
                              className={selectedGroupId === group.id ? "is-selected" : ""}
                              onClick={() => chooseGroup(group.id)}
                            >
                              <strong>{group.name}</strong>
                              <span>{group.question_count} questions</span>
                              <em>
                                {group.difficulty_breakdown.easy} easy ·{" "}
                                {group.difficulty_breakdown.medium} medium ·{" "}
                                {group.difficulty_breakdown.hard} hard
                              </em>
                            </button>
                          ))
                        ) : (
                          <EmptyState label="No active question groups available yet." />
                        )}
                      </div>
                    ) : (
                      <div className="question-bank-picker">
                        <div className="question-set-subhead">
                          <strong>Question bank</strong>
                          <span>
                            Only template-matching questions can be added
                          </span>
                        </div>
                        <div className="template-quota-grid" aria-label="Question template progress">
                          {QUESTION_DIFFICULTIES.filter(
                            (difficulty) => blueprintCounts[difficulty] > 0,
                          ).map((difficulty) => {
                            const complete = selectedDifficultyCounts[difficulty] >= blueprintCounts[difficulty];
                            return (
                              <div key={difficulty} className={complete ? "is-complete" : "is-needed"}>
                                <span className={`difficulty-chip difficulty-${difficulty}`}>{difficulty}</span>
                                <strong>{selectedDifficultyCounts[difficulty]} / {blueprintCounts[difficulty]}</strong>
                                <em>{complete ? "Requirement met" : `${blueprintCounts[difficulty] - selectedDifficultyCounts[difficulty]} still needed`}</em>
                              </div>
                            );
                          })}
                        </div>
                        <div className="question-bank-pick-list">
                          {questionBankLoading ? (
                            <EmptyState label="Loading validated questions..." />
                          ) : questionBank.length ? (
                            questionBank.map((question) => {
                              const selected = selectedQuestionIds.includes(question.id);
                              const inTemplate = difficultyBlueprint.includes(question.difficulty);
                              const nextDifficulty = difficultyBlueprint[selectedQuestionIds.length];
                              const canAdd = inTemplate && (
                                assessmentForm.shuffle_questions || question.difficulty === nextDifficulty
                              );
                              return (
                                <label
                                  key={question.id}
                                  className={`question-pick-row ${selected ? "is-selected" : ""} ${!selected && !canAdd ? "is-disabled" : ""}`}
                                >
                                  <input
                                    type="checkbox"
                                    checked={selected}
                                    disabled={!selected && !canAdd}
                                    onChange={(event) =>
                                      selectQuestion(question.id, event.target.checked)
                                    }
                                  />
                                  <span>
                                    <strong>{question.title}</strong>
                                    <em>
                                      {question.difficulty} ·{" "}
                                      {question.tags.slice(0, 3).join(", ") || "No tags"}
                                    </em>
                                    {!selected && !canAdd ? (
                                      <small>
                                        {!inTemplate
                                          ? "Not used by this template"
                                          : `Next slot requires ${nextDifficulty}`}
                                      </small>
                                    ) : null}
                                  </span>
                                </label>
                              );
                            })
                          ) : (
                            <EmptyState label="No validated questions available yet." />
                          )}
                        </div>
                      </div>
                    )}

                    <div className="questions-blueprint-and-selected">
                      <div className="difficulty-blueprint">
                        <div className="question-set-subhead">
                          <strong>Difficulty blueprint</strong>
                          <span>
                            Set the expected shape for the {desiredQuestionCount} questions delivered in a
                            test.
                          </span>
                        </div>
                        <div className="difficulty-slot-grid">
                          {difficultyBlueprint.map((difficulty, index) => (
                            <label key={`difficulty-${index}`}>
                              <span>Q{index + 1} · {templateMarks[index]} marks</span>
                              <select
                                value={difficulty}
                                onChange={(event) =>
                                  changeBlueprint(index, event.target.value as DifficultyLevel)
                                }
                              >
                                {QUESTION_DIFFICULTIES.map((item) => (
                                  <option key={item} value={item}>
                                    {item}
                                  </option>
                                ))}
                              </select>
                            </label>
                          ))}
                        </div>
                      </div>

                      {selectedQuestionIds.length ? (
                        <div className="selected-question-order">
                          <div className="question-set-subhead">
                            <strong>Selected question pool</strong>
                            <span>
                              {assessmentForm.shuffle_questions
                                ? `${desiredQuestionCount} will be randomized per candidate`
                                : `First ${desiredQuestionCount} will be used for every candidate`}
                            </span>
                          </div>
                          {selectedQuestionViews.map((question, index) => {
                            const expectedDifficulty = assessmentForm.shuffle_questions
                              ? undefined
                              : difficultyBlueprint[index];
                            const isMismatch =
                              expectedDifficulty && question.difficulty !== expectedDifficulty;
                            return (
                              <article key={question.id} className={isMismatch ? "has-warning" : ""}>
                                <span className="question-order-index">{index + 1}</span>
                                <div>
                                  <strong>{question.title}</strong>
                                  <em>
                                    {question.difficulty}
                                    {expectedDifficulty ? ` · expected ${expectedDifficulty}` : ""}
                                  </em>
                                </div>
                                {questionSetMode !== "select-groups" ? (
                                  <div className="question-order-actions">
                                    <button
                                      type="button"
                                      disabled={index === 0}
                                      onClick={() =>
                                        onChangeQuestions(
                                          reorderQuestionIds(selectedQuestionIds, index, index - 1),
                                        )
                                      }
                                    >
                                      Up
                                    </button>
                                    <button
                                      type="button"
                                      disabled={index === selectedQuestionIds.length - 1}
                                      onClick={() =>
                                        onChangeQuestions(
                                          reorderQuestionIds(selectedQuestionIds, index, index + 1),
                                        )
                                      }
                                    >
                                      Down
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() =>
                                        onChangeQuestions(
                                          selectedQuestionIds.filter((item) => item !== question.id),
                                        )
                                      }
                                    >
                                      Remove
                                    </button>
                                  </div>
                                ) : null}
                              </article>
                            );
                          })}
                          {blueprintMismatches.length ? (
                            <p className="helper-warning">
                              {blueprintMismatches.length} selected question
                              {blueprintMismatches.length > 1 ? "s do" : " does"} not match the
                              difficulty blueprint.
                            </p>
                          ) : null}
                          <div className={`question-template-readiness ${questionSetReady ? "is-complete" : "is-needed"}`}>
                            <strong>{questionSetReady ? "Question set ready" : "Complete the template requirements"}</strong>
                            <span>
                              {questionSetReady
                                ? "Every candidate receives the template-defined questions for exactly 100 marks."
                                : "Assessment creation stays locked until every required difficulty is selected."}
                            </span>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {activeSection === "rules" ? (
              <div className="assessment-form-stack assessment-form-pro assessment-create-form">
                <div className="question-status-strip" aria-label="Assessment rules readiness">
                  <span className={scoringIsValid ? "is-ready" : "is-needed"}>
                    Scoring {scoringTotal} / 100
                  </span>
                  <span
                    className={
                      assessmentForm.supported_languages.length > 0 ? "is-ready" : "is-needed"
                    }
                  >
                    Languages {assessmentForm.supported_languages.length}
                  </span>
                  <span className={rulesReady ? "is-ready" : "is-needed"}>
                    Policy {enabledPolicyCount} active
                  </span>
                </div>

                <div className="assessment-form-section assessment-section-pro assessment-builder-page-card">
                  <div className="assessment-section-heading">
                    <span className="assessment-section-icon is-warm">
                      <SlidersHorizontal size={18} />
                    </span>
                    <div>
                      <span className="panel-eyebrow">Rules</span>
                      <h3>Scoring and candidate policy</h3>
                    </div>
                  </div>

                  <div className="assessment-form-section assessment-section-pro">
                    <div className="assessment-section-heading">
                      <span className="assessment-section-icon is-green">
                        <Gauge size={18} />
                      </span>
                      <div>
                        <span className="panel-eyebrow">Scoring Configuration</span>
                        <h3>Evaluation weightage</h3>
                      </div>
                    </div>
                    <div className="scoring-preset-row" aria-label="Scoring presets">
                      {[
                        {
                          label: "Balanced",
                          detail: "40 / 30 / 30",
                          values: [40, 30, 30] as const,
                        },
                        {
                          label: "Test-Heavy",
                          detail: "80 / 10 / 10",
                          values: [80, 10, 10] as const,
                        },
                        {
                          label: "Quality-Heavy",
                          detail: "20 / 40 / 40",
                          values: [20, 40, 40] as const,
                        },
                      ].map((preset) => (
                        <button
                          key={preset.label}
                          type="button"
                          onClick={() =>
                            applyScoringPreset(
                              preset.values[0],
                              preset.values[1],
                              preset.values[2],
                            )
                          }
                        >
                          <strong>{preset.label}</strong>
                          <span>{preset.detail}</span>
                        </button>
                      ))}
                    </div>
                    <div className="assessment-inline-fields assessment-three-fields">
                      <label className="field field-pro">
                        <span>
                          Test case weight {requiredMark}
                        </span>
                        <input
                          type="number"
                          min={0}
                          max={100}
                          value={assessmentForm.test_case_score_weight}
                          onChange={(event) =>
                            onChange({
                              ...assessmentForm,
                              test_case_score_weight: Number(event.target.value),
                            })
                          }
                        />
                      </label>
                      <label className="field field-pro">
                        <span>
                          Coding metrics {requiredMark}
                        </span>
                        <input
                          type="number"
                          min={0}
                          max={100}
                          value={assessmentForm.coding_score_weight}
                          onChange={(event) =>
                            onChange({
                              ...assessmentForm,
                              coding_score_weight: Number(event.target.value),
                            })
                          }
                        />
                      </label>
                      <label className="field field-pro">
                        <span>
                          AI quality {requiredMark}
                        </span>
                        <input
                          type="number"
                          min={0}
                          max={100}
                          value={assessmentForm.ai_score_weight}
                          onChange={(event) =>
                            onChange({
                              ...assessmentForm,
                              ai_score_weight: Number(event.target.value),
                            })
                          }
                        />
                      </label>
                    </div>
                    <div className="assessment-score-meter">
                      <div className="score-meter-track">
                        <span
                          className="score-segment is-tests"
                          style={{ width: `${assessmentForm.test_case_score_weight}%` }}
                        />
                        <span
                          className="score-segment is-code"
                          style={{ width: `${assessmentForm.coding_score_weight}%` }}
                        />
                        <span
                          className="score-segment is-ai"
                          style={{ width: `${assessmentForm.ai_score_weight}%` }}
                        />
                      </div>
                      <p className={scoringIsValid ? "helper-success" : "helper-warning"}>
                        Current total: {scoringTotal}. Target total: 100.
                      </p>
                    </div>
                  </div>

                  <div className="assessment-form-section assessment-section-pro">
                    <div className="assessment-section-heading">
                      <span className="assessment-section-icon is-blue">
                        <ShieldCheck size={18} />
                      </span>
                      <div>
                        <span className="panel-eyebrow">Access & Test Policy</span>
                        <h3>Candidate experience</h3>
                      </div>
                    </div>
                    <div className="proctoring-option-grid">
                      {[
                        {
                          value: "basic",
                          title: "Basic monitoring",
                          features: [
                            "Tab switch warning alerts",
                            "Window blur detection",
                            "Copy/paste monitoring",
                          ],
                        },
                        {
                          value: "strict",
                          title: "Strict monitoring",
                          features: [
                            "Full-screen lockout enforcement",
                            "Close the test if the candidate exits",
                            "Copy/paste restrictions",
                          ],
                        },
                        {
                          value: "none",
                          title: "No proctoring",
                          features: [
                            "Relaxed candidate experience",
                            "Standard submission logging",
                            "No alert policies",
                          ],
                        },
                      ].map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          className={
                            assessmentForm.proctoring_mode === option.value
                              ? "is-selected"
                              : ""
                          }
                          onClick={() =>
                            onChange({
                              ...assessmentForm,
                              proctoring_mode: option.value,
                            })
                          }
                        >
                          <strong>{option.title}</strong>
                          <ul>
                            {option.features.map((feature) => (
                              <li key={feature}>{feature}</li>
                            ))}
                          </ul>
                        </button>
                      ))}
                    </div>

                    <div className="assessment-inline-fields">
                      <label className="field field-pro">
                        <span>
                          Supported languages {requiredMark}
                        </span>
                        <div className="assessment-language-grid">
                          {ASSESSMENT_LANGUAGES.map((language) => {
                            const selected =
                              assessmentForm.supported_languages.includes(language);
                            return (
                              <label
                                key={language}
                                className={`language-option ${selected ? "is-selected" : ""}`}
                              >
                                <input
                                  type="checkbox"
                                  className="language-option-input"
                                  checked={selected}
                                  onChange={(event) =>
                                    toggleLanguage(language, event.target.checked)
                                  }
                                />
                                <span className="language-option-icon">
                                  <Code2 size={15} />
                                </span>
                                <span className="language-option-name">
                                  {LANGUAGE_LABELS[language]}
                                </span>
                                <span className="language-option-check" aria-hidden="true">
                                  <Check size={13} />
                                </span>
                              </label>
                            );
                          })}
                        </div>
                      </label>
                    </div>

                    <div className="assessment-policy-grid">
                      <label className="policy-toggle">
                        <input
                          type="checkbox"
                          checked={assessmentForm.allow_resume}
                          onChange={(event) =>
                            onChange({
                              ...assessmentForm,
                              allow_resume: event.target.checked,
                            })
                          }
                        />
                        <span>
                          <strong>Allow resume</strong>
                        </span>
                      </label>
                      <label className="policy-toggle">
                        <input
                          type="checkbox"
                          checked={assessmentForm.show_score_to_candidate}
                          onChange={(event) =>
                            onChange({
                              ...assessmentForm,
                              show_score_to_candidate: event.target.checked,
                            })
                          }
                        />
                        <span>
                          <strong>Show final score</strong>
                        </span>
                      </label>
                    </div>

                  </div>
                </div>
              </div>
            ) : null}

            <div className="assessment-builder-footer">
              <div className="assessment-builder-footer-copy">
                {createError ? <p className="form-error">{createError}</p> : null}
              </div>
              <div className="assessment-actions-row">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={goToPreviousSection}
                  disabled={activeSectionIndex === 0}
                >
                  Back
                </Button>
                {activeSection !== "rules" ? (
                  <Button
                    type="button"
                    onClick={goToNextSection}
                    disabled={!sectionReady(activeSection)}
                  >
                    Save & Continue
                  </Button>
                ) : (
                  <Button type="button" onClick={onCreate} disabled={!canCreateAssessment}>
                    <BadgeCheck size={17} />
                    {createPending ? "Creating..." : "Create Assessment"}
                  </Button>
                )}
                <Button type="button" variant="secondary" onClick={onBack}>
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </section>
  );
}

function AssessmentDetailView({
  assessment,
  slots,
  slotsLoading,
  questionBank,
  selectedQuestions,
  canArchive,
  questionPending,
  questionError,
  publishError,
  publishPending,
  deletePending,
  deleteError,
  assessmentUpdatePending,
  slotForm,
  slotPending,
  slotError,
  successMessage,
  evaluationBackfillPending,
  evaluationBackfillError,
  evaluationBackfillResult,
  onBack,
  onOpenTest,
  onArchive,
  onDeleteAssessment,
  onUpdateAssessment,
  onSaveQuestions,
  onToggleQuestion,
  onUpdateQuestionSelection,
  onChangeSlot,
  onCreateSlot,
  onBackfillEvaluations,
}: {
  assessment: Assessment;
  slots: AssessmentSlot[];
  slotsLoading: boolean;
  questionBank: Array<{
    id: string;
    title: string;
    difficulty: string;
    tags: string[];
  }>;
  selectedQuestions: Record<string, AssessmentQuestionAssignment>;
  canArchive: boolean;
  questionPending: boolean;
  questionError: string;
  publishError: string;
  publishPending: boolean;
  deletePending: boolean;
  deleteError: string;
  assessmentUpdatePending: boolean;
  slotForm: {
    title: string;
    start_at: string;
    end_at: string;
    duration_minutes: number;
    timezone_name: string;
    timezone_offset_minutes: number;
    instructions_override: string;
    status: "scheduled";
  };
  slotPending: boolean;
  slotError: string;
  successMessage: string;
  evaluationBackfillPending: boolean;
  evaluationBackfillError: string;
  evaluationBackfillResult: EvaluationBackfillResponse | null;
  onBack: () => void;
  onOpenTest: (slotId: string) => void;
  onArchive: () => void;
  onDeleteAssessment: () => Promise<void>;
  onUpdateAssessment: (payload: Partial<AssessmentCreatePayload>) => Promise<void>;
  onSaveQuestions: () => Promise<void>;
  onToggleQuestion: (questionId: string, checked: boolean) => void;
  onUpdateQuestionSelection: (
    updater: (
      current: Record<string, AssessmentQuestionAssignment>,
    ) => Record<string, AssessmentQuestionAssignment>,
  ) => void;
  onChangeSlot: (payload: {
    title: string;
    start_at: string;
    end_at: string;
    duration_minutes: number;
    timezone_name: string;
    timezone_offset_minutes: number;
    instructions_override: string;
    status: "scheduled";
  }) => void;
  onCreateSlot: () => Promise<void>;
  onBackfillEvaluations: () => Promise<unknown> | void;
}) {
  const totalCandidates = slots.reduce((sum, slot) => sum + slot.candidate_count, 0);
  const totalSubmitted = slots.reduce((sum, slot) => sum + slot.submitted_count, 0);
  const [showCreateTest, setShowCreateTest] = useState(false);
  const [detailMode, setDetailMode] = useState<AssessmentDetailMode>("tests");
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [settingsTab, setSettingsTab] = useState<"details" | "rules" | "danger">("details");
  const minimumSlotStart = nextAvailableTimeInput(
    slotForm.timezone_name,
    slotForm.timezone_offset_minutes,
  );
  const minimumSlotEnd = addMinutesToLocalInput(
    slotForm.start_at,
    slotForm.duration_minutes,
  );
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [detailSuccessMessage, setDetailSuccessMessage] = useState("");
  const [assessmentEditForm, setAssessmentEditForm] = useState<AssessmentCreatePayload>(
    () => assessmentToPayload(assessment),
  );

  useEffect(() => {
    setAssessmentEditForm(assessmentToPayload(assessment));
  }, [assessment]);

  useEffect(() => {
    setDetailMode("tests");
    setShowCreateTest(false);
    setShowSettingsModal(false);
    setSettingsTab("details");
    setDeleteConfirmText("");
    setDetailSuccessMessage("");
  }, [assessment.id]);

  useEffect(() => {
    setDetailSuccessMessage(successMessage);
  }, [successMessage]);
  const editScoringTotal =
    assessmentEditForm.test_case_score_weight +
    assessmentEditForm.coding_score_weight +
    assessmentEditForm.ai_score_weight;

  async function saveAssessmentDetails() {
    setDetailSuccessMessage("");
    await onUpdateAssessment(assessmentEditForm);
    setShowSettingsModal(false);
    setDetailSuccessMessage("Assessment details saved successfully.");
  }

  async function deleteAssessmentFromSettings() {
    if (deleteConfirmText !== "delete") {
      return;
    }
    setDetailSuccessMessage("");
    await onDeleteAssessment();
  }

  async function createTestSlot() {
    setDetailSuccessMessage("");
    try {
      await onCreateSlot();
      setShowCreateTest(false);
      setDetailSuccessMessage("Test created successfully.");
    } catch {
      setDetailSuccessMessage("");
    }
  }

  async function saveQuestionSet() {
    setDetailSuccessMessage("");
    await onSaveQuestions();
    setDetailSuccessMessage("Question set saved successfully.");
  }

  async function updateQuestionSetDelivery(payload: Partial<AssessmentCreatePayload>) {
    setDetailSuccessMessage("");
    await onUpdateAssessment(payload);
    setDetailSuccessMessage("Question delivery settings saved successfully.");
  }

  return (
    <section className="assessment-drilldown">
      <div className="assessment-breadcrumb">
        <button type="button" onClick={onBack}>
          Back to assessments
        </button>
        <span>/</span>
        <strong>{assessment.title}</strong>
      </div>

      <Card className="assessment-panel assessment-command-center">
        <div className="assessment-command-main">
          <div>
            <span className="panel-eyebrow">Assessment Template</span>
            <h2>{assessment.title}</h2>
            <p>{assessment.description || "No description added yet."}</p>
          </div>
          <div className="assessment-row-actions">
            <StatusBadge value={assessment.status} />
            <Button
              type="button"
              variant="secondary"
              className="icon-only-button"
              onClick={() => {
                setSettingsTab("details");
                setShowSettingsModal(true);
              }}
              title="Assessment settings"
            >
              <Settings size={18} />
              <span className="sr-only">Assessment settings</span>
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="icon-only-button"
              onClick={onArchive}
              disabled={publishPending || !canArchive}
              title="Archive assessment"
            >
              <Archive size={18} />
              <span className="sr-only">Archive assessment</span>
            </Button>
          </div>
        </div>

        <div className="assessment-hero-metrics assessment-command-metrics">
          <span>
            <strong>{slots.length}</strong>
            Tests
          </span>
          <span>
            <strong>{totalCandidates}</strong>
            Candidates
          </span>
          <span>
            <strong>{totalSubmitted}</strong>
            Submitted
          </span>
          <span>
            <strong>
              {assessment.question_count_per_candidate || assessment.question_count}
            </strong>
            Per candidate
          </span>
        </div>

        <div className="assessment-detail-list">
          <div>
            <span>Duration</span>
            <strong>Configured per test</strong>
          </div>
          <div>
            <span>Passing score</span>
            <strong>{assessment.passing_score}%</strong>
          </div>
          <div>
            <span>Scoring</span>
            <strong>
              {assessment.test_case_score_weight}/{assessment.coding_score_weight}/{assessment.ai_score_weight}
            </strong>
            <em>Test cases / coding / AI</em>
          </div>
          <div>
            <span>Candidate policy</span>
            <strong>
              {assessment.allow_resume ? "Resume allowed" : "No resume"} ·{" "}
              {assessment.shuffle_questions ? "Randomized set" : "Same set"}
            </strong>
          </div>
          <div>
            <span>Hidden feedback</span>
            <strong>{assessment.hidden_feedback_mode}</strong>
            <em>
              Unlimited checks, 5s cooldown
            </em>
          </div>
          <div>
            <span>Languages</span>
            <strong>{assessment.supported_languages.join(", ")}</strong>
          </div>
        </div>
      </Card>

      <div className="assessment-detail-tabs" role="tablist" aria-label="Assessment sections">
        <button
          type="button"
          role="tab"
          aria-selected={detailMode === "tests"}
          className={detailMode === "tests" ? "is-active" : ""}
          onClick={() => setDetailMode("tests")}
        >
          <ListChecks size={18} aria-hidden="true" />
          <span>
            <strong>Tests</strong>
            <small>{slots.length} scheduled batches</small>
          </span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={detailMode === "questions"}
          className={detailMode === "questions" ? "is-active" : ""}
          onClick={() => setDetailMode("questions")}
        >
          <Code2 size={18} aria-hidden="true" />
          <span>
            <strong>Questions</strong>
            <small>{assessment.question_count} configured</small>
          </span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={detailMode === "evaluation"}
          className={detailMode === "evaluation" ? "is-active" : ""}
          onClick={() => setDetailMode("evaluation")}
        >
          <BarChart3 size={18} aria-hidden="true" />
          <span>
            <strong>Evaluations</strong>
            <small>Analytics and reports</small>
          </span>
        </button>
      </div>

      {detailSuccessMessage ? (
        <p className="helper-success assessment-success-banner">
          {detailSuccessMessage}
        </p>
      ) : null}

      {showSettingsModal ? (
        <div className="dialog-backdrop" onClick={() => setShowSettingsModal(false)}>
          <Card
            className="assessment-settings-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="assessment-settings-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="panel-heading">
              <div>
                <span>Settings</span>
                <h2 id="assessment-settings-title">Assessment settings</h2>
              </div>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setShowSettingsModal(false)}
              >
                Close
              </Button>
            </div>

            <div className="settings-tabbar" role="tablist" aria-label="Assessment settings tabs">
              {[
                { id: "details", label: "Details" },
                { id: "rules", label: "Rules" },
                { id: "danger", label: "Danger" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  className={settingsTab === tab.id ? "is-active" : ""}
                  onClick={() => setSettingsTab(tab.id as typeof settingsTab)}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {settingsTab === "details" ? (
              <div className="assessment-form-stack">
                <label className="field">
                  <span>Assessment title</span>
                  <input
                    value={assessmentEditForm.title}
                    onChange={(event) =>
                      setAssessmentEditForm({
                        ...assessmentEditForm,
                        title: event.target.value,
                      })
                    }
                  />
                </label>
                <label className="field">
                  <span>Description</span>
                  <textarea
                    value={assessmentEditForm.description}
                    onChange={(event) =>
                      setAssessmentEditForm({
                        ...assessmentEditForm,
                        description: event.target.value,
                      })
                    }
                  />
                </label>
                <label className="field">
                  <span>Candidate instructions</span>
                  <textarea
                    value={assessmentEditForm.instructions}
                    onChange={(event) =>
                      setAssessmentEditForm({
                        ...assessmentEditForm,
                        instructions: event.target.value,
                      })
                    }
                  />
                </label>
                <div className="assessment-inline-fields">
                  <label className="field">
                    <span>Passing score</span>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={assessmentEditForm.passing_score}
                      onChange={(event) =>
                        setAssessmentEditForm({
                          ...assessmentEditForm,
                          passing_score: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Questions per candidate</span>
                    <input
                      type="number"
                      min={1}
                      max={200}
                      value={assessmentEditForm.question_count_per_candidate || assessment.question_count || 1}
                      onChange={(event) =>
                        setAssessmentEditForm({
                          ...assessmentEditForm,
                          question_count_per_candidate: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                </div>
              </div>
            ) : null}

            {settingsTab === "rules" ? (
              <div className="assessment-form-stack">
                <div className="assessment-inline-fields assessment-three-fields">
                  <label className="field">
                    <span>Test case weight</span>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={assessmentEditForm.test_case_score_weight}
                      onChange={(event) =>
                        setAssessmentEditForm({
                          ...assessmentEditForm,
                          test_case_score_weight: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Coding weight</span>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={assessmentEditForm.coding_score_weight}
                      onChange={(event) =>
                        setAssessmentEditForm({
                          ...assessmentEditForm,
                          coding_score_weight: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>AI weight</span>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={assessmentEditForm.ai_score_weight}
                      onChange={(event) =>
                        setAssessmentEditForm({
                          ...assessmentEditForm,
                          ai_score_weight: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                </div>
                <p className={editScoringTotal === 100 ? "helper-success" : "helper-warning"}>
                  Score total: {editScoringTotal} / 100
                </p>
                <div className="assessment-inline-fields">
                  <label className="field">
                    <span>Proctoring</span>
                    <select
                      value={assessmentEditForm.proctoring_mode}
                      onChange={(event) =>
                        setAssessmentEditForm({
                          ...assessmentEditForm,
                          proctoring_mode: event.target.value,
                        })
                      }
                    >
                      <option value="basic">Basic monitoring</option>
                      <option value="strict">Strict monitoring</option>
                      <option value="none">No proctoring</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>Supported languages</span>
                    <div className="assessment-checkbox-grid">
                      {ASSESSMENT_LANGUAGES.map((language) => (
                        <label key={language}>
                          <input
                            type="checkbox"
                            checked={assessmentEditForm.supported_languages.includes(language)}
                            onChange={(event) => {
                              const nextLanguages = event.target.checked
                                ? [...assessmentEditForm.supported_languages, language]
                                : assessmentEditForm.supported_languages.filter(
                                  (item) => item !== language,
                                );
                              setAssessmentEditForm({
                                ...assessmentEditForm,
                                supported_languages: Array.from(new Set(nextLanguages)),
                              });
                            }}
                          />
                          {language}
                        </label>
                      ))}
                    </div>
                  </label>
                </div>
                <div className="assessment-toggle-row">
                  <label>
                    <input
                      type="checkbox"
                      checked={assessmentEditForm.allow_resume}
                      onChange={(event) =>
                        setAssessmentEditForm({
                          ...assessmentEditForm,
                          allow_resume: event.target.checked,
                        })
                      }
                    />
                    Allow resume
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={assessmentEditForm.shuffle_questions}
                      onChange={(event) =>
                        setAssessmentEditForm({
                          ...assessmentEditForm,
                          shuffle_questions: event.target.checked,
                        })
                      }
                    />
                    Randomize question set
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={assessmentEditForm.show_score_to_candidate}
                      onChange={(event) =>
                        setAssessmentEditForm({
                          ...assessmentEditForm,
                          show_score_to_candidate: event.target.checked,
                        })
                      }
                    />
                    Show score after evaluation
                  </label>
                </div>
              </div>
            ) : null}

            {settingsTab === "danger" ? (
              <div className="danger-settings-panel">
                <div>
                  <Trash2 size={18} aria-hidden="true" />
                  <strong>Delete this assessment</strong>
                </div>
                <p>Type <b>delete</b> to permanently delete this assessment and its test slots.</p>
                <label className="field">
                  <span>Confirmation</span>
                  <input
                    value={deleteConfirmText}
                    onChange={(event) => setDeleteConfirmText(event.target.value)}
                    placeholder="delete"
                  />
                </label>
                <Button
                  type="button"
                  className="danger-button-solid"
                  disabled={deletePending || deleteConfirmText !== "delete"}
                  onClick={() => void deleteAssessmentFromSettings()}
                >
                  {deletePending ? "Deleting..." : "Delete Assessment"}
                </Button>
                {deleteError ? <p className="form-error">{deleteError}</p> : null}
              </div>
            ) : null}

            {settingsTab !== "danger" ? (
              <div className="settings-modal-actions">
                <Button
                  type="button"
                  disabled={
                    assessmentUpdatePending ||
                    !assessmentEditForm.title.trim() ||
                    editScoringTotal !== 100 ||
                    assessmentEditForm.supported_languages.length === 0
                  }
                  onClick={() => void saveAssessmentDetails()}
                >
                  {assessmentUpdatePending ? "Saving..." : "Save Settings"}
                </Button>
              </div>
            ) : null}
            {publishError ? <p className="form-error">{publishError}</p> : null}
          </Card>
        </div>
      ) : null}

      <div className="assessment-workspace-layout">
      <section className={`assessment-console assessment-console-${detailMode}`}>
        {detailMode === "tests" ? (
          <>
            <Card className="assessment-panel assessment-panel-wide">
              <div className="assessment-table-toolbar">
                <div>
                  <span className="panel-eyebrow">Tests</span>
                  <h2>Tests in this assessment</h2>
                  <p>Each test can have a different schedule and candidate batch.</p>
                </div>
                <Button
                  type="button"
                  onClick={() => setShowCreateTest(true)}
                >
                  Create New Test
                </Button>
              </div>

              {slotsLoading ? <EmptyState label="Loading tests..." /> : null}
              {!slotsLoading && slots.length ? (
                <div className="test-card-grid">
                  {slots.map((slot) => {
                    const submittedPercent = Math.round(
                      (slot.submitted_count / Math.max(slot.candidate_count, 1)) * 100,
                    );
                    return (
                      <button
                        key={slot.id}
                        type="button"
                        className="test-summary-card"
                        onClick={() => onOpenTest(slot.id)}
                      >
                        <div className="test-card-topline">
                          <span className="test-card-icon">
                            <Clock3 size={18} aria-hidden="true" />
                          </span>
                          <StatusBadge value={slot.effective_status} />
                        </div>
                        <div className="test-card-title-row">
                          <div>
                            <strong>{slot.title}</strong>
                            <span>
                              {formatDateTime(slot.start_at)} to {formatDateTime(slot.end_at)}
                            </span>
                          </div>
                          <HealthDot status={slot.effective_status} />
                        </div>
                        <div className="test-card-metrics">
                          <span>
                            <strong>{slot.candidate_count}</strong>
                            Candidates
                          </span>
                          <span>
                            <strong>{slot.submitted_count}</strong>
                            Submitted
                          </span>
                          <span>
                            <strong>{submittedPercent}%</strong>
                            Completion
                          </span>
                        </div>
                        <div className="test-card-progress" aria-hidden="true">
                          <i style={{ width: `${submittedPercent}%` }} />
                        </div>
                        <div className="test-card-footer">
                          <span>
                            <BadgeCheck size={15} aria-hidden="true" />
                            {slot.status === slot.effective_status
                              ? "Schedule status is current"
                              : `Configured as ${slot.status}`}
                          </span>
                          <strong>Open Test</strong>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : null}
              {!slotsLoading && !slots.length ? (
                <EmptyState label="No tests scheduled yet. Create a test for the first candidate batch." />
              ) : null}
            </Card>

            {showCreateTest ? (
              <div
                className="modal-backdrop test-create-backdrop"
                role="presentation"
                onClick={() => setShowCreateTest(false)}
              >
                <Card
                  className="assessment-panel action-drawer-card test-create-dialog"
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="create-test-title"
                  onClick={(event) => event.stopPropagation()}
                >
                  <div className="panel-heading">
                    <div>
                      <span>New Test</span>
                      <h2 id="create-test-title">Schedule Candidate Batch</h2>
                      <p>Create a slot for this assessment's saved question set.</p>
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setShowCreateTest(false)}
                    >
                      Close
                    </Button>
                  </div>
                  <div className="assessment-form-stack">
                    <label className="field">
                      <span>Test title</span>
                      <input
                        placeholder="Morning batch · CSE"
                        value={slotForm.title}
                        onChange={(event) =>
                          onChangeSlot({ ...slotForm, title: event.target.value })
                        }
                      />
                    </label>
                    <div className="assessment-inline-fields">
                      <label className="field">
                        <span>Time region</span>
                        <select
                          value={slotForm.timezone_name}
                          onChange={(event) => {
                            const timezone = TIME_ZONE_OPTIONS.find(
                              (option) => option.name === event.target.value,
                            );
                            if (!timezone) {
                              return;
                            }
                            onChangeSlot({
                              ...slotForm,
                              timezone_name: timezone.name,
                              timezone_offset_minutes:
                                timezoneOffsetMinutesForLocalDateTime(
                                  slotForm.start_at || slotForm.end_at,
                                  timezone.name,
                                  timezone.fallbackOffset,
                                ),
                            });
                          }}
                        >
                          {TIME_ZONE_OPTIONS.map((timezone) => (
                            <option
                              key={timezone.name}
                              value={timezone.name}
                            >
                              {timezone.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        <span>Start time</span>
                        <input
                          type="datetime-local"
                          min={minimumSlotStart}
                          value={slotForm.start_at}
                          onChange={(event) => {
                            const startAt = event.target.value;
                            onChangeSlot({
                              ...slotForm,
                              start_at: startAt,
                              end_at: addMinutesToLocalInput(startAt, slotForm.duration_minutes),
                            });
                          }}
                        />
                      </label>
                    </div>
                    <p className="assessment-context-banner">
                      Times are interpreted in {slotForm.timezone_name}. For India, choose
                      GMT+05:30 and enter the local IST start/end time.
                    </p>
                    <div className="assessment-inline-fields">
                      <label className="field">
                        <span>Test duration (minutes)</span>
                        <input
                          type="number"
                          min={15}
                          max={360}
                          value={slotForm.duration_minutes}
                          onChange={(event) => {
                            const duration = Math.max(15, Number(event.target.value) || 15);
                            onChangeSlot({
                              ...slotForm,
                              duration_minutes: duration,
                              end_at: addMinutesToLocalInput(slotForm.start_at, duration),
                            });
                          }}
                        />
                      </label>
                      <label className="field">
                        <span>End time</span>
                        <input
                          type="datetime-local"
                          min={minimumSlotEnd}
                          value={slotForm.end_at}
                          onChange={(event) =>
                            onChangeSlot({ ...slotForm, end_at: event.target.value })
                          }
                        />
                      </label>
                    </div>
                    <label className="field">
                      <span>Batch instructions override</span>
                      <textarea
                        placeholder="Optional instructions only for this test batch"
                        value={slotForm.instructions_override}
                        onChange={(event) =>
                          onChangeSlot({
                            ...slotForm,
                            instructions_override: event.target.value,
                          })
                        }
                      />
                    </label>
                    <div className="assessment-actions-row">
                      <Button
                        type="button"
                        onClick={() => void createTestSlot()}
                        disabled={
                          slotPending ||
                          !slotForm.title ||
                          !slotForm.start_at ||
                          !slotForm.end_at
                        }
                      >
                        {slotPending ? "Creating..." : "Create New Test"}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => setShowCreateTest(false)}
                      >
                        Cancel
                      </Button>
                    </div>
                    {slotError ? <p className="form-error">{slotError}</p> : null}
                  </div>
                </Card>
              </div>
            ) : null}

          </>
        ) : detailMode === "questions" ? (
          <QuestionSetPanel
            assessment={assessment}
            questionBank={questionBank}
            selectedQuestions={selectedQuestions}
            pending={questionPending}
            assessmentUpdatePending={assessmentUpdatePending}
            error={questionError}
            publishError={publishError}
            onToggle={onToggleQuestion}
            onSave={saveQuestionSet}
            onUpdateAssessment={updateQuestionSetDelivery}
            onUpdateSelection={onUpdateQuestionSelection}
          />
        ) : (
          <AssessmentEvaluationPanel
            assessment={assessment}
            slots={slots}
            backfillPending={evaluationBackfillPending}
            backfillError={evaluationBackfillError}
            backfillResult={evaluationBackfillResult}
            onBackfill={onBackfillEvaluations}
            onOpenTest={onOpenTest}
          />
        )}
      </section>
      </div>
    </section>
  );
}

function QuestionSetPanel({
  assessment,
  questionBank,
  selectedQuestions,
  pending,
  assessmentUpdatePending,
  error,
  publishError,
  onToggle,
  onSave,
  onUpdateAssessment,
  onUpdateSelection,
}: {
  assessment: Assessment;
  questionBank: Array<{
    id: string;
    title: string;
    difficulty: string;
    tags: string[];
  }>;
  selectedQuestions: Record<string, AssessmentQuestionAssignment>;
  pending: boolean;
  assessmentUpdatePending: boolean;
  error: string;
  publishError: string;
  onToggle: (questionId: string, checked: boolean) => void;
  onSave: () => Promise<void>;
  onUpdateAssessment: (payload: Partial<AssessmentCreatePayload>) => Promise<void>;
  onUpdateSelection: (
    updater: (
      current: Record<string, AssessmentQuestionAssignment>,
    ) => Record<string, AssessmentQuestionAssignment>,
  ) => void;
}) {
  const navigate = useNavigate();
  const [showQuestionBankPicker, setShowQuestionBankPicker] = useState(false);
  const [showTemplateDialog, setShowTemplateDialog] = useState(false);
  const [panelWarning, setPanelWarning] = useState("");
  const [hasTemplateDraft, setHasTemplateDraft] = useState(false);
  const [templateDraft, setTemplateDraft] = useState<DifficultyLevel[]>(
    assessment.difficulty_blueprint?.length
      ? assessment.difficulty_blueprint
      : createQuestionBlueprint(assessment.question_count_per_candidate || 1),
  );

  async function saveQuestionsAndClose() {
    if (!selectionReady) {
      setPanelWarning(
        "Complete every difficulty requirement in the question template before saving.",
      );
      return;
    }
    if (hasTemplateDraft) {
      await onUpdateAssessment({
        difficulty_blueprint: templateDraft,
        question_count_per_candidate: templateDraft.length,
      });
    }
    await onSave();
    setHasTemplateDraft(false);
    setShowQuestionBankPicker(false);
    setShowTemplateDialog(false);
  }

  async function toggleRandomizedSet() {
    if (assessment.shuffle_questions) {
      const requiredCount = assessment.question_count_per_candidate;
      const blueprint = assessment.difficulty_blueprint || [];
      const currentDifficulties = selectedRows.map((row) => row.difficulty);
      if (
        selectedRows.length !== requiredCount ||
        blueprint.some((difficulty, index) => currentDifficulties[index] !== difficulty)
      ) {
        setPanelWarning(
          `Same-set mode requires exactly ${requiredCount} questions in the current template order.`,
        );
        return;
      }
    }
    await onUpdateAssessment({ shuffle_questions: !assessment.shuffle_questions });
  }

  const selectedRows = Object.values(selectedQuestions)
    .sort((left, right) => left.question_order - right.question_order)
    .map((selection) => {
      const assessmentQuestion = assessment.questions.find(
        (question) => question.question_id === selection.question_id,
      );
      const bankQuestion = questionBank.find(
        (question) => question.id === selection.question_id,
      );
      return {
        selection,
        title: assessmentQuestion?.title || bankQuestion?.title || "Question unavailable",
        difficulty: assessmentQuestion?.difficulty || bankQuestion?.difficulty || "unknown",
        tags: assessmentQuestion?.tags || bankQuestion?.tags || [],
        supportedLanguages: assessmentQuestion?.supported_languages || [],
      };
    });
  const activeBlueprint = hasTemplateDraft
    ? templateDraft
    : assessment.difficulty_blueprint?.length
      ? assessment.difficulty_blueprint
      : templateDraft;
  const templateMarks = calculateQuestionTemplateMarks(activeBlueprint);
  const requiredCounts = activeBlueprint.reduce<Record<DifficultyLevel, number>>(
    (counts, difficulty) => ({ ...counts, [difficulty]: counts[difficulty] + 1 }),
    { easy: 0, medium: 0, hard: 0 },
  );
  const selectedCounts = selectedRows.reduce<Record<DifficultyLevel, number>>(
    (counts, row) => {
      if (!QUESTION_DIFFICULTIES.includes(row.difficulty as DifficultyLevel)) return counts;
      const difficulty = row.difficulty as DifficultyLevel;
      return { ...counts, [difficulty]: counts[difficulty] + 1 };
    },
    { easy: 0, medium: 0, hard: 0 },
  );
  const minimumRequirementsMet = QUESTION_DIFFICULTIES.every(
    (difficulty) => selectedCounts[difficulty] >= requiredCounts[difficulty],
  );
  const allSelectedInTemplate = selectedRows.every((row) =>
    activeBlueprint.includes(row.difficulty as DifficultyLevel),
  );
  const orderedSelectionMatches = selectedRows.length === activeBlueprint.length &&
    selectedRows.every((row, index) => row.difficulty === activeBlueprint[index]);
  const selectionReady = assessment.shuffle_questions
    ? selectedRows.length >= activeBlueprint.length && minimumRequirementsMet && allSelectedInTemplate
    : orderedSelectionMatches;
  const nextRequiredDifficulty = assessment.shuffle_questions
    ? null
    : activeBlueprint[selectedRows.length];
  const availableBankQuestions = questionBank.filter(
    (question) => !selectedQuestions[question.id] && activeBlueprint.includes(question.difficulty as DifficultyLevel),
  );
  const difficultySummary = selectedRows.reduce<Record<string, number>>(
    (summary, row) => ({
      ...summary,
      [row.difficulty]: (summary[row.difficulty] || 0) + 1,
    }),
    {},
  );
  const templateLabel = activeBlueprint
    .map((difficulty, index) => `Q${index + 1} ${difficulty} (${templateMarks[index]} marks)`)
    .join(" · ");

  function marksForDifficulty(difficulty: string) {
    const values = templateMarks.filter((_, index) => activeBlueprint[index] === difficulty);
    if (!values.length) return "Not in template";
    const unique = Array.from(new Set(values));
    return unique.length === 1 ? `${unique[0]} marks` : `${Math.min(...unique)}-${Math.max(...unique)} marks`;
  }

  function openQuestionEditor(questionId: string) {
    navigate(
      `/recruiter/question-management/new?questionId=${encodeURIComponent(questionId)}`,
    );
  }

  function addEligibleQuestion(questionId: string) {
    onUpdateSelection((current) => ({
      ...current,
      [questionId]: {
        question_id: questionId,
        question_order: Object.keys(current).length + 1,
        marks: 1,
        is_mandatory: true,
      },
    }));
  }

  return (
    <Card className="assessment-panel question-management-panel">
      {panelWarning ? (
        <div className="question-flow-toast-stack" aria-live="assertive">
          <div className="question-flow-toast is-warning" role="alert">
            <div><strong>Question set warning</strong><p>{panelWarning}</p></div>
            <button type="button" className="question-flow-toast-dismiss" onClick={() => setPanelWarning("")}>Close</button>
          </div>
        </div>
      ) : null}
      <div className="panel-heading">
        <div>
          <span>Question Set</span>
          <h2>Assessment questions</h2>
        </div>
        <div className="assessment-row-actions">
          <Button
            type="button"
            variant="secondary"
            onClick={() => setShowTemplateDialog(true)}
          >
            Question Template
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setShowQuestionBankPicker((current) => !current)}
          >
            {showQuestionBankPicker ? "Hide Question Bank" : "Add More From Question Bank"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={assessmentUpdatePending}
            onClick={() => void toggleRandomizedSet()}
          >
            {assessment.shuffle_questions ? "Use Same Set" : "Randomize Set"}
          </Button>
        </div>
      </div>

      <div className="question-policy-grid">
        <div>
          <span>Delivery rule</span>
          <strong>{templateLabel}</strong>
        </div>
        <div>
          <span>Candidate set</span>
          <strong>{assessment.shuffle_questions ? "Randomized per candidate" : "Same for everyone"}</strong>
        </div>
        <div>
          <span>Assessment total</span>
          <strong>100 marks</strong>
          <em>Fixed by the question template</em>
        </div>
        <div>
          <span>Difficulty mix</span>
          <strong>
            {Object.entries(difficultySummary)
              .map(([difficulty, count]) => `${count} ${difficulty}`)
              .join(" · ") || "Not selected"}
          </strong>
        </div>
      </div>

      <div className="template-requirements-panel">
        <div className="template-requirements-copy">
          <span className="panel-eyebrow">Selection requirements</span>
          <strong>{selectionReady ? "Template requirements complete" : "Select the minimum required questions"}</strong>
          <p>
            {assessment.shuffle_questions
              ? "You may add extra questions for randomization, but each difficulty must meet its template minimum."
              : "Add questions in template order. Only a question matching the next slot can be selected."}
          </p>
        </div>
        <div className="template-quota-grid">
          {QUESTION_DIFFICULTIES.filter((difficulty) => requiredCounts[difficulty] > 0).map((difficulty) => {
            const complete = selectedCounts[difficulty] >= requiredCounts[difficulty];
            return (
              <div key={difficulty} className={complete ? "is-complete" : "is-needed"}>
                <span className={`difficulty-chip difficulty-${difficulty}`}>{difficulty}</span>
                <strong>{selectedCounts[difficulty]} / {requiredCounts[difficulty]}</strong>
                <em>{complete ? "Ready" : `${requiredCounts[difficulty] - selectedCounts[difficulty]} more required`}</em>
              </div>
            );
          })}
        </div>
        {!allSelectedInTemplate ? (
          <p className="template-selection-error">
            Remove questions whose difficulty is no longer part of this template.
          </p>
        ) : null}
      </div>

      <div className="selected-question-list">
        {selectedRows.length ? (
          selectedRows.map((row) => (
            <div
              key={row.selection.question_id}
              className={`selected-question-card difficulty-${row.difficulty}`}
            >
              <div className="selected-question-index">
                {row.selection.question_order}
              </div>
              <div className="selected-question-main">
                <button
                  type="button"
                  className="question-title-link"
                  onClick={() => openQuestionEditor(row.selection.question_id)}
                >
                  {row.title}
                </button>
                <div className="selected-question-tags">
                  <span className={`difficulty-chip difficulty-${row.difficulty}`}>
                    {row.difficulty}
                  </span>
                  {row.tags.slice(0, 3).map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                  {row.supportedLanguages.slice(0, 3).map((language) => (
                    <span key={language}>{language}</span>
                  ))}
                </div>
              </div>
              <div className="assessment-inline-fields">
                <label className="field">
                  <span>Order</span>
                  <input
                    type="number"
                    min={1}
                    value={row.selection.question_order}
                    onChange={(event) =>
                      onUpdateSelection((current) => ({
                        ...current,
                        [row.selection.question_id]: {
                          ...current[row.selection.question_id],
                          question_order: Number(event.target.value),
                        },
                      }))
                    }
                  />
                </label>
                <label className="field">
                  <span>Template weight</span>
                  <strong className="template-weight-value">
                    {assessment.shuffle_questions
                      ? marksForDifficulty(row.difficulty)
                      : `${templateMarks[row.selection.question_order - 1] || 0} marks`}
                  </strong>
                </label>
              </div>
              <div className="selected-question-actions">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => onToggle(row.selection.question_id, false)}
                >
                  Remove
                </Button>
              </div>
            </div>
          ))
        ) : (
          <EmptyState label="No questions selected yet. Add questions from the bank to make this assessment attendable." />
        )}
      </div>

      {showQuestionBankPicker ? (
        <div className="question-bank-picker">
          <div className="assessment-table-toolbar">
            <div>
              <span className="panel-eyebrow">Question Bank</span>
              <h2>{nextRequiredDifficulty ? `Choose a ${nextRequiredDifficulty} question next` : "Add eligible questions"}</h2>
              <p>Only difficulties included in the active template are shown.</p>
            </div>
          </div>
          {availableBankQuestions.length ? (
            <div className="question-bank-card-grid">
              {availableBankQuestions.map((question) => (
                <div key={question.id} className="question-bank-card">
                  <div>
                    <strong>{question.title}</strong>
                    <span>
                      {question.difficulty}
                      {question.tags.length ? ` · ${question.tags.slice(0, 3).join(", ")}` : ""}
                    </span>
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={Boolean(nextRequiredDifficulty && question.difficulty !== nextRequiredDifficulty)}
                    onClick={() => addEligibleQuestion(question.id)}
                  >
                    {nextRequiredDifficulty && question.difficulty !== nextRequiredDifficulty
                      ? `Need ${nextRequiredDifficulty}`
                      : "Add Question"}
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState label="Every available question is already selected for this assessment." />
          )}
        </div>
      ) : null}

      <div className="assessment-actions-row">
        <Button
          type="button"
          onClick={() => void saveQuestionsAndClose()}
          disabled={pending || !selectionReady}
        >
          {pending ? "Saving..." : "Save Question Set"}
        </Button>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      {publishError ? <p className="form-error">{publishError}</p> : null}

      {showTemplateDialog ? (
        <div className="dialog-backdrop">
          <div className="question-template-modal" role="dialog" aria-modal="true">
            <div className="panel-heading">
              <div>
                <span>Question Template</span>
                <h2>Question delivery</h2>
              </div>
            </div>
            <div className="difficulty-blueprint">
              <div className="question-set-subhead">
                <strong>Current template</strong>
                <span>{templateLabel}</span>
              </div>
              <div className="difficulty-slot-grid">
                {templateDraft.map((difficulty, index) => (
                  <label key={`edit-template-${index}`}>
                    <span>Q{index + 1} · {calculateQuestionTemplateMarks(templateDraft)[index]} marks</span>
                    <select
                      value={difficulty}
                      onChange={(event) =>
                        setTemplateDraft((current) => current.map((item, itemIndex) =>
                          itemIndex === index ? event.target.value as DifficultyLevel : item,
                        ))
                      }
                    >
                      {QUESTION_DIFFICULTIES.map((item) => <option key={item} value={item}>{item}</option>)}
                    </select>
                  </label>
                ))}
              </div>
            </div>
            <div className="confirm-dialog-actions">
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setTemplateDraft(
                    assessment.difficulty_blueprint?.length
                      ? assessment.difficulty_blueprint
                      : createQuestionBlueprint(assessment.question_count_per_candidate || 1),
                  );
                  setShowTemplateDialog(false);
                }}
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={() => {
                  setHasTemplateDraft(true);
                  setShowTemplateDialog(false);
                  setShowQuestionBankPicker(true);
                }}
              >
                Apply Template & Select Questions
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

function TestDetailView({
  assessment,
  slot,
  tab,
  candidates,
  monitoringItems,
  monitoringLoading,
  submittedCount,
  inProgressCount,
  candidateCsv,
  importPending,
  invitePending,
  slotUpdatePending,
  importErrors,
  importError,
  inviteError,
  slotUpdateError,
  evaluationBackfillPending,
  evaluationBackfillError,
  evaluationBackfillResult,
  resendPendingId,
  onBack,
  onTabChange,
  onCsvChange,
  onImport,
  onSendInvites,
  onUpdateSlot,
  onControlSlot,
  onBackfillEvaluations,
  onResend,
}: {
  assessment: Assessment;
  slot: AssessmentSlot;
  tab: TestTab;
  candidates: SlotCandidate[];
  monitoringItems: MonitoringCandidate[];
  monitoringLoading: boolean;
  submittedCount: number;
  inProgressCount: number;
  candidateCsv: string;
  importPending: boolean;
  invitePending: boolean;
  slotUpdatePending: boolean;
  importErrors: Array<{ row_number: number; email: string; errors: string[] }>;
  importError: string;
  inviteError: string;
  slotUpdateError: string;
  evaluationBackfillPending: boolean;
  evaluationBackfillError: string;
  evaluationBackfillResult: EvaluationBackfillResponse | null;
  resendPendingId: string | null;
  onBack: () => void;
  onTabChange: (tab: TestTab) => void;
  onCsvChange: (value: string) => void;
  onImport: (csvText: string) => void;
  onSendInvites: (candidateAssessmentIds?: string[]) => void;
  onUpdateSlot: (payload: AssessmentSlotUpdatePayload) => Promise<unknown> | void;
  onControlSlot: (payload: AssessmentSlotActionPayload) => Promise<unknown> | void;
  onBackfillEvaluations: (
    candidateAssessmentIds: string[],
  ) => Promise<unknown> | void;
  onResend: (candidateAssessmentId: string) => void;
}) {
  const [isEditingSlot, setIsEditingSlot] = useState(false);
  const [isManagingTest, setIsManagingTest] = useState(false);
  const [pendingTestAction, setPendingTestAction] =
    useState<AssessmentSlotActionPayload | null>(null);
  const [testResponseMessage, setTestResponseMessage] = useState("");
  const [testResponseTone, setTestResponseTone] = useState<"success" | "warning">(
    "success",
  );
  const [extendMinutes, setExtendMinutes] = useState(15);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [editForm, setEditForm] = useState({
    title: slot.title,
    start_at: toTimezoneInputValue(
      slot.start_at,
      slot.timezone_name,
      slot.timezone_offset_minutes,
    ),
    end_at: toTimezoneInputValue(
      slot.end_at,
      slot.timezone_name,
      slot.timezone_offset_minutes,
    ),
    duration_minutes: slot.duration_minutes || assessment.duration_minutes || 60,
    timezone_name: slot.timezone_name,
    timezone_offset_minutes: slot.timezone_offset_minutes,
    instructions_override: slot.instructions_override,
    status: slot.status,
  });

  useEffect(() => {
    setEditForm({
      title: slot.title,
      start_at: toTimezoneInputValue(
        slot.start_at,
        slot.timezone_name,
        slot.timezone_offset_minutes,
      ),
      end_at: toTimezoneInputValue(
        slot.end_at,
        slot.timezone_name,
        slot.timezone_offset_minutes,
      ),
      duration_minutes: slot.duration_minutes || assessment.duration_minutes || 60,
      timezone_name: slot.timezone_name,
      timezone_offset_minutes: slot.timezone_offset_minutes,
      instructions_override: slot.instructions_override,
      status: slot.status,
    });
  }, [assessment.duration_minutes, slot]);

  useEffect(() => {
    const interval = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  const secondsUntilStart = Math.max(
    0,
    Math.floor((new Date(slot.start_at).getTime() - nowMs) / 1000),
  );
  const minimumEditStart = nextAvailableTimeInput(
    editForm.timezone_name,
    editForm.timezone_offset_minutes,
  );
  const minimumEditEnd = addMinutesToLocalInput(
    editForm.start_at,
    editForm.duration_minutes,
  );
  const secondsUntilClose = Math.max(
    0,
    Math.floor((new Date(slot.end_at).getTime() - nowMs) / 1000),
  );
  const effectiveStatus =
    slot.status === "paused" || slot.status === "closed" || slot.status === "draft"
      ? slot.status
      : secondsUntilStart > 0
        ? "scheduled"
        : secondsUntilClose > 0
          ? "active"
          : "closed";
  const statusLabel =
    effectiveStatus === "scheduled"
      ? `To be started in ${formatCountdown(secondsUntilStart)}`
      : effectiveStatus === "active"
        ? `Accepting responses closes in ${formatCountdown(secondsUntilClose)}`
        : effectiveStatus === "paused"
          ? "Paused. Candidate work is temporarily blocked."
          : "Closed for responses";
  const pendingActionLabel =
    pendingTestAction?.action === "continue"
      ? "continue this test"
      : pendingTestAction?.action === "extend"
        ? `extend this test by ${pendingTestAction.extend_minutes || extendMinutes} minutes`
        : pendingTestAction?.action === "close"
          ? "close this test now"
          : pendingTestAction?.action === "pause"
            ? "pause this test"
            : "";
  const proposedExtendedEndAt = new Date(
    new Date(slot.end_at).getTime() + Math.max(extendMinutes, 1) * 60_000,
  ).toISOString();
  const canPauseTest = effectiveStatus !== "paused" && effectiveStatus !== "closed";
  const canContinueTest = effectiveStatus === "paused";
  const canExtendTest = effectiveStatus !== "closed";
  const canCloseTest = effectiveStatus !== "closed";
  const pendingActionImpact =
    pendingTestAction?.action === "pause"
      ? "Candidates will see that the assessment is paused and cannot continue until you resume it."
      : pendingTestAction?.action === "continue"
        ? "Candidates will be able to continue from their saved progress."
        : pendingTestAction?.action === "extend"
          ? `The end time will move from ${formatDateTime(slot.end_at)} to ${formatDateTime(proposedExtendedEndAt)}.`
          : pendingTestAction?.action === "close"
            ? "Candidate access will close immediately. Submitted work remains available for results."
            : "";

  function requestTestAction(
    action: AssessmentSlotActionPayload,
    unavailableMessage?: string,
  ) {
    setPendingTestAction(null);
    if (unavailableMessage) {
      setTestResponseTone("warning");
      setTestResponseMessage(unavailableMessage);
      return;
    }
    setTestResponseMessage("");
    setPendingTestAction(action);
  }

  async function confirmTestAction() {
    if (!pendingTestAction) {
      return;
    }
    setTestResponseMessage("");
    try {
      await onControlSlot(pendingTestAction);
      const completionMessage =
        pendingTestAction.action === "extend"
          ? `Action completed: extended by ${pendingTestAction.extend_minutes || extendMinutes} minutes. New planned end: ${formatDateTime(proposedExtendedEndAt)}.`
          : `Action completed: ${pendingActionLabel}.`;
      setTestResponseTone("success");
      setTestResponseMessage(completionMessage);
      setPendingTestAction(null);
    } catch {
      setTestResponseMessage("");
    }
  }

  async function saveSlotChanges() {
    setTestResponseMessage("");
    try {
      const timezoneOffsetMinutes = timezoneOffsetMinutesForLocalDateTime(
        editForm.start_at || editForm.end_at,
        editForm.timezone_name,
        editForm.timezone_offset_minutes,
      );
      const startAt = toIsoDateTimeForTimezone(
        editForm.start_at,
        editForm.timezone_name,
        timezoneOffsetMinutes,
      );
      const endAt = toIsoDateTimeForTimezone(
        editForm.end_at,
        editForm.timezone_name,
        timezoneOffsetMinutes,
      );
      if (new Date(startAt).getTime() < Date.now()) {
        throw new Error("Past times are unavailable. Choose a future start time.");
      }
      if (
        new Date(endAt).getTime() <
        new Date(startAt).getTime() + editForm.duration_minutes * 60_000
      ) {
        throw new Error(
          `End time must be at least ${editForm.duration_minutes} minutes after the start time.`,
        );
      }
      await onUpdateSlot({
        title: editForm.title,
        start_at: startAt,
        end_at: endAt,
        duration_minutes: editForm.duration_minutes,
        timezone_name: editForm.timezone_name,
        timezone_offset_minutes: timezoneOffsetMinutes,
        instructions_override: editForm.instructions_override,
        status: editForm.status,
      });
      setTestResponseTone("success");
      setTestResponseMessage(
        `Test details updated successfully. New window: ${formatDateTime(startAt)} to ${formatDateTime(endAt)}.`,
      );
      setIsEditingSlot(false);
      setIsManagingTest(false);
    } catch (error) {
      setTestResponseTone("warning");
      setTestResponseMessage(
        errorMessage(error) || "Choose a valid start and end time.",
      );
    }
  }

  return (
    <section className="assessment-drilldown">
      <div className="assessment-breadcrumb">
        <button type="button" onClick={onBack}>
          Back to tests
        </button>
        <span>/</span>
        <strong>{assessment.title}</strong>
        <span>/</span>
        <strong>{slot.title}</strong>
      </div>

      <Card className="assessment-panel assessment-command-center test-command-center">
        <div className="assessment-command-main">
          <div>
            <span className="panel-eyebrow">Test Session</span>
            <h2>{slot.title}</h2>
            <p>
              {formatDateTime(slot.start_at)} to {formatDateTime(slot.end_at)}
            </p>
            <p className="slot-live-line">{statusLabel}</p>
          </div>
          <div className="assessment-row-actions">
            <div className="status-with-dot">
              <HealthDot status={effectiveStatus} />
              <StatusBadge value={effectiveStatus} />
            </div>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsManagingTest(true)}
            >
              Manage Test
            </Button>
          </div>
        </div>

        <div className="assessment-hero-metrics assessment-command-metrics">
          <span>
            <strong>{slot.candidate_count}</strong>
            Candidates
          </span>
          <span>
            <strong>{inProgressCount}</strong>
            In progress
          </span>
          <span>
            <strong>{submittedCount}</strong>
            Submitted
          </span>
          <span>
            <strong>{slot.duration_minutes || assessment.duration_minutes}m</strong>
            Duration
          </span>
        </div>

        <div className="test-meta-line">
          <span>{slot.timezone_name}</span>
          <span>GMT offset {slot.timezone_offset_minutes} minutes</span>
          <span>{slot.is_accepting_responses ? "Accepting responses" : "Not accepting responses"}</span>
        </div>
      </Card>

      {!isManagingTest && testResponseMessage ? (
        <p className={`test-feedback-message is-${testResponseTone}`}>
          {testResponseMessage}
        </p>
      ) : null}

      {isManagingTest ? (
        <div className="dialog-backdrop">
          <div className="test-management-modal" role="dialog" aria-modal="true">
            <div className="panel-heading">
              <div>
                <span>Manage Test</span>
                <h2>{slot.title}</h2>
                <p>
                  Review the current test window, choose one action, then confirm
                  before the change is applied.
                </p>
              </div>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setIsManagingTest(false);
                  setPendingTestAction(null);
                  setIsEditingSlot(false);
                  setTestResponseMessage("");
                }}
              >
                Close
              </Button>
            </div>

            <div className="test-timing-summary">
              <div>
                <span>Current status</span>
                <strong>{effectiveStatus.replace("_", " ")}</strong>
                <em>{statusLabel}</em>
              </div>
              <div>
                <span>Start time</span>
                <strong>{formatDateTime(slot.start_at)}</strong>
                <em>{slot.timezone_name}</em>
              </div>
              <div>
                <span>End time</span>
                <strong>{formatDateTime(slot.end_at)}</strong>
                <em>
                  {effectiveStatus === "active"
                    ? `${formatCountdown(secondsUntilClose)} remaining`
                    : slot.is_accepting_responses
                      ? "Window is accepting responses"
                      : "Window is not accepting responses"}
                </em>
              </div>
              <div>
                <span>After extension</span>
                <strong>{formatDateTime(proposedExtendedEndAt)}</strong>
                <em>Based on +{Math.max(extendMinutes, 1)} minutes</em>
              </div>
            </div>

            <div className="test-management-actions">
              <button
                type="button"
                className={`test-action-card ${canPauseTest ? "" : "is-unavailable"}`}
                disabled={slotUpdatePending}
                onClick={() =>
                  requestTestAction(
                    { action: "pause" },
                    canPauseTest
                      ? undefined
                      : effectiveStatus === "paused"
                        ? "This test is already paused. Use Continue Test when candidates can resume."
                        : "This test is already closed, so it cannot be paused.",
                  )
                }
              >
                <span>Pause</span>
                <strong>Pause Test</strong>
                <em>
                  {canPauseTest
                    ? "Temporarily block candidate progress."
                    : "Not available for the current status."}
                </em>
              </button>
              <button
                type="button"
                className={`test-action-card ${canContinueTest ? "" : "is-unavailable"}`}
                disabled={slotUpdatePending}
                onClick={() =>
                  requestTestAction(
                    { action: "continue" },
                    canContinueTest
                      ? undefined
                      : "Continue becomes available only after this test is paused.",
                  )
                }
              >
                <span>Resume</span>
                <strong>Continue Test</strong>
                <em>
                  {canContinueTest
                    ? "Let candidates continue from saved progress."
                    : "Available only while paused."}
                </em>
              </button>
              <label className="field compact-field">
                <span>Extend minutes</span>
                <input
                  type="number"
                  min={1}
                  max={720}
                  value={extendMinutes}
                  onChange={(event) => setExtendMinutes(Number(event.target.value))}
                />
              </label>
              <button
                type="button"
                className={`test-action-card ${canExtendTest ? "" : "is-unavailable"}`}
                disabled={slotUpdatePending}
                onClick={() =>
                  requestTestAction(
                    {
                      action: "extend",
                      extend_minutes: Math.max(extendMinutes, 1),
                    },
                    canExtendTest
                      ? undefined
                      : "This test is closed. Reopening closed tests is not supported in this flow.",
                  )
                }
              >
                <span>Extend</span>
                <strong>Extend Time</strong>
                <em>New end: {formatDateTime(proposedExtendedEndAt)}</em>
              </button>
              <button
                type="button"
                className={`test-action-card test-action-danger ${canCloseTest ? "" : "is-unavailable"
                  }`}
                disabled={slotUpdatePending}
                onClick={() =>
                  requestTestAction(
                    { action: "close" },
                    canCloseTest
                      ? undefined
                      : "This test is already closed. No further close action is needed.",
                  )
                }
              >
                <span>Close</span>
                <strong>Close Test</strong>
                <em>
                  {canCloseTest
                    ? "Stop accepting candidate responses now."
                    : "Already closed."}
                </em>
              </button>
            </div>

            {pendingTestAction ? (
              <div className="test-confirm-panel">
                <div>
                  <strong>Confirm action</strong>
                  <p>Are you sure you want to {pendingActionLabel}?</p>
                  <p>{pendingActionImpact}</p>
                </div>
                <div className="assessment-row-actions">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setPendingTestAction(null)}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="button"
                    disabled={slotUpdatePending}
                    onClick={() => void confirmTestAction()}
                  >
                    {slotUpdatePending ? "Applying..." : "Confirm"}
                  </Button>
                </div>
              </div>
            ) : null}

            <div className="test-management-edit-header">
              <div>
                <span className="panel-eyebrow">Batch Details</span>
                <h3>Test schedule and instructions</h3>
              </div>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setIsEditingSlot((current) => !current)}
              >
                {isEditingSlot ? "Hide Edit" : "Edit Test Details"}
              </Button>
            </div>

            {isEditingSlot ? (
              <div className="assessment-form-stack slot-edit-form">
                <label className="field">
                  <span>Test title</span>
                  <input
                    value={editForm.title}
                    onChange={(event) =>
                      setEditForm({ ...editForm, title: event.target.value })
                    }
                  />
                </label>
                <div className="assessment-inline-fields">
                  <label className="field">
                    <span>Time region</span>
                    <select
                      value={editForm.timezone_name}
                      onChange={(event) => {
                        const timezone = TIME_ZONE_OPTIONS.find(
                          (option) => option.name === event.target.value,
                        );
                        if (!timezone) {
                          return;
                        }
                        setEditForm({
                          ...editForm,
                          timezone_name: timezone.name,
                          timezone_offset_minutes:
                            timezoneOffsetMinutesForLocalDateTime(
                              editForm.start_at || editForm.end_at,
                              timezone.name,
                              timezone.fallbackOffset,
                            ),
                        });
                      }}
                    >
                      {TIME_ZONE_OPTIONS.map((timezone) => (
                        <option
                          key={timezone.name}
                          value={timezone.name}
                        >
                          {timezone.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>Start time</span>
                    <input
                      type="datetime-local"
                      min={minimumEditStart}
                      value={editForm.start_at}
                      onChange={(event) => {
                        const startAt = event.target.value;
                        setEditForm({
                          ...editForm,
                          start_at: startAt,
                          end_at: addMinutesToLocalInput(startAt, editForm.duration_minutes),
                        });
                      }}
                    />
                  </label>
                  <label className="field">
                    <span>Test duration (minutes)</span>
                    <input
                      type="number"
                      min={15}
                      max={360}
                      value={editForm.duration_minutes}
                      onChange={(event) => {
                        const duration = Math.max(15, Number(event.target.value) || 15);
                        setEditForm({
                          ...editForm,
                          duration_minutes: duration,
                          end_at: addMinutesToLocalInput(editForm.start_at, duration),
                        });
                      }}
                    />
                  </label>
                  <label className="field">
                    <span>End time</span>
                    <input
                      type="datetime-local"
                      min={minimumEditEnd}
                      value={editForm.end_at}
                      onChange={(event) =>
                        setEditForm({ ...editForm, end_at: event.target.value })
                      }
                    />
                  </label>
                </div>
                <label className="field">
                  <span>Batch instructions override</span>
                  <textarea
                    value={editForm.instructions_override}
                    onChange={(event) =>
                      setEditForm({
                        ...editForm,
                        instructions_override: event.target.value,
                      })
                    }
                  />
                </label>
                <Button
                  type="button"
                  disabled={slotUpdatePending}
                  onClick={() => void saveSlotChanges()}
                >
                  {slotUpdatePending ? "Saving..." : "Save Slot Changes"}
                </Button>
              </div>
            ) : null}
            {testResponseMessage && testResponseTone === "warning" ? (
              <div className="question-flow-toast-stack" aria-live="assertive">
                <div className="question-flow-toast is-warning" role="alert">
                  <div><strong>Schedule warning</strong><p>{testResponseMessage}</p></div>
                  <button type="button" className="question-flow-toast-dismiss" onClick={() => setTestResponseMessage("")}>Close</button>
                </div>
              </div>
            ) : testResponseMessage ? (
              <p className="test-feedback-message is-success">{testResponseMessage}</p>
            ) : null}
            {slotUpdateError ? <p className="form-error">{slotUpdateError}</p> : null}
          </div>
        </div>
      ) : null}

      <div className="test-tab-bar">
        <button
          type="button"
          className={tab === "candidates" ? "is-active" : ""}
          onClick={() => onTabChange("candidates")}
        >
          Candidates & Batch
        </button>
        <button
          type="button"
          className={tab === "live" ? "is-active" : ""}
          onClick={() => onTabChange("live")}
        >
          Live Monitoring
        </button>
        <button
          type="button"
          className={tab === "results" ? "is-active" : ""}
          onClick={() => onTabChange("results")}
        >
          Results & Leaderboard
        </button>
      </div>

      {tab === "candidates" ? (
        <CandidatesTab
          slot={slot}
          candidateCsv={candidateCsv}
          candidates={candidates}
          importPending={importPending}
          invitePending={invitePending}
          importErrors={importErrors}
          importError={importError}
          inviteError={inviteError}
          resendPendingId={resendPendingId}
          onCsvChange={onCsvChange}
          onImport={onImport}
          onSendInvites={onSendInvites}
          onResend={onResend}
        />
      ) : null}

      {tab === "live" ? (
        <LiveMonitoringTab
          items={monitoringItems}
          loading={monitoringLoading}
        />
      ) : null}

      {tab === "results" ? (
        <TestResultsTab
          assessmentId={assessment.id}
          slotId={slot.id}
          candidates={candidates}
          backfillPending={evaluationBackfillPending}
          backfillError={evaluationBackfillError}
          backfillResult={evaluationBackfillResult}
          onBackfillEvaluations={onBackfillEvaluations}
        />
      ) : null}
    </section>
  );
}

function CandidatesTab({
  slot,
  candidateCsv,
  candidates,
  importPending,
  invitePending,
  importErrors,
  importError,
  inviteError,
  resendPendingId,
  onCsvChange,
  onImport,
  onSendInvites,
  onResend,
}: {
  slot: AssessmentSlot;
  candidateCsv: string;
  candidates: SlotCandidate[];
  importPending: boolean;
  invitePending: boolean;
  importErrors: Array<{ row_number: number; email: string; errors: string[] }>;
  importError: string;
  inviteError: string;
  resendPendingId: string | null;
  onCsvChange: (value: string) => void;
  onImport: (csvText: string) => void;
  onSendInvites: (candidateAssessmentIds?: string[]) => void;
  onResend: (candidateAssessmentId: string) => void;
}) {
  const [entryMode, setEntryMode] = useState<CandidateEntryMode>("csv");
  const [showCandidateEntry, setShowCandidateEntry] = useState(false);
  const [manualRows, setManualRows] = useState<ManualCandidateRow[]>([
    createManualCandidateRow(),
  ]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<string>>(
    () => new Set(),
  );

  useEffect(() => {
    const visibleCandidateIds = new Set(
      candidates.map((candidate) => candidate.candidate_assessment_id),
    );
    setSelectedCandidateIds((current) => {
      const next = new Set(
        [...current].filter((candidateId) => visibleCandidateIds.has(candidateId)),
      );
      return next.size === current.size ? current : next;
    });
  }, [candidates]);

  const manualCsv = useMemo(() => buildCandidateCsv(manualRows), [manualRows]);
  const manualHasRows = manualRows.some(
    (row) => row.name.trim() || row.email.trim() || row.external_id.trim(),
  );
  const selectedIds = [...selectedCandidateIds];
  const allSelected = Boolean(candidates.length) && selectedIds.length === candidates.length;

  function updateManualRow(
    rowId: string,
    field: keyof Omit<ManualCandidateRow, "row_id">,
    value: string,
  ) {
    setManualRows((current) =>
      current.map((row) => (row.row_id === rowId ? { ...row, [field]: value } : row)),
    );
  }

  function removeManualRow(rowId: string) {
    setManualRows((current) =>
      current.length === 1
        ? [createManualCandidateRow()]
        : current.filter((row) => row.row_id !== rowId),
    );
  }

  function toggleCandidateSelection(candidateAssessmentId: string, checked: boolean) {
    setSelectedCandidateIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(candidateAssessmentId);
      } else {
        next.delete(candidateAssessmentId);
      }
      return next;
    });
  }

  function toggleAllCandidates(checked: boolean) {
    setSelectedCandidateIds(
      checked
        ? new Set(candidates.map((candidate) => candidate.candidate_assessment_id))
        : new Set(),
    );
  }

  return (
    <section className="assessment-console">
      {!showCandidateEntry ? (
        <Card className="assessment-panel action-drawer-card">
          <div className="panel-heading">
            <div>
              <span>Candidate Batch</span>
              <h2>Add candidates when you are ready</h2>
              <p>
                Keep this test page focused on the current batch. Open candidate
                entry only when you need to import or type new candidates.
              </p>
            </div>
            <Button type="button" onClick={() => setShowCandidateEntry(true)}>
              Add Candidates
            </Button>
          </div>
        </Card>
      ) : (
        <Card className="assessment-panel candidate-import-card action-drawer-card">
          <div className="panel-heading">
            <div>
              <span>Candidate Setup</span>
              <h2>Add candidates</h2>
              <p>Import a batch first. Invites are sent only when you click send.</p>
            </div>
            <div className="assessment-row-actions">
              <StatusBadge value={slot.status} />
              <Button
                type="button"
                variant="secondary"
                onClick={() => setShowCandidateEntry(false)}
              >
                Close
              </Button>
            </div>
          </div>
          <div className="candidate-entry-tabs">
            <button
              type="button"
              className={entryMode === "csv" ? "is-active" : ""}
              onClick={() => setEntryMode("csv")}
            >
              CSV upload or paste
            </button>
            <button
              type="button"
              className={entryMode === "manual" ? "is-active" : ""}
              onClick={() => setEntryMode("manual")}
            >
              Type candidates
            </button>
          </div>

          {entryMode === "csv" ? (
            <div className="candidate-entry-panel">
              <p className="assessment-context-banner">
                Use columns: name, email, external_id. You can upload a CSV file or
                paste rows below.
              </p>
              <label className="candidate-upload-dropzone">
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (!file) {
                      return;
                    }
                    void file.text().then((text) => onCsvChange(text));
                    event.target.value = "";
                  }}
                />
                <strong>Upload CSV</strong>
                <span>or paste/edit the same content below</span>
              </label>
              <textarea
                className="candidate-csv-box"
                value={candidateCsv}
                onChange={(event) => onCsvChange(event.target.value)}
              />
              <div className="assessment-actions-row">
                <Button
                  type="button"
                  onClick={() => onImport(candidateCsv)}
                  disabled={importPending || !candidateCsv.trim()}
                >
                  {importPending ? "Importing..." : "Import CSV Candidates"}
                </Button>
              </div>
            </div>
          ) : (
            <div className="candidate-entry-panel">
              <p className="assessment-context-banner">
                Add candidates one by one. External ID is optional and useful for
                college roll numbers or HR IDs.
              </p>
              <div className="manual-candidate-list">
                {manualRows.map((row, index) => (
                  <div className="manual-candidate-row" key={row.row_id}>
                    <label className="field">
                      <span>Name</span>
                      <input
                        placeholder={`Candidate ${index + 1}`}
                        value={row.name}
                        onChange={(event) =>
                          updateManualRow(row.row_id, "name", event.target.value)
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Email</span>
                      <input
                        type="email"
                        placeholder="candidate@example.com"
                        value={row.email}
                        onChange={(event) =>
                          updateManualRow(row.row_id, "email", event.target.value)
                        }
                      />
                    </label>
                    <label className="field">
                      <span>External ID</span>
                      <input
                        placeholder="Optional"
                        value={row.external_id}
                        onChange={(event) =>
                          updateManualRow(
                            row.row_id,
                            "external_id",
                            event.target.value,
                          )
                        }
                      />
                    </label>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => removeManualRow(row.row_id)}
                    >
                      Remove
                    </Button>
                  </div>
                ))}
              </div>
              <div className="assessment-actions-row">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() =>
                    setManualRows((current) => [...current, createManualCandidateRow()])
                  }
                >
                  Add another candidate
                </Button>
                <Button
                  type="button"
                  onClick={() => onImport(manualCsv)}
                  disabled={importPending || !manualHasRows}
                >
                  {importPending ? "Importing..." : "Import Typed Candidates"}
                </Button>
              </div>
            </div>
          )}

          {importError ? <p className="form-error">{importError}</p> : null}
          {inviteError ? <p className="form-error">{inviteError}</p> : null}
          {importErrors.length ? (
            <div className="import-error-list">
              {importErrors.map((error) => (
                <p key={`${error.row_number}-${error.email}`}>
                  Row {error.row_number}: {error.errors.join(", ")}
                </p>
              ))}
            </div>
          ) : null}
        </Card>
      )}

      <Card className="assessment-panel">
        <div className="panel-heading">
          <div>
            <span>Candidate List</span>
            <h2>{candidates.length} candidates</h2>
            <p>Select rows when you want to send invites to only a few people.</p>
          </div>
        </div>
        <div className="candidate-invite-actions">
          <Button
            type="button"
            disabled={invitePending || candidates.length === 0}
            onClick={() => onSendInvites()}
          >
            {invitePending ? "Sending invites..." : "Send invites"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={invitePending || selectedIds.length === 0}
            onClick={() => onSendInvites(selectedIds)}
          >
            Send selected ({selectedIds.length})
          </Button>
        </div>
        <CandidateTable
          candidates={candidates}
          resendPendingId={resendPendingId}
          selectedCandidateIds={selectedCandidateIds}
          allSelected={allSelected}
          onToggleAll={toggleAllCandidates}
          onToggleCandidate={toggleCandidateSelection}
          onResend={onResend}
        />
      </Card>
    </section>
  );
}

function CandidateTable({
  candidates,
  resendPendingId,
  selectedCandidateIds,
  allSelected,
  onToggleAll,
  onToggleCandidate,
  onResend,
}: {
  candidates: SlotCandidate[];
  resendPendingId: string | null;
  selectedCandidateIds: Set<string>;
  allSelected: boolean;
  onToggleAll: (checked: boolean) => void;
  onToggleCandidate: (candidateAssessmentId: string, checked: boolean) => void;
  onResend: (candidateAssessmentId: string) => void;
}) {
  if (!candidates.length) {
    return <EmptyState label="Imported candidates for this test will appear here." />;
  }

  return (
    <div className="assessment-table-shell">
      <table className="assessment-table compact-table">
        <thead>
          <tr>
            <th className="candidate-select-cell">
              <input
                type="checkbox"
                aria-label="Select all candidates"
                checked={allSelected}
                onChange={(event) => onToggleAll(event.target.checked)}
              />
            </th>
            <th>Candidate</th>
            <th>Invite</th>
            <th>Assessment</th>
            <th>Activity</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => (
            <tr key={candidate.candidate_assessment_id}>
              <td className="candidate-select-cell">
                <input
                  type="checkbox"
                  aria-label={`Select ${candidate.name}`}
                  checked={selectedCandidateIds.has(
                    candidate.candidate_assessment_id,
                  )}
                  onChange={(event) =>
                    onToggleCandidate(
                      candidate.candidate_assessment_id,
                      event.target.checked,
                    )
                  }
                />
              </td>
              <td>
                <div className="assessment-name-cell">
                  <strong>{candidate.name}</strong>
                  <span>{candidate.email}</span>
                </div>
              </td>
              <td>
                <StatusBadge value={candidate.invite_status} />
              </td>
              <td>
                <div className="status-with-dot">
                  <HealthDot status={candidate.assessment_status} />
                  <StatusBadge value={candidate.assessment_status} />
                </div>
              </td>
              <td>{formatDateTime(candidate.last_activity_at)}</td>
              <td>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={resendPendingId === candidate.candidate_assessment_id}
                  onClick={() => onResend(candidate.candidate_assessment_id)}
                >
                  {resendPendingId === candidate.candidate_assessment_id
                    ? "Sending..."
                    : "Resend"}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LiveMonitoringTab({
  items,
  loading,
}: {
  items: MonitoringCandidate[];
  loading: boolean;
}) {
  const statusCounts = items.reduce(
    (counts, item) => ({
      ...counts,
      [item.status]: (counts[item.status] || 0) + 1,
    }),
    {} as Record<CandidateAssessmentStatus, number>,
  );

  return (
    <Card className="assessment-panel assessment-panel-wide">
      <div className="panel-heading">
        <div>
          <span>Live Monitoring</span>
          <h2>Candidate Activity</h2>
        </div>
        <strong>Refreshes every 15 seconds</strong>
      </div>

      <div className="monitoring-status-strip">
        <MetricTile label="Not started" value={statusCounts.not_started || 0} />
        <MetricTile label="In progress" value={statusCounts.in_progress || 0} />
        <MetricTile label="Submitted" value={(statusCounts.submitted || 0) + (statusCounts.auto_submitted || 0)} />
      </div>

      {loading ? <EmptyState label="Loading live activity..." /> : null}
      {!loading && items.length ? (
        <div className="assessment-table-shell">
          <table className="assessment-table compact-table">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Status</th>
                <th>Current Q</th>
                <th>Questions touched</th>
                <th>Hidden checks</th>
                <th>Time left</th>
                <th>Submit reason</th>
              </tr>
            </thead>
            <tbody>
              {items.map((candidate) => (
                <tr key={candidate.candidate_assessment_id}>
                  <td>
                    <div className="assessment-name-cell">
                      <strong>{candidate.name}</strong>
                      <span>{candidate.email}</span>
                    </div>
                  </td>
                  <td>
                    <div className="status-with-dot">
                      <HealthDot status={candidate.status} />
                      <StatusBadge value={candidate.status} />
                    </div>
                  </td>
                  <td>Q{candidate.current_question_order || "-"}</td>
                  <td>{candidate.questions_attempted}</td>
                  <td>{candidate.hidden_checks_used}</td>
                  <td>{formatDuration(candidate.time_remaining_seconds)}</td>
                  <td>
                    {candidate.submission_tag ? (
                      <div className="assessment-name-cell">
                        <strong>{candidate.submission_tag}</strong>
                        <span>{candidate.submission_message || "Auto submit"}</span>
                      </div>
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {!loading && !items.length ? (
        <EmptyState label="Live activity appears after candidates open their invite links." />
      ) : null}
    </Card>
  );
}
