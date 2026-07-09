import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Archive,
  ArchiveRestore,
  ArrowLeft,
  BarChart3,
  BadgeCheck,
  Check,
  ChevronRight,
  Clock3,
  Code2,
  Download,
  Gauge,
  Info,
  ListChecks,
  Settings,
  Trash2,
} from "lucide-react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { ScheduleDateTimePicker } from "../../../components/ui/ScheduleDateTimePicker";
import { ToastNotification } from "../../../components/ui/ToastNotification";
import { useAuth } from "../../auth";
import { AssessmentEvaluationPanel } from "./AssessmentEvaluationPanel";
import { AssessmentList } from "./AssessmentList";
import {
  EmptyState,
  HealthDot,
  StatusBadge,
} from "./AssessmentStatusPrimitives";
import { TestDetailView, type TestTab } from "./TestDetailView";
import {
  assessmentToPayload,
  buildAssessmentQuestionAssignments,
  calculateQuestionTemplateMarks,
  clampLocalInputToMinimum,
  createDefaultSlotSchedule,
  createEmptyAssessment,
  createQuestionBlueprint,
  errorMessage,
  formatDateTime,
  getSlotScheduleFieldErrors,
  marksSummaryForDifficulty,
  minimumSlotEndInput,
  nextAvailableTimeInput,
  reorderQuestionIds,
  TIME_ZONE_OPTIONS,
  timezoneOffsetMinutesForLocalDateTime,
  toIsoDateTimeForTimezone,
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
  EvaluationBackfillResponse,
} from "../types/Assessment";
import type {
  DifficultyLevel,
  QuestionGroupCreatePayload,
  QuestionGroupRecord,
  QuestionRecord,
} from "../types/QuestionBank";
import { assessmentPath, assessmentTestPath } from "../utils/assessmentRoutes";

type RecruiterView = "list" | "create" | "assessment" | "test";
type AssessmentDetailMode = "tests" | "questions" | "analytics";
type QuestionSetMode = "select-questions" | "select-groups" | "custom";
type AssessmentCreateSection = "basics" | "questions" | "rules";
type QuestionSetupStep = 1 | 2 | 3 | 4;

const ASSESSMENT_LANGUAGES = ["python", "java", "cpp", "c"] as const;
const QUESTION_DIFFICULTIES: DifficultyLevel[] = ["easy", "medium", "hard"];
const LANGUAGE_LABELS: Record<(typeof ASSESSMENT_LANGUAGES)[number], string> = {
  python: "Python",
  java: "Java",
  cpp: "C++",
  c: "C",
};

const PROCTORING_POLICY_OPTIONS = [
  {
    value: "basic",
    title: "Basic monitoring",
    summary: "Light monitoring with warnings before auto-submit.",
    restrictions: [
      "Records tab switches and warns candidates",
      "Auto-submits after 3 tab-switch warnings",
      "Logs clipboard copy, cut, and paste activity",
    ],
  },
  {
    value: "strict",
    title: "Strict monitoring",
    summary: "Highest integrity with fullscreen and blocked clipboard.",
    restrictions: [
      "Requires fullscreen mode during the test",
      "Auto-submits if fullscreen is exited",
      "Auto-submits after 3 tab-switch warnings",
      "Blocks copy, cut, and paste",
    ],
  },
  {
    value: "none",
    title: "No proctoring",
    summary: "No monitoring restrictions during the test.",
    restrictions: [
      "No tab-switch warnings or auto-submit",
      "No clipboard monitoring",
      "No fullscreen requirement",
    ],
  },
] as const;

export function RecruiterAssessmentsPage() {
  const { currentUser } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const {
    assessmentId: routeAssessmentId,
    assessmentTestId: routeAssessmentTestId,
    testId: routeTestId,
  } = useParams<{
    assessmentId?: string;
    assessmentTestId?: string;
    testId?: string;
  }>();
  const targetTestId = routeAssessmentTestId || routeTestId || null;
  const isCreateRoute = location.pathname === "/recruiter/assessments/new";
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
  const canToggleArchive = Boolean(selectedAssessment);

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
    if (!targetTestId) {
      setSelectedSlotId(null);
    }
    setTestTab("candidates");
  }, [targetTestId, selectedAssessmentId]);

  useEffect(() => {
    if (isCreateRoute) {
      setSelectedAssessmentId(null);
      setSelectedSlotId(null);
      setView("create");
      return;
    }
    if (!routeAssessmentId && !targetTestId) {
      setSelectedAssessmentId(null);
      setSelectedSlotId(null);
      setView("list");
      return;
    }

    let resolvedAssessmentId = routeAssessmentId || null;
    if (!resolvedAssessmentId && targetTestId && assessments.length > 0) {
      const found = assessments.find((assessment) =>
        (assessment.slots || []).some((slot) => slot.id === targetTestId)
      );
      if (found) {
        resolvedAssessmentId = found.id;
      }
    }

    setSelectedAssessmentId(resolvedAssessmentId);
    setSelectedSlotId(targetTestId || null);
    setView(targetTestId ? "test" : "assessment");
  }, [isCreateRoute, routeAssessmentId, targetTestId, assessments]);

  useEffect(() => {
    if (!selectedAssessmentId || assessmentsQuery.isLoading) {
      return;
    }
    if (!selectedAssessment) {
      navigate("/recruiter/assessments", { replace: true });
      return;
    }
    if (targetTestId) {
      if (
        !slotsQuery.isSuccess ||
        slotsQuery.isFetching ||
        selectedSlotId !== targetTestId
      ) {
        return;
      }
      if (!slots.some((slot) => slot.id === targetTestId)) {
        navigate(assessmentPath(selectedAssessment.id, selectedAssessment.title), { replace: true });
      }
    }
  }, [
    assessmentsQuery.isLoading,
    navigate,
    targetTestId,
    selectedAssessment,
    selectedAssessmentId,
    selectedSlotId,
    slots,
    slotsQuery.isSuccess,
    slotsQuery.isFetching,
  ]);

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
    navigate(assessmentPath(created.id, created.title));
  }

  async function handleArchiveAssessment() {
    if (!selectedAssessment) {
      return;
    }
    const nextStatus = selectedAssessment.status === "archived" ? "available" : "archived";
    await updateAssessmentMutation.mutateAsync({
      assessmentId: selectedAssessment.id,
      payload: { status: nextStatus },
    });
    setAssessmentPageSuccessMessage(
      nextStatus === "archived"
        ? "Assessment archived successfully."
        : "Assessment restored successfully.",
    );
  }

  async function handleDeleteAssessment() {
    if (!selectedAssessment) {
      return;
    }
    await deleteAssessmentMutation.mutateAsync(selectedAssessment.id);
    setSelectedAssessmentId(null);
    setAssessmentPageSuccessMessage("Assessment deleted successfully.");
    setView("list");
    navigate("/recruiter/assessments");
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
    if (!selectedAssessmentId || !selectedAssessment) {
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
    navigate(assessmentTestPath(selectedAssessment.id, created.id, selectedAssessment.title, created.title));
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


  return (
    <main className="recruiter-assessments-page assessment-flow-page">
      {warningToast ? (
        <ToastNotification
          title="Question selection"
          message={warningToast}
          tone="warning"
          onClose={() => setWarningToast("")}
        />
      ) : null}
      {view === "list" ? (
        <AssessmentList
          assessments={assessments}
          loading={assessmentsQuery.isLoading}
          onAddNew={() => navigate("/recruiter/assessments/new")}
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
          onBack={() => {
            navigate("/recruiter/assessments");
            setView("list");
          }}
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
          canArchive={canToggleArchive}
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
            navigate("/recruiter/assessments");
            setView("list");
          }}
          onArchive={handleArchiveAssessment}
          onDeleteAssessment={handleDeleteAssessment}
          onUpdateAssessment={handleUpdateAssessment}
          onSaveQuestions={handleSaveQuestions}
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
          onBack={() => {
            navigate(assessmentPath(selectedAssessment.id, selectedAssessment.title));
            setView("assessment");
          }}
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
  const [visitedSections, setVisitedSections] = useState<Set<AssessmentCreateSection>>(
    () => new Set(),
  );
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
  const [questionSetupStep, setQuestionSetupStep] = useState<QuestionSetupStep>(1);
  const [activeQuestionSetupStep, setActiveQuestionSetupStep] =
    useState<QuestionSetupStep>(1);
  const [deliveryConfigured, setDeliveryConfigured] = useState(false);
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
  const blueprintMismatches = selectedQuestionViews.filter((question, index) => {
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
  const questionSetReady = deliveryConfigured && (assessmentForm.shuffle_questions
    ? selectedQuestionIds.length >= desiredQuestionCount && randomPoolMatchesBlueprint
    : selectedQuestionIds.length === desiredQuestionCount && blueprintMismatches.length === 0);
  const rulesReady = scoringIsValid && assessmentForm.supported_languages.length > 0;
  const requiredMark = <em className="required-indicator" aria-hidden="true">*</em>;
  const sectionDefinitions = [
    {
      id: "basics" as const,
      label: "Basics",
      title: "Basics",
      ready: basicsReady,
    },
    {
      id: "questions" as const,
      label: "Questions",
      title: "Question set",
      ready: questionSetReady,
    },
    {
      id: "rules" as const,
      label: "Rules",
      title: "Scoring & policy",
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
    const visited = visitedSections.has(section);
    const classes: string[] = [];

    if (activeSection === section) {
      classes.push("is-active");
    }

    if (visited) {
      classes.push(done ? "is-complete" : "is-needed");
    }

    return classes.join(" ");
  }

  function navigateToSection(section: AssessmentCreateSection) {
    if (section !== activeSection) {
      setVisitedSections((current) => {
        if (current.has(activeSection)) {
          return current;
        }
        const next = new Set(current);
        next.add(activeSection);
        return next;
      });
    }
    setActiveSection(section);
  }

  function moveToSection(section: AssessmentCreateSection) {
    navigateToSection(section);
  }

  function goToPreviousSection() {
    if (activeSectionIndex <= 0) {
      return;
    }
    navigateToSection(sectionDefinitions[activeSectionIndex - 1].id);
  }

  function goToNextSection() {
    if (!sectionReady(activeSection) || activeSectionIndex >= sectionDefinitions.length - 1) {
      return;
    }
    navigateToSection(sectionDefinitions[activeSectionIndex + 1].id);
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
    if (safeCount === desiredQuestionCount) {
      return;
    }
    setDesiredQuestionCount(safeCount);
    const nextBlueprint = createQuestionBlueprint(safeCount);
    setDifficultyBlueprint(nextBlueprint);
    setQuestionSetupStep(1);
    setActiveQuestionSetupStep(1);
    setDeliveryConfigured(false);
    setSelectedGroupId("");
    if (selectedQuestionIds.length) {
      onChangeQuestions([]);
      setSelectionWarning(
        `Question count changed to ${safeCount}. Previous selections were cleared because the required template changed.`,
      );
    }
    onChange({
      ...assessmentForm,
      question_count_per_candidate: safeCount,
      difficulty_blueprint: nextBlueprint,
      shuffle_questions: false,
    });
  }

  function confirmQuestionCount() {
    setQuestionSetupStep((current) => Math.max(current, 2) as QuestionSetupStep);
    setActiveQuestionSetupStep(2);
  }

  function confirmDifficultyBlueprint() {
    setQuestionSetupStep((current) => Math.max(current, 3) as QuestionSetupStep);
    setActiveQuestionSetupStep(3);
  }

  function configureDelivery(shuffleQuestions: boolean) {
    let keepSelection = selectedQuestionIds.length === 0;
    if (selectedQuestionIds.length) {
      keepSelection = shuffleQuestions
        ? selectedQuestionIds.length >= desiredQuestionCount && randomPoolMatchesBlueprint
        : selectedQuestionIds.length === desiredQuestionCount && blueprintMismatches.length === 0;
    }
    if (!keepSelection) {
      onChangeQuestions([]);
      setSelectedGroupId("");
      setSelectionWarning(
        "Delivery mode changed. Previous questions were cleared because they do not satisfy the new selection rules.",
      );
    }
    setDeliveryConfigured(true);
    setQuestionSetupStep(4);
    setActiveQuestionSetupStep(4);
    onChange({
      ...assessmentForm,
      shuffle_questions: shuffleQuestions,
    });
  }

  function groupMatchesConfiguredTemplate(group: QuestionGroupRecord) {
    const groupDifficulties = group.question_ids.map((questionId) =>
      group.questions.find((question) => question.id === questionId)?.difficulty ||
      questionById.get(questionId)?.difficulty,
    );
    if (groupDifficulties.some((difficulty) => !difficulty)) {
      return false;
    }
    if (!assessmentForm.shuffle_questions) {
      return (
        group.question_ids.length === desiredQuestionCount &&
        groupDifficulties.every(
          (difficulty, index) => difficulty === difficultyBlueprint[index],
        )
      );
    }
    const groupCounts = groupDifficulties.reduce<Record<DifficultyLevel, number>>(
      (counts, difficulty) => ({
        ...counts,
        [difficulty as DifficultyLevel]: counts[difficulty as DifficultyLevel] + 1,
      }),
      { easy: 0, medium: 0, hard: 0 },
    );
    return (
      group.question_ids.length >= desiredQuestionCount &&
      QUESTION_DIFFICULTIES.every(
        (difficulty) => groupCounts[difficulty] >= blueprintCounts[difficulty],
      )
    );
  }

  function applyGroupQuestions(group: QuestionGroupRecord) {
    if (!groupMatchesConfiguredTemplate(group)) {
      setSelectionWarning(
        `The ${group.name} group does not match the configured count, difficulty order, or delivery mode.`,
      );
      return false;
    }
    onChangeQuestions(group.question_ids);
    return true;
  }

  function chooseGroup(groupId: string) {
    setSelectedGroupId(groupId);
    const group = questionGroups.find((item) => item.id === groupId);
    if (!group) {
      return;
    }
    if (!applyGroupQuestions(group)) {
      setSelectedGroupId("");
    }
  }

  function handleImportFromGroup() {
    const group = questionGroups.find((item) => item.id === selectedImportGroupId);
    if (!group) {
      return;
    }
    if (!applyGroupQuestions(group)) {
      return;
    }
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
    if (difficultyBlueprint[index] === difficulty) {
      return;
    }
    const nextBlueprint = difficultyBlueprint.map((item, itemIndex) =>
      itemIndex === index ? difficulty : item,
    );
    setDifficultyBlueprint(nextBlueprint);
    setQuestionSetupStep(2);
    setActiveQuestionSetupStep(2);
    setDeliveryConfigured(false);
    setSelectedGroupId("");
    if (selectedQuestionIds.length) {
      onChangeQuestions([]);
      setSelectionWarning(
        "Difficulty requirements changed. Previous questions were cleared so every slot can be matched correctly.",
      );
    }
    onChange({
      ...assessmentForm,
      difficulty_blueprint: nextBlueprint,
      shuffle_questions: false,
    });
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
        <ToastNotification
          title="Question selection"
          message={selectionWarning}
          tone="warning"
          onClose={() => setSelectionWarning("")}
        />
      ) : null}
      <button type="button" className="assessment-back-link" onClick={onBack}>
        <ArrowLeft size={16} />
        Back to assessments
      </button>

      <Card className="assessment-panel assessment-panel-wide assessment-create-panel">
        <div className="assessment-builder-wizard">
          <div className="assessment-builder-banner">
            <div className="assessment-builder-banner-copy">
              <h2>Create assessment</h2>
            </div>
            <div className="assessment-builder-metrics" aria-label="Assessment setup summary">
              <span>
                <strong>{desiredQuestionCount}</strong>
                Questions
              </span>
              <span>
                <strong>{selectedQuestionIds.length}</strong>
                Selected
              </span>
              <span>
                <strong>{assessmentForm.passing_score}%</strong>
                Pass mark
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
                <span>{visitedSections.has(step.id) && step.ready ? "✓" : index + 1}</span>
                <strong>{step.label}</strong>
              </button>
            ))}
          </div>

          <div className="assessment-builder-shell">
            <div className="assessment-builder-header assessment-builder-header-compact">
              <h3>{activeSectionDefinition.title}</h3>
            </div>

            <div className="assessment-builder-form-body">
            {activeSection === "basics" ? (
              <div className="assessment-form-stack assessment-form-pro assessment-create-form">
                <div className="assessment-form-section assessment-section-pro assessment-builder-page-card">
                  <label className="field field-pro field-full">
                    <span>
                      Title {requiredMark}
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
                        Pass mark {requiredMark}
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
                        rows={2}
                        placeholder="What this assessment evaluates"
                        value={assessmentForm.description}
                        onChange={(event) =>
                          onChange({ ...assessmentForm, description: event.target.value })
                        }
                      />
                    </label>
                    <label className="field field-pro field-full">
                      <span>Instructions for candidates</span>
                      <textarea
                        rows={2}
                        placeholder="Timing, languages, and rules"
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
              <div className="assessment-form-stack assessment-form-stack-fill assessment-form-pro assessment-create-form">
                <div className="assessment-form-section assessment-section-pro assessment-builder-page-card">
                  <div className="question-setup-tabs" role="tablist" aria-label="Question selection setup">
                    {[
                      { step: 1 as const, label: "Count" },
                      { step: 2 as const, label: "Difficulty" },
                      { step: 3 as const, label: "Delivery" },
                      { step: 4 as const, label: "Select" },
                    ].map((item) => {
                      const complete = item.step < questionSetupStep || (item.step === 4 && questionSetReady);
                      const available = item.step <= questionSetupStep;
                      return (
                        <button
                          key={item.step}
                          type="button"
                          role="tab"
                          aria-selected={item.step === activeQuestionSetupStep}
                          disabled={!available}
                          className={`${complete ? "is-complete" : "is-needed"} ${item.step === activeQuestionSetupStep ? "is-active" : ""}`}
                          onClick={() => available && setActiveQuestionSetupStep(item.step)}
                        >
                          <span>{complete ? "✓" : item.step}</span>
                          <strong>{item.label}</strong>
                        </button>
                      );
                    })}
                  </div>

                  <div className="question-setup-flow">
                    {activeQuestionSetupStep === 1 ? (
                    <section className={`question-setup-card is-visible ${questionSetupStep > 1 ? "is-complete" : ""} is-current`}>
                      <div className="question-setup-card-heading">
                        <strong>Questions per candidate</strong>
                      </div>
                      <div className="question-count-control">
                        <label className="field field-pro metric-field">
                          <span>Count {requiredMark}</span>
                          <input
                            type="number"
                            min={1}
                            max={50}
                            value={desiredQuestionCount}
                            onChange={(event) => updateQuestionCount(Number(event.target.value))}
                          />
                        </label>
                        <Button type="button" onClick={confirmQuestionCount}>
                          Continue
                        </Button>
                      </div>
                    </section>
                    ) : null}

                    {activeQuestionSetupStep === 2 && questionSetupStep >= 2 ? (
                      <section className={`question-setup-card is-visible ${questionSetupStep > 2 ? "is-complete" : ""} is-current`}>
                        <div className="question-setup-card-heading">
                          <strong>Difficulty per slot</strong>
                        </div>
                        <div className="difficulty-slot-grid question-setup-difficulty-grid">
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
                                  <option key={item} value={item}>{item}</option>
                                ))}
                              </select>
                            </label>
                          ))}
                        </div>
                        <div className="question-setup-card-actions">
                          <Button type="button" onClick={confirmDifficultyBlueprint}>
                            Continue
                          </Button>
                        </div>
                      </section>
                    ) : null}

                    {activeQuestionSetupStep === 3 && questionSetupStep >= 3 ? (
                      <section className={`question-setup-card is-visible ${questionSetupStep > 3 ? "is-complete" : ""} is-current`}>
                        <div className="question-setup-card-heading">
                          <strong>Delivery mode</strong>
                        </div>
                        <div className="question-delivery-toggle" role="group" aria-label="Question delivery mode">
                          <button
                            type="button"
                            className={deliveryConfigured && !assessmentForm.shuffle_questions ? "is-active" : ""}
                            onClick={() => configureDelivery(false)}
                          >
                            <strong>Fixed set</strong>
                            <span>Same {desiredQuestionCount} questions for every candidate.</span>
                          </button>
                          <button
                            type="button"
                            className={deliveryConfigured && assessmentForm.shuffle_questions ? "is-active" : ""}
                            onClick={() => configureDelivery(true)}
                          >
                            <strong>Randomized</strong>
                            <span>Pick {desiredQuestionCount} from a larger pool.</span>
                          </button>
                        </div>
                      </section>
                    ) : null}

                    {activeQuestionSetupStep === 4 && questionSetupStep >= 4 ? (
                      <section className="question-setup-card question-selection-stage is-visible is-current">
                        <div className="question-set-mode-grid" role="tablist" aria-label="Question set source">
                          {[
                            { mode: "select-questions" as const, title: "Questions" },
                            { mode: "select-groups" as const, title: "Groups" },
                            { mode: "custom" as const, title: "Save as group" },
                          ].map((option) => (
                            <button
                              key={option.mode}
                              type="button"
                              className={questionSetMode === option.mode ? "is-active" : ""}
                              onClick={() => {
                                if (questionSetMode !== option.mode && selectedQuestionIds.length) {
                                  onChangeQuestions([]);
                                  setSelectedGroupId("");
                                  setSelectionWarning("Question source changed. Previous selections were cleared.");
                                }
                                setQuestionSetMode(option.mode);
                                setGroupSaveSuccess("");
                              }}
                            >
                              <strong>{option.title}</strong>
                            </button>
                          ))}
                        </div>

                  {questionSetMode === "custom" ? (
                    <div className="custom-group-composer-card">
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
                          <span>Import group</span>
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
                          placeholder="Optional"
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
                          {createGroupPending ? "Saving..." : "Save & apply"}
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
                          questionGroups.map((group) => {
                            const matchesTemplate = groupMatchesConfiguredTemplate(group);
                            return (
                              <button
                                key={group.id}
                                type="button"
                                disabled={!matchesTemplate}
                                className={selectedGroupId === group.id ? "is-selected" : ""}
                                onClick={() => chooseGroup(group.id)}
                              >
                                <strong>{group.name}</strong>
                                <span>{group.question_count} questions</span>
                                {!matchesTemplate ? <small>Does not match template</small> : null}
                              </button>
                            );
                          })
                        ) : (
                          <EmptyState label="No question groups yet." />
                        )}
                      </div>
                    ) : (
                      <div className="question-bank-picker">
                        <div className="template-quota-grid" aria-label="Question template progress">
                          {QUESTION_DIFFICULTIES.filter(
                            (difficulty) => blueprintCounts[difficulty] > 0,
                          ).map((difficulty) => {
                            const complete = selectedDifficultyCounts[difficulty] >= blueprintCounts[difficulty];
                            return (
                              <div key={difficulty} className={complete ? "is-complete" : "is-needed"}>
                                <span className={`difficulty-chip difficulty-${difficulty}`}>{difficulty}</span>
                                <strong>{selectedDifficultyCounts[difficulty]} / {blueprintCounts[difficulty]}</strong>
                              </div>
                            );
                          })}
                        </div>
                        <div className="question-bank-pick-list">
                          {questionBankLoading ? (
                            <EmptyState label="Loading questions..." />
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
                                      {question.difficulty}
                                      {question.tags.length ? ` · ${question.tags.slice(0, 2).join(", ")}` : ""}
                                    </em>
                                  </span>
                                </label>
                              );
                            })
                          ) : (
                            <EmptyState label="No validated questions yet." />
                          )}
                        </div>
                      </div>
                    )}

                    <div className="questions-blueprint-and-selected">
                      {selectedQuestionIds.length ? (
                        <div className="selected-question-order">
                          <strong className="selected-pool-label">
                            Selected ({selectedQuestionIds.length})
                          </strong>
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
                                  <em>{question.difficulty}</em>
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
                              {blueprintMismatches.length} question
                              {blueprintMismatches.length > 1 ? "s don't" : " doesn't"} match the difficulty template.
                            </p>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  </div>
                      </section>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : null}

            {activeSection === "rules" ? (
              <div className="assessment-form-stack assessment-form-stack-rules assessment-form-pro assessment-create-form">
                <div className="assessment-form-section assessment-section-pro assessment-builder-page-card assessment-rules-panel">
                  <section className="rules-section-block">
                    <div className="rules-section-heading">
                      <h4>How scores are calculated</h4>
                      <p>
                        Split 100 points across test cases, code quality, and AI review. Use a
                        preset or enter your own weights.
                      </p>
                    </div>
                  <div className="scoring-preset-row" aria-label="Scoring presets">
                    {[
                      {
                        label: "Balanced",
                        detail: "40 / 30 / 30",
                        values: [40, 30, 30] as const,
                      },
                      {
                        label: "Test-heavy",
                        detail: "80 / 10 / 10",
                        values: [80, 10, 10] as const,
                      },
                      {
                        label: "Quality-heavy",
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
                        Test cases {requiredMark}
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
                        Code quality {requiredMark}
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
                        AI review {requiredMark}
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
                      Total: {scoringTotal}/100
                    </p>
                  </div>
                  </section>

                  <section className="rules-section-block">
                    <div className="rules-section-heading">
                      <h4>Proctoring policy</h4>
                      <p>Choose what restrictions candidates experience while taking the test.</p>
                    </div>
                  <div className="proctoring-option-grid" role="radiogroup" aria-label="Proctoring policy">
                    {PROCTORING_POLICY_OPTIONS.map((option) => (
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
                        role="radio"
                        aria-checked={assessmentForm.proctoring_mode === option.value}
                      >
                        <strong>{option.title}</strong>
                        <span>{option.summary}</span>
                        <ul>
                          {option.restrictions.map((restriction) => (
                            <li key={restriction}>{restriction}</li>
                          ))}
                        </ul>
                      </button>
                    ))}
                  </div>
                  </section>

                  <section className="rules-section-block">
                    <div className="rules-section-heading">
                      <h4>Allowed languages</h4>
                      <p>Select at least one language candidates can use in the code editor.</p>
                    </div>
                  <div className="assessment-inline-fields">
                    <label className="field field-pro">
                      <span>
                        Languages {requiredMark}
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
                  </section>

                  <section className="rules-section-block">
                    <div className="rules-section-heading">
                      <h4>Candidate experience</h4>
                      <p>Decide whether candidates can resume work during an open test slot.</p>
                    </div>
                  <div className="assessment-policy-grid assessment-policy-grid-single">
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
                        <strong>Allow candidates to Resume the Test</strong>
                        <em>
                          When enabled, candidates can leave and return before the slot closes.
                          When disabled, they get one uninterrupted attempt.
                        </em>
                      </span>
                    </label>
                  </div>
                  </section>
                </div>
              </div>
            ) : null}
            </div>

            <div className="assessment-builder-footer">
              <div className="assessment-builder-footer-copy">
                {createError ? <p className="form-error">{createError}</p> : null}
                <p className="assessment-builder-required-note">
                  Fields marked with {requiredMark} are mandatory.
                </p>
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
                    Continue
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
  onArchive,
  onDeleteAssessment,
  onUpdateAssessment,
  onSaveQuestions,
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
  onArchive: () => Promise<void>;
  onDeleteAssessment: () => Promise<void>;
  onUpdateAssessment: (payload: Partial<AssessmentCreatePayload>) => Promise<void>;
  onSaveQuestions: () => Promise<void>;
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
  const [pdfTrigger, setPdfTrigger] = useState(0);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [showArchiveConfirm, setShowArchiveConfirm] = useState(false);
  const [settingsTab, setSettingsTab] = useState<"details" | "rules" | "delete">("details");
  const [scheduleNowMs, setScheduleNowMs] = useState(() => Date.now());
  const [slotFieldErrors, setSlotFieldErrors] = useState({
    start_at: "",
    end_at: "",
    general: "",
  });
  const minimumSlotStart = nextAvailableTimeInput(
    slotForm.timezone_name,
    slotForm.timezone_offset_minutes,
    scheduleNowMs,
  );
  const minimumSlotEnd = minimumSlotEndInput(
    slotForm.start_at,
    slotForm.duration_minutes,
    slotForm.timezone_name,
    slotForm.timezone_offset_minutes,
    scheduleNowMs,
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
    setShowDetailsModal(false);
    setShowArchiveConfirm(false);
    setSettingsTab("details");
    setDeleteConfirmText("");
    setDetailSuccessMessage("");
    setSlotFieldErrors({ start_at: "", end_at: "", general: "" });
  }, [assessment.id]);

  useEffect(() => {
    setDetailSuccessMessage(successMessage);
  }, [successMessage]);

  useEffect(() => {
    if (!showCreateTest) {
      return;
    }
    const interval = window.setInterval(() => setScheduleNowMs(Date.now()), 30_000);
    return () => window.clearInterval(interval);
  }, [showCreateTest]);

  function openCreateTestModal() {
    const nowMs = Date.now();
    const defaults = createDefaultSlotSchedule(
      slotForm.timezone_name,
      slotForm.timezone_offset_minutes,
      slotForm.duration_minutes,
      nowMs,
    );
    const startAt = clampLocalInputToMinimum(slotForm.start_at, defaults.start_at) || defaults.start_at;
    const endAt =
      clampLocalInputToMinimum(slotForm.end_at, defaults.end_at) ||
      minimumSlotEndInput(
        startAt,
        slotForm.duration_minutes,
        slotForm.timezone_name,
        slotForm.timezone_offset_minutes,
        nowMs,
      );
    onChangeSlot({
      ...slotForm,
      start_at: startAt,
      end_at: endAt,
    });
    setSlotFieldErrors({ start_at: "", end_at: "", general: "" });
    setScheduleNowMs(nowMs);
    setShowCreateTest(true);
  }

  function updateSlotSchedule(
    patch: Partial<typeof slotForm>,
    currentForm: typeof slotForm = slotForm,
  ) {
    const nextForm = { ...currentForm, ...patch };
    const minimumStart = nextAvailableTimeInput(
      nextForm.timezone_name,
      nextForm.timezone_offset_minutes,
      scheduleNowMs,
    );
    const startAt = clampLocalInputToMinimum(nextForm.start_at, minimumStart) || minimumStart;
    const minimumEnd = minimumSlotEndInput(
      startAt,
      nextForm.duration_minutes,
      nextForm.timezone_name,
      nextForm.timezone_offset_minutes,
      scheduleNowMs,
    );
    const endAt =
      "end_at" in patch
        ? clampLocalInputToMinimum(nextForm.end_at, minimumEnd) || minimumEnd
        : "start_at" in patch || "duration_minutes" in patch
          ? minimumEnd
          : clampLocalInputToMinimum(nextForm.end_at, minimumEnd) || minimumEnd;
    const resolvedForm = {
      ...nextForm,
      start_at: startAt,
      end_at: endAt,
    };
    onChangeSlot(resolvedForm);
    setSlotFieldErrors(getSlotScheduleFieldErrors(resolvedForm, scheduleNowMs));
  }
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
    const fieldErrors = getSlotScheduleFieldErrors(slotForm, scheduleNowMs);
    setSlotFieldErrors(fieldErrors);
    if (fieldErrors.start_at || fieldErrors.end_at || fieldErrors.general) {
      return;
    }
    try {
      await onCreateSlot();
      setShowCreateTest(false);
      setSlotFieldErrors({ start_at: "", end_at: "", general: "" });
      setDetailSuccessMessage("Test slot created successfully.");
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

  async function confirmArchiveToggle() {
    setDetailSuccessMessage("");
    await onArchive();
    setShowArchiveConfirm(false);
    setDetailSuccessMessage(
      assessment.status === "archived"
        ? "Assessment restored successfully."
        : "Assessment archived successfully.",
    );
  }

  const isArchived = assessment.status === "archived";
  const archiveActionLabel = isArchived ? "Restore assessment" : "Archive assessment";
  const ArchiveActionIcon = isArchived ? ArchiveRestore : Archive;
  const detailsPanel = (
    <div className="assessment-detail-list assessment-details-modal-list">
      <div>
        <span>Duration</span>
        <strong>Configured per test slot</strong>
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
        <em>Unlimited checks, 5s cooldown</em>
      </div>
      <div>
        <span>Languages</span>
        <strong>{assessment.supported_languages.join(", ")}</strong>
      </div>
    </div>
  );

  return (
    <section className="assessment-drilldown">
      <div className="assessment-breadcrumb">
        <button type="button" onClick={onBack}>
          Back to assessments
        </button>
        <span>/</span>
        <strong>{assessment.title}</strong>
      </div>

      <Card className="assessment-panel assessment-command-center assessment-command-center-compact">
        <div className="assessment-command-title">
          <h2>{assessment.title}</h2>
          <p>{assessment.description || "No description added yet."}</p>
        </div>

        <div className="assessment-header-metrics" aria-label="Assessment summary">
          <div className="assessment-header-metric">
            <strong>{slots.length}</strong>
            <span>Test Slots</span>
          </div>
          <div className="assessment-header-metric">
            <strong>{totalCandidates}</strong>
            <span>Candidates</span>
          </div>
          <div className="assessment-header-metric">
            <strong>{totalSubmitted}</strong>
            <span>Submitted</span>
          </div>
          <div className="assessment-header-metric">
            <strong>
              {assessment.question_count_per_candidate || assessment.question_count}
            </strong>
            <span>Per candidate</span>
          </div>
        </div>

        <div className="assessment-row-actions">
          <StatusBadge value={assessment.status} />
          {detailMode === "analytics" && (
            <>
              <Button
                type="button"
                variant="secondary"
                disabled={evaluationBackfillPending}
                onClick={() => void onBackfillEvaluations()}
              >
                <Activity size={16} aria-hidden="true" />
                {evaluationBackfillPending ? "Evaluating..." : "Evaluate previous"}
              </Button>
              <Button
                type="button"
                onClick={() => setPdfTrigger((prev) => prev + 1)}
              >
                <Download size={16} aria-hidden="true" />
                Download Report
              </Button>
            </>
          )}
          <Button
            type="button"
            variant="secondary"
            className="icon-only-button"
            onClick={() => setShowDetailsModal(true)}
            title="Assessment details"
          >
            <Info size={18} />
            <span className="sr-only">Assessment details</span>
          </Button>
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
            onClick={() => setShowArchiveConfirm(true)}
            disabled={publishPending || !canArchive || assessmentUpdatePending}
            title={archiveActionLabel}
          >
            <ArchiveActionIcon size={18} />
            <span className="sr-only">{archiveActionLabel}</span>
          </Button>
        </div>
      </Card>

      {showDetailsModal ? (
        <div className="dialog-backdrop" onClick={() => setShowDetailsModal(false)}>
          <Card
            className="assessment-info-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="assessment-info-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="settings-modal-header">
              <div>
                <span>Details</span>
                <h2 id="assessment-info-title">Assessment information</h2>
              </div>
              <button
                type="button"
                className="modal-close-button"
                onClick={() => setShowDetailsModal(false)}
              >
                Close
              </button>
            </div>
            {detailsPanel}
          </Card>
        </div>
      ) : null}

      {showArchiveConfirm ? (
        <div className="dialog-backdrop" onClick={() => setShowArchiveConfirm(false)}>
          <div
            className="confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="archive-confirm-title"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id="archive-confirm-title">
              {isArchived ? "Restore assessment?" : "Archive assessment?"}
            </h3>
            <p>
              {isArchived
                ? "This assessment will be restored to the available list."
                : "This assessment will be retained but marked as archived."}
            </p>
            <div className="confirm-dialog-actions">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setShowArchiveConfirm(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={() => void confirmArchiveToggle()}
                disabled={assessmentUpdatePending}
              >
                {assessmentUpdatePending ? "Saving..." : archiveActionLabel}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="assessment-detail-tabs" role="tablist" aria-label="Assessment sections">
        <button
          type="button"
          role="tab"
          aria-selected={detailMode === "tests"}
          className={detailMode === "tests" ? "is-active" : ""}
          onClick={() => setDetailMode("tests")}
        >
          <ListChecks size={18} aria-hidden="true" />
          <strong>Test Slots</strong>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={detailMode === "questions"}
          className={detailMode === "questions" ? "is-active" : ""}
          onClick={() => setDetailMode("questions")}
        >
          <Code2 size={18} aria-hidden="true" />
          <strong>Questions</strong>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={detailMode === "analytics"}
          className={detailMode === "analytics" ? "is-active" : ""}
          onClick={() => setDetailMode("analytics")}
        >
          <BarChart3 size={18} aria-hidden="true" />
          <strong>Analytics</strong>
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
                { id: "delete", label: "Delete" },
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
                  <label className="field field-pro">
                    <span>Supported languages</span>
                    <div className="assessment-language-grid">
                      {ASSESSMENT_LANGUAGES.map((language) => {
                        const selected =
                          assessmentEditForm.supported_languages.includes(language);
                        return (
                          <label
                            key={language}
                            className={`language-option ${selected ? "is-selected" : ""}`}
                          >
                            <input
                              type="checkbox"
                              className="language-option-input"
                              checked={selected}
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
                    Allow candidates to Resume the Test
                  </label>
                </div>
              </div>
            ) : null}

            {settingsTab === "delete" ? (
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

            {settingsTab !== "delete" ? (
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
              <div className="assessment-tests-toolbar">
                <Button
                  type="button"
                  onClick={openCreateTestModal}
                >
                  Create New Test Slot
                </Button>
              </div>

              {slotsLoading ? <EmptyState label="Loading test slots..." /> : null}
              {!slotsLoading && slots.length ? (
                <div className="test-card-grid">
                  {slots.map((slot) => {
                    const submittedPercent = Math.round(
                      (slot.submitted_count / Math.max(slot.candidate_count, 1)) * 100,
                    );
                    return (
                      <Link
                        key={slot.id}
                        className="test-summary-card"
                        to={assessmentTestPath(assessment.id, slot.id, assessment.title, slot.title)}
                      >
                        <span className="test-card-icon">
                          <Clock3 size={18} aria-hidden="true" />
                        </span>
                        <div className="test-card-primary">
                          <span className="test-card-kind">Test Slot</span>
                          <strong>{slot.title}</strong>
                          <span>
                            {formatDateTime(slot.start_at)} to {formatDateTime(slot.end_at)}
                          </span>
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
                          <span className="test-card-completion">
                            <strong>{submittedPercent}%</strong>
                            Completion
                            <i className="test-card-progress" aria-hidden="true">
                              <b style={{ width: `${submittedPercent}%` }} />
                            </i>
                          </span>
                        </div>
                        <div className="test-card-status">
                          <div className="status-with-dot">
                            <HealthDot status={slot.effective_status} />
                            <StatusBadge value={slot.effective_status} />
                          </div>
                          <small>
                            {slot.status === slot.effective_status
                              ? "Schedule current"
                              : `Configured as ${slot.status}`}
                          </small>
                        </div>
                        <span className="test-card-open" aria-hidden="true">
                          <ChevronRight size={20} />
                        </span>
                      </Link>
                    );
                  })}
                </div>
              ) : null}
              {!slotsLoading && !slots.length ? (
                <EmptyState label="No test slots scheduled yet. Create a test slot for the first candidate batch." />
              ) : null}
            </Card>

            {showCreateTest ? (
              <div
                className="modal-backdrop test-create-backdrop"
                role="presentation"
                onMouseDown={(event) => {
                  if (event.target === event.currentTarget && !slotPending) {
                    setShowCreateTest(false);
                  }
                }}
              >
                <Card
                  className="assessment-panel action-drawer-card test-create-dialog"
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="create-test-title"
                  onMouseDown={(event) => event.stopPropagation()}
                >
                  <div className="panel-heading">
                    <div>
                      <span>New Test Slot</span>
                      <h2 id="create-test-title">Schedule Candidate Batch</h2>
                      <p>Create a test slot for this assessment's saved question set.</p>
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setShowCreateTest(false)}
                      disabled={slotPending}
                    >
                      Close
                    </Button>
                  </div>
                  <div className="assessment-form-stack">
                    {slotError ||
                    slotFieldErrors.general ||
                    slotFieldErrors.start_at ||
                    slotFieldErrors.end_at ? (
                      <div className="slot-schedule-inline-alert" role="status">
                        <Info size={18} aria-hidden="true" />
                        <div>
                          <strong>Adjust the schedule below</strong>
                          <p>
                            {slotFieldErrors.general ||
                              slotError ||
                              "Choose a future start and end time. This form stays open while you fix it."}
                          </p>
                        </div>
                      </div>
                    ) : null}
                    <label className="field">
                      <span>Test slot title</span>
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
                            updateSlotSchedule({
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
                      <ScheduleDateTimePicker
                        label="Start time"
                        value={slotForm.start_at}
                        min={minimumSlotStart}
                        error={slotFieldErrors.start_at}
                        onChange={(startAt) => updateSlotSchedule({ start_at: startAt })}
                      />
                    </div>
                    <p className="assessment-context-banner">
                      Times use {slotForm.timezone_name}. Past times are disabled in the picker.
                      Earliest start: {minimumSlotStart.replace("T", " ")}.
                    </p>
                    <div className="assessment-inline-fields">
                      <label className="field">
                        <span>Test slot duration (minutes)</span>
                        <input
                          type="number"
                          min={15}
                          max={360}
                          value={slotForm.duration_minutes}
                          onChange={(event) => {
                            const duration = Math.max(15, Number(event.target.value) || 15);
                            updateSlotSchedule({ duration_minutes: duration });
                          }}
                        />
                      </label>
                      <div className="field">
                        <ScheduleDateTimePicker
                          label="End time"
                          value={slotForm.end_at}
                          min={minimumSlotEnd}
                          error={slotFieldErrors.end_at}
                          onChange={(endAt) => updateSlotSchedule({ end_at: endAt })}
                        />
                      </div>
                    </div>
                    <label className="field">
                      <span>Batch instructions override</span>
                      <textarea
                        placeholder="Optional instructions only for this test slot"
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
                        {slotPending ? "Creating..." : "Create New Test Slot"}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => setShowCreateTest(false)}
                        disabled={slotPending}
                      >
                        Cancel
                      </Button>
                    </div>
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
            pdfTrigger={pdfTrigger}
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
  error,
  publishError,
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
    supported_languages?: string[];
  }>;
  selectedQuestions: Record<string, AssessmentQuestionAssignment>;
  pending: boolean;
  assessmentUpdatePending: boolean;
  error: string;
  publishError: string;
  onSave: () => Promise<void>;
  onUpdateAssessment: (payload: Partial<AssessmentCreatePayload>) => Promise<void>;
  onUpdateSelection: (
    updater: (
      current: Record<string, AssessmentQuestionAssignment>,
    ) => Record<string, AssessmentQuestionAssignment>,
  ) => void;
}) {
  const [showTemplateDialog, setShowTemplateDialog] = useState(false);
  const [panelWarning, setPanelWarning] = useState("");
  const [hasTemplateDraft, setHasTemplateDraft] = useState(false);
  const [templateEditorStep, setTemplateEditorStep] = useState<QuestionSetupStep>(1);
  const [templateDraft, setTemplateDraft] = useState<DifficultyLevel[]>(
    assessment.difficulty_blueprint?.length
      ? assessment.difficulty_blueprint
      : createQuestionBlueprint(assessment.question_count_per_candidate || 1),
  );
  const [templateShuffleDraft, setTemplateShuffleDraft] = useState(assessment.shuffle_questions);
  const [templateCountDraft, setTemplateCountDraft] = useState(assessment.question_count_per_candidate || 1);
  const [templateQuestionsDraft, setTemplateQuestionsDraft] = useState<string[]>([]);

  function openEditTemplate() {
    setTemplateDraft(
      assessment.difficulty_blueprint?.length
        ? [...assessment.difficulty_blueprint]
        : createQuestionBlueprint(assessment.question_count_per_candidate || 1)
    );
    setTemplateCountDraft(assessment.question_count_per_candidate || 1);
    setTemplateShuffleDraft(assessment.shuffle_questions);

    const initialQuestions: string[] = [];
    const currentSelected = Object.values(selectedQuestions)
      .sort((left, right) => left.question_order - right.question_order);

    const activeCount = assessment.question_count_per_candidate || 1;
    for (let i = 0; i < activeCount; i++) {
      initialQuestions.push(currentSelected[i]?.question_id || "");
    }
    setTemplateQuestionsDraft(initialQuestions);

    setTemplateEditorStep(1);
    setShowTemplateDialog(true);
  }

  function updateTemplateCount(newCount: number) {
    const count = Math.max(1, Math.min(50, newCount));
    setTemplateCountDraft(count);
    setTemplateDraft((current) => {
      if (current.length === count) return current;
      if (current.length < count) {
        return [...current, ...Array<DifficultyLevel>(count - current.length).fill("easy")];
      }
      return current.slice(0, count);
    });
    setTemplateQuestionsDraft((current) => {
      if (current.length === count) return current;
      if (current.length < count) {
        return [...current, ...Array<string>(count - current.length).fill("")];
      }
      return current.slice(0, count);
    });
  }

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
        shuffle_questions: templateShuffleDraft,
      });
    }
    await onSave();
    setHasTemplateDraft(false);
    setShowTemplateDialog(false);
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
  const activeShuffleQuestions = hasTemplateDraft ? templateShuffleDraft : assessment.shuffle_questions;
  const selectionReady = activeShuffleQuestions
    ? selectedRows.length >= activeBlueprint.length && minimumRequirementsMet && allSelectedInTemplate
    : orderedSelectionMatches;
  const draftTemplateMarks = calculateQuestionTemplateMarks(templateDraft);
  const draftRequiredCounts = templateDraft.reduce<Record<DifficultyLevel, number>>(
    (counts, difficulty) => ({ ...counts, [difficulty]: counts[difficulty] + 1 }),
    { easy: 0, medium: 0, hard: 0 },
  );
  const draftSelectedRows = templateQuestionsDraft.map((qId) => {
    const q = questionBank.find((item) => item.id === qId);
    return {
      difficulty: q?.difficulty || "unknown",
    };
  });

  const draftSelectedCounts = draftSelectedRows.reduce<Record<DifficultyLevel, number>>(
    (counts, row) => {
      if (!QUESTION_DIFFICULTIES.includes(row.difficulty as DifficultyLevel)) return counts;
      const difficulty = row.difficulty as DifficultyLevel;
      return { ...counts, [difficulty]: counts[difficulty] + 1 };
    },
    { easy: 0, medium: 0, hard: 0 },
  );
  const draftMinimumRequirementsMet = QUESTION_DIFFICULTIES.every(
    (difficulty) => draftSelectedCounts[difficulty] >= draftRequiredCounts[difficulty],
  );
  const draftAllSelectedInTemplate = draftSelectedRows.every((row) =>
    templateDraft.includes(row.difficulty as DifficultyLevel),
  );
  const draftOrderedSelectionMatches = draftSelectedRows.length === templateDraft.length &&
    draftSelectedRows.every((row, index) => row.difficulty === templateDraft[index]);
  const draftSelectionReady = templateShuffleDraft
    ? draftSelectedRows.length >= templateDraft.length && draftMinimumRequirementsMet && draftAllSelectedInTemplate
    : draftOrderedSelectionMatches;

  const allSlotsHaveQuestions = templateQuestionsDraft.length === templateCountDraft &&
    templateQuestionsDraft.every((qId) => qId !== "");

  function marksForDifficulty(difficulty: string) {
    const values = templateMarks.filter((_, index) => activeBlueprint[index] === difficulty);
    if (!values.length) return "Not in template";
    const unique = Array.from(new Set(values));
    return unique.length === 1 ? `${unique[0]} marks` : `${Math.min(...unique)}-${Math.max(...unique)} marks`;
  }

  function renderTemplateQuotaCards(
    blueprint: DifficultyLevel[],
    marks: number[],
    requiredCounts: Record<DifficultyLevel, number>,
    selectedCounts: Record<DifficultyLevel, number>,
    shuffleQuestions: boolean,
  ) {
    return (
      <div className="template-quota-grid">
        {QUESTION_DIFFICULTIES.filter((difficulty) => requiredCounts[difficulty] > 0).map(
          (difficulty) => {
            const complete = selectedCounts[difficulty] >= requiredCounts[difficulty];
            const markLabel = marksSummaryForDifficulty(difficulty, blueprint, marks);
            return (
              <div
                key={difficulty}
                className={`template-quota-card ${complete ? "is-complete" : "is-needed"}`}
              >
                <div className="template-quota-card-top">
                  <span className={`difficulty-chip difficulty-${difficulty}`}>
                    {difficulty}
                  </span>
                  <strong>
                    {selectedCounts[difficulty]} / {requiredCounts[difficulty]}
                  </strong>
                </div>
                <div className="template-quota-card-details">
                  {markLabel ? <span>{markLabel}</span> : null}
                  <span>{shuffleQuestions ? "Random pool" : "Fixed order"}</span>
                  <span>{complete ? "Complete" : `${requiredCounts[difficulty] - selectedCounts[difficulty]} more`}</span>
                </div>
              </div>
            );
          },
        )}
      </div>
    );
  }

  return (
    <Card className="assessment-panel question-management-panel">
      {panelWarning ? (
        <ToastNotification
          title="Question set warning"
          message={panelWarning}
          tone="warning"
          onClose={() => setPanelWarning("")}
        />
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
            onClick={openEditTemplate}
          >
            Edit Template
          </Button>
        </div>
      </div>

      <div className="template-requirements-panel template-requirements-panel-compact">
        <div className="template-requirements-chips">
          <span>{activeShuffleQuestions ? "Randomized" : "Fixed set"}</span>
          <span>{activeBlueprint.length} questions</span>
          <span>100 marks</span>
        </div>
        {renderTemplateQuotaCards(
          activeBlueprint,
          templateMarks,
          requiredCounts,
          selectedCounts,
          activeShuffleQuestions,
        )}
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
                <strong className="question-title-static" style={{ fontSize: "15px", color: "#0f172a" }}>
                  {row.title}
                </strong>
                <div className="selected-question-metadata">
                  <span className={`difficulty-chip difficulty-${row.difficulty}`}>
                    {row.difficulty}
                  </span>
                  {row.tags.length > 0 ? (
                    <div className="meta-pills">
                      {row.tags.slice(0, 3).map((tag) => (
                        <span key={tag} className="tag-pill">{tag}</span>
                      ))}
                    </div>
                  ) : null}
                  {row.supportedLanguages.length > 0 ? (
                    <div className="meta-pills">
                      {row.supportedLanguages.slice(0, 5).map((language) => (
                        <span key={language} className="lang-pill">{language}</span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="selected-question-side">
                <span className="template-weight-value">
                  {assessment.shuffle_questions
                    ? marksForDifficulty(row.difficulty)
                    : `${templateMarks[row.selection.question_order - 1] || 0} marks`}
                </span>
              </div>
            </div>
          ))
        ) : (
          <EmptyState label="No questions selected yet. Add questions from the bank to make this assessment attendable." />
        )}
      </div>


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
                <span>Assessment Template</span>
                <h2>Edit question template</h2>
              </div>
              <div className="assessment-row-actions">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    setShowTemplateDialog(false);
                  }}
                >
                  Close
                </Button>
              </div>
            </div>

            <div className="question-setup-tabs question-template-editor-tabs" role="tablist" aria-label="Template editor steps">
              {[
                { step: 1 as const, label: "Question count", meta: `${templateCountDraft} required`, complete: templateDraft.length === templateCountDraft },
                { step: 2 as const, label: "Difficulties", meta: `${templateDraft.length} slots`, complete: templateDraft.length === templateCountDraft },
                { step: 3 as const, label: "Delivery", meta: templateShuffleDraft ? "Randomized" : "Fixed set", complete: true },
                { step: 4 as const, label: "Pool check", meta: `${selectedRows.length} selected`, complete: draftSelectionReady },
              ].map((item) => (
                <button
                  key={item.step}
                  type="button"
                  role="tab"
                  aria-selected={templateEditorStep === item.step}
                  className={`${item.complete ? "is-complete" : "is-needed"} ${templateEditorStep === item.step ? "is-active" : ""}`}
                  onClick={() => setTemplateEditorStep(item.step)}
                >
                  <span>{item.complete ? "✓" : item.step}</span>
                  <strong>{item.label}</strong>
                  <small>{item.complete ? "Ready" : item.meta}</small>
                </button>
              ))}
            </div>

            <div className="question-setup-flow question-template-editor-flow">
              <section className={`question-setup-card is-visible ${templateEditorStep === 1 ? "is-current" : ""} ${templateDraft.length === templateCountDraft ? "is-complete" : ""}`}>
                <div className="question-setup-card-heading">
                  <span>1</span>
                  <div>
                    <strong>How many questions should each candidate receive?</strong>
                    <p>This rebuilds the editable difficulty slots and keeps the assessment requirement clear.</p>
                  </div>
                </div>
                <div className="question-count-control">
                  <label className="field field-pro metric-field">
                    <span>Questions per candidate</span>
                    <input
                      type="number"
                      min={1}
                      max={50}
                      value={templateCountDraft}
                      onChange={(event) => updateTemplateCount(Number(event.target.value))}
                    />
                  </label>
                  <Button type="button" onClick={() => setTemplateEditorStep(2)}>
                    Continue to difficulties
                  </Button>
                </div>
              </section>

              <section className={`question-setup-card is-visible ${templateEditorStep === 2 ? "is-current" : ""} ${templateDraft.length === templateCountDraft ? "is-complete" : ""}`}>
                <div className="question-setup-card-heading">
                  <span>2</span>
                  <div>
                    <strong>Choose the difficulty for every question slot</strong>
                    <p>Marks are calculated automatically from difficulty weightage: easy 1, medium 2, hard 3.</p>
                  </div>
                </div>
                <div className="difficulty-slot-grid question-setup-difficulty-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
                  {templateDraft.map((difficulty, index) => (
                    <div key={`edit-template-${index}`} className="difficulty-slot-card" style={{ display: "grid", gap: "8px", padding: "12px", background: "#ffffff", border: "1px solid #dbe4f0", borderRadius: "12px" }}>
                      <label style={{ display: "grid", gap: "4px" }}>
                        <span style={{ color: "#64748b", fontSize: "11px", fontWeight: 900, textTransform: "uppercase" }}>Slot {index + 1} Difficulty · {draftTemplateMarks[index]} marks</span>
                        <select
                          value={difficulty}
                          onChange={(event) => {
                            const newDifficulty = event.target.value as DifficultyLevel;
                            setTemplateDraft((current) => current.map((item, itemIndex) =>
                              itemIndex === index ? newDifficulty : item,
                            ));
                            setTemplateQuestionsDraft((current) => current.map((qId, itemIndex) =>
                              itemIndex === index ? "" : qId
                            ));
                          }}
                          style={{ background: "#ffffff", border: "1px solid #dbe4f0", borderRadius: "8px", minHeight: "34px", padding: "0 8px", textTransform: "capitalize" }}
                        >
                          {QUESTION_DIFFICULTIES.map((item) => <option key={item} value={item}>{item}</option>)}
                        </select>
                      </label>
                      <label style={{ display: "grid", gap: "4px" }}>
                        <span style={{ color: "#64748b", fontSize: "11px", fontWeight: 900, textTransform: "uppercase" }}>Assigned Question</span>
                        <select
                          value={templateQuestionsDraft[index] || ""}
                          onChange={(event) => {
                            const val = event.target.value;
                            setTemplateQuestionsDraft((current) => current.map((qId, itemIndex) =>
                              itemIndex === index ? val : qId
                            ));
                          }}
                          style={{ background: "#ffffff", border: "1px solid #dbe4f0", borderRadius: "8px", minHeight: "34px", padding: "0 8px" }}
                        >
                          <option value="">-- Select Question --</option>
                          {questionBank
                            .filter((q) => q.difficulty === difficulty)
                            .map((q) => {
                              const isUsed = templateQuestionsDraft.some((qId, qIndex) => qId === q.id && qIndex !== index);
                              return (
                                <option key={q.id} value={q.id} disabled={isUsed}>
                                  {q.title} {isUsed ? "(selected in another slot)" : ""}
                                </option>
                              );
                            })}
                        </select>
                      </label>
                    </div>
                  ))}
                </div>
                <div className="question-setup-card-actions">
                  <Button type="button" onClick={() => setTemplateEditorStep(3)}>
                    Continue to delivery
                  </Button>
                </div>
              </section>

              <section className={`question-setup-card is-visible is-complete ${templateEditorStep === 3 ? "is-current" : ""}`}>
                <div className="question-setup-card-heading">
                  <span>3</span>
                  <div>
                    <strong>How should questions be delivered?</strong>
                    <p>Use a fixed set for identical test slots or a randomized pool when candidates can receive different matching questions.</p>
                  </div>
                </div>
                <div className="question-delivery-toggle" role="group" aria-label="Question delivery mode">
                  <button
                    type="button"
                    className={!templateShuffleDraft ? "is-active" : ""}
                    onClick={() => {
                      setTemplateShuffleDraft(false);
                      setTemplateEditorStep(4);
                    }}
                  >
                    <strong>Fixed set</strong>
                    <span>Everyone receives the same {templateDraft.length} questions in blueprint order.</span>
                  </button>
                  <button
                    type="button"
                    className={templateShuffleDraft ? "is-active" : ""}
                    onClick={() => {
                      setTemplateShuffleDraft(true);
                      setTemplateEditorStep(4);
                    }}
                  >
                    <strong>Randomized pool</strong>
                    <span>Each candidate receives {templateDraft.length} matching questions from the selected pool.</span>
                  </button>
                </div>
              </section>

              <section className={`question-setup-card is-visible ${templateEditorStep === 4 ? "is-current" : ""} ${draftSelectionReady ? "is-complete" : ""}`}>
                <div className="question-setup-card-heading">
                  <span>4</span>
                  <div>
                    <strong>Review how the current question pool matches this template</strong>
                    <p>Apply the template here, then adjust the selected questions below the modal if the pool needs changes.</p>
                  </div>
                </div>
                <div className="question-template-editor-summary template-requirements-panel-compact">
                  <div className="template-requirements-chips">
                    <span>{templateShuffleDraft ? "Randomized" : "Fixed set"}</span>
                    <span>{templateDraft.length} questions</span>
                    <span>{templateQuestionsDraft.filter(Boolean).length} selected</span>
                  </div>
                  {renderTemplateQuotaCards(
                    templateDraft,
                    draftTemplateMarks,
                    draftRequiredCounts,
                    draftSelectedCounts,
                    templateShuffleDraft,
                  )}
                </div>
              </section>
            </div>

            <div className="confirm-dialog-actions">
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setShowTemplateDialog(false);
                }}
              >
                Cancel
              </Button>
              <Button
                type="button"
                disabled={!allSlotsHaveQuestions}
                onClick={() => {
                  const nextSelection: Record<string, AssessmentQuestionAssignment> = {};
                  templateQuestionsDraft.forEach((qId, index) => {
                    if (qId) {
                      nextSelection[qId] = {
                        question_id: qId,
                        question_order: index + 1,
                        marks: draftTemplateMarks[index],
                        is_mandatory: true,
                      };
                    }
                  });
                  onUpdateSelection(() => nextSelection);
                  setHasTemplateDraft(true);
                  setShowTemplateDialog(false);
                }}
              >
                Apply Changes
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
