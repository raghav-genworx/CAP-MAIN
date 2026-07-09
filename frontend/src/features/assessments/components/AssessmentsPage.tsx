import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileText,
  Play,
  Plus,
  Redo2,
  Save,
  Sparkles,
  Trash2,
  Undo2,
  Wand2,
  X,
} from "lucide-react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { useAuth } from "../../auth";
import { AgentRunOverlay, StepCard } from "./QuestionBuilderPanels";
import {
  useBulkImportQuestionBankQuestions,
  useCreateQuestionGroup,
  useCreateQuestionBankQuestion,
  useDeleteQuestionBankQuestion,
  useQuestionBank,
  useQuestionGroups,
  useRefineQuestionBankSolution,
  useRefineQuestionBankTestCases,
  useStreamQuestionBankDraft,
  useUpdateQuestionGroup,
  useUpdateQuestionBankQuestion,
  useValidateQuestionBankDraft,
} from "../hooks/useQuestionBank";
import type {
  AnswerValidationMode,
  DifficultyLevel,
  QuestionBulkImportResponse,
  QuestionCreatePayload,
  QuestionDraftRefinementResponse,
  QuestionAIDraftProgressEvent,
  QuestionAIDraftResponse,
  QuestionGroupRecord,
  QuestionGroupStatus,
  QuestionRecord,
  QuestionStatus,
  QuestionVisibility,
  ReferenceSolutionArtifact,
  SolutionValidationReport,
  SolutionValidationCaseResult,
  TestCase,
  ValidationStatus,
} from "../types/QuestionBank";
import { languageDisplayName } from "../utils/questionLanguage";
import {
  appendQuestionGenerationProgress,
  clearQuestionGenerationSession,
  completeQuestionGenerationSession,
  failQuestionGenerationSession,
  getQuestionGenerationSession,
  startQuestionGenerationSession,
  subscribeQuestionGenerationSession,
  type QuestionGenerationSettingsSnapshot,
} from "../services/questionGenerationSession";

type DashboardView = "questions" | "groups";
type GroupSideTab = "selected" | "groups";
type WizardStep = 1 | 2 | 3 | 4 | 5 | 6;
type DraftScope =
  | "full"
  | "basics"
  | "problem"
  | "problem_field"
  | "constraints"
  | "constraints_formats"
  | "examples"
  | "tests"
  | "tests_solution"
  | "solution"
  | "other_languages"
  | "recruiter_validation"
  | "difficulty"
  | "metadata";
type BusyScope = DraftScope | "validation";

type GenerationSettingsState = QuestionGenerationSettingsSnapshot;

interface ActivityEntry {
  label: string;
  detail: string;
  tone: "info" | "success" | "warning" | "error";
  timestamp: string;
}

interface StepDefinition {
  id: WizardStep;
  title: string;
  required: string[];
  optional: string[];
  actionLabel: string;
}

interface AiPromptRequest {
  scope: DraftScope;
  prompt: string;
}

interface AiPromptCopy {
  eyebrow: string;
  title: string;
  question: string;
  placeholder: string;
  helper: string;
  actionLabel: string;
}

type TestBucket = "sample_test_cases" | "hidden_test_cases";
type ValidationBucket = "sample" | "hidden";

interface TestCaseEditorState {
  bucket: TestBucket;
  index: number;
  draft: TestCase;
  originalResult: SolutionValidationCaseResult | null;
  undoStack: TestCase[];
  redoStack: TestCase[];
}

interface PromptContextSource {
  label: string;
  value: string;
  ready: boolean;
}

type FieldToastTone = "warning" | "error";

interface FieldToast {
  id: number;
  message: string;
  tone: FieldToastTone;
}

function fieldToastTitle(toast: FieldToast) {
  for (const title of [
    "Security alert",
    "Safety alert",
    "Data sanitation alert",
  ]) {
    if (toast.message.includes(`${title}:`)) {
      return title;
    }
  }
  return toast.tone === "error" ? "Error" : "Check this";
}

interface LanguageGenerationOptions {
  baseDraft?: QuestionCreatePayload;
  requestedLanguages?: string[];
  progressStart?: number;
  progressSpan?: number;
  appendFinalCompleteEvent?: boolean;
  signal?: AbortSignal;
}

const AVAILABLE_LANGUAGES = ["python", "java", "cpp", "c"] as const;
const ANSWER_VALIDATION_OPTIONS: Array<{
  value: AnswerValidationMode;
  label: string;
  detail: string;
}> = [
  {
    value: "exact",
    label: "Exact output",
    detail: "Candidate output must match the expected output after safe whitespace normalization.",
  },
  {
    value: "unordered",
    label: "Unordered tokens",
    detail: "The same whitespace-separated tokens may appear in any order.",
  },
  {
    value: "floating",
    label: "Floating tolerance",
    detail: "Numeric outputs are accepted within a small tolerance.",
  },
  {
    value: "multiple_valid",
    label: "Multiple valid answers",
    detail: "A custom checker accepts any output that satisfies the testcase.",
  },
  {
    value: "constructive",
    label: "Constructive checker",
    detail: "A custom checker validates any constructed answer against the rules.",
  },
];
const BULK_IMPORT_COLUMNS = [
  "title",
  "problem_statement",
  "difficulty",
  "topics",
  "tags",
  "category",
  "constraints",
  "input_format",
  "input_explanation",
  "output_format",
  "output_explanation",
  "sample_test_cases",
  "hidden_test_cases",
  "reference_solution",
  "reference_language",
  "supported_languages",
  "answer_validation_mode",
  "output_checker",
  "output_checker_explanation",
  "execution_time_limit_seconds",
  "memory_limit_mb",
  "metadata_status",
  "validation_status",
  "solution_approach",
  "time_complexity",
  "space_complexity",
  "status",
] as const;
const STEP_DEFINITIONS: StepDefinition[] = [
  {
    id: 1,
    title: "Basic Details",
    required: ["Title", "Context", "Languages", "Test counts"],
    optional: [],
    actionLabel: "Generate Full Question Draft",
  },
  {
    id: 2,
    title: "Problem & Constraints",
    required: ["Problem", "Formats", "Constraints"],
    optional: ["Generate sections separately"],
    actionLabel: "Generate Problem Statement",
  },
  {
    id: 3,
    title: "Tests, Solution & Validation",
    required: ["Exact test counts", "Reference solution", "Passing validation"],
    optional: ["Run all or one case"],
    actionLabel: "Generate Tests & Solution",
  },
  {
    id: 4,
    title: "Other Language Solutions",
    required: ["Validated translations"],
    optional: ["Skip when one language"],
    actionLabel: "Generate Other Languages",
  },
  {
    id: 5,
    title: "Metadata & Preview",
    required: ["AI classification", "Preview"],
    optional: [],
    actionLabel: "Classify Difficulty & Metadata",
  },
  {
    id: 6,
    title: "Review & Publish",
    required: ["Full review", "Status confirmation"],
    optional: [],
    actionLabel: "Create Question",
  },
];

function createEmptyTestCase(isSample = false): TestCase {
  return { input: "", expected_output: "", is_sample: isSample, explanation: "" };
}

function answerValidationOption(mode: AnswerValidationMode) {
  return (
    ANSWER_VALIDATION_OPTIONS.find((option) => option.value === mode) ??
    ANSWER_VALIDATION_OPTIONS[0]
  );
}

function answerValidationNeedsCustomChecker(mode: AnswerValidationMode) {
  return mode === "multiple_valid" || mode === "constructive";
}

function answerValidationDescription(composer: QuestionCreatePayload) {
  return (
    composer.output_checker_explanation.trim() ||
    answerValidationOption(composer.answer_validation_mode).detail
  );
}

function createEmptyComposer(): QuestionCreatePayload {
  return {
    title: "",
    problem_statement: "",
    difficulty: "medium",
    topics: [],
    tags: [],
    category: "",
    constraints: "",
    input_format: "",
    input_explanation: "",
    output_format: "",
    output_explanation: "",
    sample_test_cases: [createEmptyTestCase(true)],
    hidden_test_cases: [createEmptyTestCase(false)],
    reference_solution: "",
    reference_language: "python",
    supported_languages: ["python"],
    candidate_solve_time_minutes: 45,
    execution_time_limit_seconds: 2,
    memory_limit_mb: 256,
    metadata_status: "pending",
    difficulty_source: "legacy",
    validation_report: null,
    validation_status: "not_run",
    validation_updated_at: null,
    reference_solutions: {},
    answer_validation_mode: "exact",
    output_checker: "",
    output_checker_explanation: answerValidationOption("exact").detail,
    solution_approach: "",
    time_complexity: "",
    space_complexity: "",
    status: "draft",
    creation_mode: "manual",
    visibility: "private",
  };
}

function createEmptyGenerationSettings(): GenerationSettingsState {
  return {
    question_count: 1,
    easy_count: 0,
    medium_count: 0,
    hard_count: 1,
    topics_text: "",
    interview_style: "DSA interview",
    company_style: "Enterprise",
    time_limit_minutes: 45,
    candidate_solve_time_minutes: 45,
    execution_time_limit_seconds: 2,
    memory_limit_mb: 256,
    sample_test_case_count: 3,
    hidden_test_case_count: 10,
    edge_case_count: 4,
    stress_test_count: 2,
  };
}

function createTimelineEntry(
  label: string,
  detail: string,
  tone: ActivityEntry["tone"],
): ActivityEntry {
  return {
    label,
    detail,
    tone,
    timestamp: new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
  };
}

function buildSingleTestResultMap(
  report: SolutionValidationReport | null | undefined,
): Record<string, SolutionValidationCaseResult> {
  if (!report) {
    return {};
  }

  return Object.fromEntries(
    report.results.map((result) => [
      `${result.bucket === "sample" ? "sample_test_cases" : "hidden_test_cases"}-${result.index - 1}`,
      result,
    ]),
  );
}

function splitList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function escapeCsvValue(value: string) {
  const normalized = value.replace(/\r\n/g, "\n");
  if (/[",\n]/.test(normalized)) {
    return `"${normalized.replace(/"/g, '""')}"`;
  }
  return normalized;
}

function buildBulkImportTemplate() {
  const row: Record<(typeof BULK_IMPORT_COLUMNS)[number], string> = {
    title: "Voting Eligibility",
    problem_statement:
      "Write a program that reads an age and prints Eligible if the age is 18 or more, otherwise print Not Eligible.",
    difficulty: "easy",
    topics: "conditionals,beginners",
    tags: "conditionals,beginners",
    category: "beginner control flow",
    constraints: "0 <= age <= 120",
    input_format: "A single integer age.",
    input_explanation: "The integer represents the candidate's age in years.",
    output_format: "Print Eligible or Not Eligible.",
    output_explanation:
      "Print Eligible when age is at least 18; otherwise print Not Eligible.",
    sample_test_cases: JSON.stringify([
      {
        input: "18\n",
        expected_output: "Eligible\n",
        is_sample: true,
        explanation: "18 is the minimum eligible age.",
      },
    ]),
    hidden_test_cases: JSON.stringify([
      {
        input: "17\n",
        expected_output: "Not Eligible\n",
        is_sample: false,
        explanation: "17 is below the minimum voting age.",
      },
    ]),
    reference_solution:
      'def solve(raw_input: str) -> str:\n    age = int(raw_input)\n    return "Eligible" if age >= 18 else "Not Eligible"\n\nif __name__ == "__main__":\n    import sys\n    print(solve(sys.stdin.read()))',
    reference_language: "python",
    supported_languages: "python",
    answer_validation_mode: "exact",
    output_checker: "",
    output_checker_explanation:
      "Candidate output must match the expected output exactly after safe whitespace normalization.",
    execution_time_limit_seconds: "2",
    memory_limit_mb: "128",
    metadata_status: "classified",
    validation_status: "not_run",
    solution_approach: "Read the age and compare it with 18 using if/else.",
    time_complexity: "O(1)",
    space_complexity: "O(1)",
    status: "draft",
  };

  return [
    BULK_IMPORT_COLUMNS.join(","),
    BULK_IMPORT_COLUMNS.map((column) => escapeCsvValue(row[column])).join(","),
  ].join("\n");
}

function downloadBulkImportTemplate() {
  const blob = new Blob([buildBulkImportTemplate()], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "question-bank-bulk-import-template.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function buildAgentThinkingLines(scope: BusyScope): string[] {
  if (scope === "full") {
    return [
      "Thinking through the recruiter prompt",
      "Generating the problem statement",
      "Creating constraints and sample tests",
      "Generating hidden test cases",
      "Writing and validating the reference solution",
      "Classifying difficulty, tags, and metadata",
    ];
  }

  if (scope === "problem" || scope === "problem_field") {
    return [
      "Reading the title and existing context",
      "Generating the problem statement",
      "Building input/output formats and constraints",
      "Reviewing the section before applying it",
    ];
  }

  if (scope === "constraints" || scope === "constraints_formats") {
    return [
      "Reading the problem statement",
      "Generating formats, explanations, and constraints",
      "Checking limits against the requested counts",
      "Updating the constraint section",
    ];
  }

  if (scope === "tests_solution") {
    return [
      "Reading the statement and constraints",
      "Generating exact-count sample and hidden tests",
      "Generating the primary reference solution",
      "Running the adversarial repair loop",
      "Replacing wrong outputs or code before applying results",
    ];
  }

  if (scope === "tests" || scope === "examples") {
    return [
      "Reading the statement and constraints",
      "Generating exact-count sample and hidden tests",
      "Checking generated inputs against constraints",
      "Applying the accepted testcase set",
    ];
  }

  if (scope === "solution") {
    return [
      "Reading the tests and constraints",
      "Generating a runnable reference solution",
      "Checking the code contract",
      "Applying solution code for execution",
    ];
  }

  if (scope === "other_languages") {
    return [
      "Reading the validated testcase set",
      "Translating the accepted solution",
      "Validating each requested language",
      "Preparing language cards for recruiter review",
    ];
  }

  if (scope === "validation" || scope === "recruiter_validation") {
    return [
      "Reading the current reference solution",
      "Running sample and hidden test cases",
      "Comparing expected and actual output",
      "Preparing the validation result",
    ];
  }

  if (scope === "metadata" || scope === "difficulty") {
    return [
      "Reading the final problem, tests, and solution",
      "Classifying difficulty",
      "Generating topics, tags, and category",
      "Reviewing complexity and approach",
    ];
  }

  return [
    "Reading current builder context",
    "Generating the requested section",
    "Reviewing the result",
  ];
}

function createInitialGenerationProgressEvent(
  scope: DraftScope,
): QuestionAIDraftProgressEvent {
  return {
    type: "start",
    scope,
    message:
      scope === "full"
        ? "Sending the builder context to the AI orchestrator."
        : "Sending the current builder context to the AI agent.",
    current_node: "queued",
    next_node: "queued",
    progress: 4,
  };
}

function languageKey(language: string) {
  const normalized = language.trim().toLowerCase();
  return normalized === "c++" ? "cpp" : normalized;
}

function normalizeLanguageList(
  languages: string[],
  fallbackLanguage = "python",
) {
  const normalized = languages.map(languageKey).filter(Boolean);
  const unique = Array.from(new Set(normalized));
  return unique.length ? unique : [languageKey(fallbackLanguage) || "python"];
}

function pruneReferenceSolutionsForLanguages(
  referenceSolutions: Record<string, ReferenceSolutionArtifact>,
  supportedLanguages: string[],
  referenceLanguage: string,
) {
  const allowedLanguages = new Set([
    ...supportedLanguages.map(languageKey),
    languageKey(referenceLanguage),
  ]);
  return Object.entries(referenceSolutions).reduce<
    Record<string, ReferenceSolutionArtifact>
  >((next, [language, artifact]) => {
    const normalizedLanguage = languageKey(language || artifact.language);
    if (!allowedLanguages.has(normalizedLanguage)) {
      return next;
    }
    next[normalizedLanguage] = {
      ...artifact,
      language: normalizedLanguage,
    };
    return next;
  }, {});
}

function syncComposerLanguageState(
  composer: QuestionCreatePayload,
): QuestionCreatePayload {
  const currentReferenceLanguage = languageKey(composer.reference_language);
  const supportedLanguages = normalizeLanguageList(
    composer.supported_languages,
    currentReferenceLanguage || "python",
  );
  const referenceLanguage = supportedLanguages.includes(currentReferenceLanguage)
    ? currentReferenceLanguage
    : supportedLanguages[0] ?? "python";
  return {
    ...composer,
    reference_language: referenceLanguage,
    supported_languages: supportedLanguages,
    reference_solutions: pruneReferenceSolutionsForLanguages(
      composer.reference_solutions,
      supportedLanguages,
      referenceLanguage,
    ),
  };
}

function monacoLanguage(language: string) {
  const normalized = languageKey(language);
  const languageMap: Record<string, string> = {
    c: "c",
    cpp: "cpp",
    java: "java",
    python: "python",
  };
  return languageMap[normalized] || normalized || "plaintext";
}

function buildSingleLanguagePrompt(language: string, recruiterPrompt: string) {
  const instruction = recruiterPrompt.trim();
  return instruction
    ? `Generate one complete runnable ${languageDisplayName(language)} solution only. ${instruction}`
    : `Generate one complete runnable ${languageDisplayName(language)} solution only from the supplied problem statement, constraints, formats, and sample test cases.`;
}

function agentCommentary(scope: BusyScope) {
  if (scope === "full") {
    return "The orchestrator is carrying the title into the statement, then constraints, tests, solution, validation, and metadata.";
  }
  if (scope === "tests_solution") {
    return "The test and solution agents are challenging each other, replacing bad testcase outputs or bad code before applying the final draft.";
  }
  if (scope === "tests") {
    return "The testcase agent is generating exact-count sample and hidden cases, then filtering inputs against the stated constraints.";
  }
  if (scope === "solution") {
    return "The solution agent writes runnable source code only. Use Execute Test Cases after this to run the accepted tests against that code.";
  }
  if (scope === "other_languages") {
    return "The language agent uses the validated tests only, then runs each translated program against the accepted inputs and outputs.";
  }
  if (scope === "validation" || scope === "recruiter_validation") {
    return "The execution engine is running the current reference solution against the sample and hidden tests.";
  }
  if (scope === "metadata" || scope === "difficulty") {
    return "The classifier is reading the final problem, tests, solution, and validation report before setting difficulty.";
  }
  return "The agent is using existing builder fields first, with your optional prompt only as extra guidance.";
}

function fromRecord(question: QuestionRecord): QuestionCreatePayload {
  return syncComposerLanguageState({
    title: question.title,
    problem_statement: question.problem_statement,
    difficulty: question.difficulty,
    topics: [...(question.topics ?? [])],
    tags: [...question.tags],
    category: question.category ?? "",
    constraints: question.constraints,
    input_format: question.input_format,
    input_explanation: question.input_explanation ?? "",
    output_format: question.output_format,
    output_explanation: question.output_explanation ?? "",
    sample_test_cases: question.sample_test_cases.map((item) => ({ ...item })),
    hidden_test_cases: question.hidden_test_cases.map((item) => ({ ...item })),
    reference_solution: question.reference_solution,
    reference_language: question.reference_language,
    supported_languages: [...question.supported_languages],
    candidate_solve_time_minutes: question.candidate_solve_time_minutes ?? 45,
    execution_time_limit_seconds: question.execution_time_limit_seconds ?? 2,
    memory_limit_mb: question.memory_limit_mb ?? 256,
    metadata_status: question.metadata_status ?? "pending",
    difficulty_source: question.difficulty_source ?? "legacy",
    validation_report: question.validation_report ?? null,
    validation_status: question.validation_status ?? "not_run",
    validation_updated_at: question.validation_updated_at ?? null,
    reference_solutions: { ...(question.reference_solutions ?? {}) },
    answer_validation_mode: question.answer_validation_mode ?? "exact",
    output_checker: question.output_checker ?? "",
    output_checker_explanation:
      question.output_checker_explanation ||
      answerValidationOption(question.answer_validation_mode ?? "exact").detail,
    solution_approach: question.solution_approach ?? "",
    time_complexity: question.time_complexity ?? "",
    space_complexity: question.space_complexity ?? "",
    status: question.status,
    creation_mode: question.creation_mode,
    visibility: question.visibility ?? "private",
  });
}

function cloneComposer(composer: QuestionCreatePayload): QuestionCreatePayload {
  return {
    ...composer,
    topics: [...composer.topics],
    tags: [...composer.tags],
    sample_test_cases: composer.sample_test_cases.map((item) => ({ ...item })),
    hidden_test_cases: composer.hidden_test_cases.map((item) => ({ ...item })),
    supported_languages: [...composer.supported_languages],
    reference_solutions: { ...composer.reference_solutions },
    validation_report: composer.validation_report
      ? {
          ...composer.validation_report,
          runner_notes: [...composer.validation_report.runner_notes],
          results: composer.validation_report.results.map((item) => ({ ...item })),
          rounds: composer.validation_report.rounds.map((round) => ({
            ...round,
            added_hidden_test_cases: round.added_hidden_test_cases.map((item) => ({
              ...item,
            })),
            results: round.results.map((item) => ({ ...item })),
          })),
        }
      : null,
  };
}

function countCompleteTestCases(testCases: TestCase[]) {
  return testCases.filter(
    (testCase) => testCase.input.trim() && testCase.expected_output.trim(),
  ).length;
}

function persistableTestCases(testCases: TestCase[]) {
  return testCases.filter((testCase) => testCase.input.trim().length > 0);
}

function scoreComposer(composer: QuestionCreatePayload) {
  const requiredChecks = [
    composer.title.trim().length >= 3,
    composer.problem_statement.trim().length > 20,
    composer.constraints.trim().length > 0,
    composer.reference_solution.trim().length > 0,
  ];
  const qualityChecks = [
    ...requiredChecks,
    countCompleteTestCases(composer.sample_test_cases) > 0,
    countCompleteTestCases(composer.hidden_test_cases) > 0,
  ];

  const completion = Math.round(
    (requiredChecks.filter(Boolean).length / requiredChecks.length) * 100,
  );
  const quality = Math.round(
    (qualityChecks.filter(Boolean).length / qualityChecks.length) * 100,
  );
  const confidence = Math.min(100, Math.max(38, completion + (quality >= 80 ? 12 : 6)));
  const readiness = Math.round((completion + quality + confidence) / 3);

  return { completion, quality, confidence, readiness };
}

function getQuestionSaveError(
  composer: QuestionCreatePayload,
  solutionValidation: SolutionValidationReport | null,
  solutionValidationStale: boolean,
) {
  if (composer.title.trim().length < 3) {
    return "Add a title with at least 3 characters.";
  }
  if (composer.problem_statement.trim().length < 20) {
    return "Add a problem statement with at least 20 characters.";
  }
  if (composer.status !== "validated") {
    return "";
  }
  if (!composer.constraints.trim()) {
    return "Validated questions require constraints.";
  }
  if (!composer.reference_solution.trim()) {
    return "Validated questions require a reference solution.";
  }
  if (countCompleteTestCases(composer.sample_test_cases) === 0) {
    return "Validated questions require at least one complete sample test.";
  }
  if (countCompleteTestCases(composer.hidden_test_cases) === 0) {
    return "Validated questions require at least one complete hidden test.";
  }
  if (solutionValidationStale && solutionValidation) {
    return "Execution validation is stale. Re-run solution validation before saving as validated.";
  }
  if (!solutionValidation || composer.validation_status !== "passed") {
    return "Validated questions require a passing execution validation for the reference solution.";
  }
  if (solutionValidation.status !== "passed") {
    return "Validated questions require a passing execution validation for the reference solution.";
  }
  if (!otherLanguageSolutionsComplete(composer)) {
    return "Validated questions require passing generated solutions for every selected non-primary language.";
  }
  if (composer.metadata_status !== "classified" || composer.difficulty_source !== "ai") {
    return "Validated questions require final AI difficulty, topics, and category classification.";
  }
  return "";
}

function nextStepAfterGeneration(scope: DraftScope): WizardStep | null {
  switch (scope) {
    case "full":
      return 5;
    case "basics":
      return 2;
    case "problem":
    case "constraints":
    case "constraints_formats":
    case "problem_field":
      return null;
    case "examples":
    case "tests":
      return 3;
    case "tests_solution":
      return 3;
    case "solution":
      return 3;
    case "other_languages":
      return 4;
    case "recruiter_validation":
      return 3;
    case "difficulty":
    case "metadata":
      return 5;
    default:
      return null;
  }
}

function getBasicsSetupError(
  composer: QuestionCreatePayload,
  generationSettings: GenerationSettingsState,
) {
  if (composer.title.trim().length < 3) {
    return "Add a question title before continuing.";
  }

  if (!composer.supported_languages.length) {
    return "Select at least one supported language.";
  }

  if (generationSettings.sample_test_case_count < 1) {
    return "Sample test count must be at least 1.";
  }

  if (generationSettings.hidden_test_case_count < 1) {
    return "Hidden test count must be at least 1.";
  }

  return "";
}

function exactTestCountsSatisfied(
  composer: QuestionCreatePayload,
  generationSettings: GenerationSettingsState,
) {
  return (
    composer.sample_test_cases.length ===
      generationSettings.sample_test_case_count &&
    countCompleteTestCases(composer.sample_test_cases) ===
      generationSettings.sample_test_case_count &&
    composer.hidden_test_cases.length ===
      generationSettings.hidden_test_case_count &&
    countCompleteTestCases(composer.hidden_test_cases) ===
      generationSettings.hidden_test_case_count
  );
}

function otherLanguageSolutionsComplete(composer: QuestionCreatePayload) {
  const primaryLanguage = languageKey(composer.reference_language);
  const targetLanguages = normalizeLanguageList(
    composer.supported_languages,
    primaryLanguage,
  ).filter(
    (language) => language !== primaryLanguage,
  );
  if (!targetLanguages.length) {
    return true;
  }

  return targetLanguages.every((language) => {
    const artifact = composer.reference_solutions[language];
    return Boolean(
      artifact?.source_code.trim() && artifact.validation_status === "passed",
    );
  });
}

function getGenerationPrerequisiteError(
  scope: DraftScope,
  composer: QuestionCreatePayload,
  generationSettings: GenerationSettingsState,
) {
  const basicsError = getBasicsSetupError(composer, generationSettings);
  if (scope === "full" || scope === "basics") {
    return basicsError;
  }
  if (scope === "problem") {
    return composer.title.trim().length < 3
      ? "Add a question title before generating the problem statement."
      : "";
  }
  if (scope === "constraints" || scope === "constraints_formats") {
    if (composer.problem_statement.trim().length < 20) {
      return "Add the problem statement before generating constraints and formats.";
    }
    return "";
  }
  if (scope === "tests" || scope === "tests_solution") {
    if (!stepIsComplete(2, composer)) {
      return "Complete the problem statement, input/output formats, and constraints before generating tests.";
    }
    return "";
  }
  if (scope === "solution") {
    if (!stepIsComplete(2, composer)) {
      return "Complete the problem statement, input/output formats, and constraints before generating solution code.";
    }
    if (!exactTestCountsSatisfied(composer, generationSettings)) {
      return "Generate or enter the exact sample and hidden test counts before generating solution code.";
    }
    return "";
  }
  if (scope === "recruiter_validation") {
    return getValidationPrerequisiteError(composer, generationSettings);
  }
  if (scope === "other_languages") {
    if (composer.validation_status !== "passed") {
      return "Run recruiter validation successfully before generating other language solutions.";
    }
    return "";
  }
  if (scope === "metadata" || scope === "difficulty") {
    if (composer.validation_status !== "passed") {
      return "Run passing validation before generating final metadata.";
    }
    return "";
  }
  return "";
}

function getValidationPrerequisiteError(
  composer: QuestionCreatePayload,
  generationSettings: GenerationSettingsState,
) {
  if (!exactTestCountsSatisfied(composer, generationSettings)) {
    return "Complete every testcase and match the sample and hidden counts before running all tests.";
  }
  if (!composer.reference_solution.trim()) {
    return "Generate or paste a runnable reference solution before executing tests.";
  }
  return "";
}

function getTestcaseRepairPrerequisiteError(composer: QuestionCreatePayload) {
  if (composer.problem_statement.trim().length < 20) {
    return "Add a clear problem statement before repairing test cases.";
  }
  if (!composer.input_format.trim() || !composer.output_format.trim()) {
    return "Add input and output formats before repairing test cases.";
  }
  if (!composer.constraints.trim()) {
    return "Add constraints before repairing test cases.";
  }
  if (!composer.reference_solution.trim()) {
    return "Generate or paste a runnable reference solution before repairing test cases.";
  }
  return "";
}

function normalizeGeneratedTestCases(
  testCases: TestCase[],
  isSample: boolean,
  targetCount?: number,
) {
  const normalized = testCases
    .filter((testCase) => testCase.input.trim() && testCase.expected_output.trim())
    .map((testCase) => ({ ...testCase, is_sample: isSample }));

  return typeof targetCount === "number" ? normalized.slice(0, targetCount) : normalized;
}

function stepIsComplete(
  step: WizardStep,
  composer: QuestionCreatePayload,
  generationSettings?: GenerationSettingsState,
) {
  switch (step) {
    case 1:
      return generationSettings
        ? !getBasicsSetupError(composer, generationSettings)
        : composer.title.trim().length >= 3 && composer.supported_languages.length > 0;
    case 2:
      return (
        composer.problem_statement.trim().length > 20 &&
        composer.input_format.trim().length > 0 &&
        composer.output_format.trim().length > 0 &&
        composer.constraints.trim().length > 0
      );
    case 3:
      return (
        (generationSettings
          ? exactTestCountsSatisfied(composer, generationSettings)
          : countCompleteTestCases(composer.sample_test_cases) > 0 &&
            countCompleteTestCases(composer.hidden_test_cases) > 0) &&
        composer.reference_solution.trim().length > 0 &&
        composer.validation_status === "passed"
      );
    case 4:
      return otherLanguageSolutionsComplete(composer);
    case 5:
      return composer.metadata_status === "classified" && composer.difficulty_source === "ai";
    case 6:
      return false;
    default:
      return false;
  }
}

function getAiPromptCopy(scope: DraftScope, composer: QuestionCreatePayload): AiPromptCopy {
  switch (scope) {
    case "full":
      return {
        eyebrow: "Full draft",
        title: "Generate full question draft",
        question: "Optional instructions",
        placeholder:
          "Example: Beginner if/else voting problem for age 18.",
        helper: "Leave blank to use the fields shown below.",
        actionLabel: "Generate Full Draft",
      };
    case "basics":
      return {
        eyebrow: "Basics",
        title: "Generate basics",
        question: "Optional instructions",
        placeholder: "Example: Keep it beginner-friendly.",
        helper: "Leave blank to use the fields shown below.",
        actionLabel: "Generate Basics",
      };
    case "problem":
      return {
        eyebrow: "Problem",
        title: "Generate problem statement and formats",
        question: "Optional instructions",
        placeholder:
          "Example: Keep the statement short and beginner-friendly.",
        helper: "Leave blank to use title, tags, and languages. Statement, input/output formats, and constraints are applied together.",
        actionLabel: "Generate Step 2 Contract",
      };
    case "problem_field":
      return {
        eyebrow: "Problem fields",
        title: "Fill missing problem fields",
        question: "Optional instructions",
        placeholder:
          "Example: Only improve input/output explanations and sample explanation.",
        helper: "Leave blank to use the title, statement, formats, constraints, and sample.",
        actionLabel: "Fill Missing Fields",
      };
    case "constraints":
    case "constraints_formats":
      return {
        eyebrow: "Formats and constraints",
        title: "Generate constraints and formats",
        question: "Optional instructions",
        placeholder:
          "Example: Add clear input/output format and bounds like 0 <= age <= 120.",
        helper: "Leave blank to use the problem statement and formats.",
        actionLabel: "Generate Constraints & Formats",
      };
    case "examples":
    case "tests":
    case "tests_solution":
      if (scope === "tests_solution") {
        return {
          eyebrow: "Tests and solution",
          title: "Generate test cases and solution",
          question: "Optional instructions",
          placeholder:
            "Example: Add strong boundary cases and keep the solution simple.",
          helper: "Leave blank to run the full testcase, solution, validation, and repair loop.",
          actionLabel: "Generate Tests & Solution",
        };
      }
      return {
        eyebrow: "Tests",
        title: "Generate test cases",
        question: "Optional instructions",
        placeholder:
          "Example: Add strong boundary and edge cases.",
        helper: "Leave blank to use the statement and constraints. The final counts must match Step 1.",
        actionLabel: "Generate Test Cases",
      };
    case "solution":
      return {
        eyebrow: "Solution",
        title: "Generate solution code",
        question: "Optional instructions",
        placeholder:
          `Example: Write complete ${composer.reference_language.toUpperCase()} source code, not just the algorithm name.`,
        helper: "Leave blank to use generated tests and constraints. Execution runs only when you click Execute Test Cases.",
        actionLabel: "Generate Solution Code",
      };
    case "other_languages":
      return {
        eyebrow: "Other languages",
        title: "Generate other language solutions",
        question: "Optional instructions",
        placeholder:
          "Example: Keep Java and C++ solutions simple and readable.",
        helper: "Leave blank to translate the validated primary solution against accepted tests.",
        actionLabel: "Generate Other Languages",
      };
    case "recruiter_validation":
      return {
        eyebrow: "Recruiter validation",
        title: "Run recruiter validation gate",
        question: "Optional instructions",
        placeholder:
          "Example: Confirm edge cases are covered before metadata.",
        helper: "Leave blank to run execution validation with the current draft.",
        actionLabel: "Run Validation Gate",
      };
    case "difficulty":
    case "metadata":
      return {
        eyebrow: "Metadata",
        title: "Classify difficulty and metadata",
        question: "Optional instructions",
        placeholder:
          "Example: This is for absolute beginners learning if/else.",
        helper: "Leave blank to let the classifier use the completed question.",
        actionLabel: "Classify Difficulty & Metadata",
      };
    default:
      return {
        eyebrow: "AI prompt",
        title: "Generate with AI",
        question: "Optional instructions",
        placeholder: "Add any extra instruction.",
        helper: "Leave blank to use the fields shown below.",
        actionLabel: "Run AI",
      };
  }
}

function compactValue(value: string, fallback = "Not added yet") {
  const normalized = value.trim().replace(/\s+/g, " ");
  if (!normalized) {
    return fallback;
  }
  return normalized.length > 90 ? `${normalized.slice(0, 90)}...` : normalized;
}

function getPromptContextSources(
  scope: DraftScope,
  composer: QuestionCreatePayload,
  generationSettings: GenerationSettingsState,
): PromptContextSource[] {
  const source = (label: string, value: string, ready = Boolean(value.trim())) => ({
    label,
    value: compactValue(value),
    ready,
  });
  const testSummary = `${countCompleteTestCases(composer.sample_test_cases)} sample, ${countCompleteTestCases(composer.hidden_test_cases)} hidden`;
  const testTargets = `${generationSettings.sample_test_case_count} sample, ${generationSettings.hidden_test_case_count} hidden`;
  const solveTime = `${generationSettings.candidate_solve_time_minutes} min candidate solve time`;
  const runtimeCap = `${generationSettings.execution_time_limit_seconds}s execution time`;
  const memoryCap = `${generationSettings.memory_limit_mb} MB memory`;

  switch (scope) {
    case "full":
      return [
        source("Title", composer.title),
        source("Languages", composer.supported_languages.join(", "), true),
        source("Test targets", testTargets, true),
        source("Limits", `${solveTime}; ${runtimeCap}; ${memoryCap}`, true),
      ];
    case "problem":
    case "problem_field":
      return [
        source("Title", composer.title),
        source("Problem statement", composer.problem_statement),
        source("Languages", composer.supported_languages.join(", "), true),
      ];
    case "constraints":
    case "constraints_formats":
      return [
        source("Title", composer.title),
        source("Problem statement", composer.problem_statement),
        source("Input format", composer.input_format),
        source("Output format", composer.output_format),
        source("Limits", `${solveTime}; ${runtimeCap}; ${memoryCap}`, true),
      ];
    case "examples":
    case "tests":
    case "tests_solution":
      return [
        source("Problem statement", composer.problem_statement),
        source("Constraints", composer.constraints),
        source("Input format", composer.input_format),
        source("Output format", composer.output_format),
        source("Test targets", testTargets, true),
      ];
    case "solution":
      return [
        source("Problem statement", composer.problem_statement),
        source("Constraints", composer.constraints),
        source("Tests", testSummary, testSummary !== "0 sample, 0 hidden"),
        source("Language", composer.reference_language, true),
        source("Program contract", "Complete STDIN/STDOUT program", true),
      ];
    case "other_languages":
      return [
        source("Primary validation", composer.validation_status, composer.validation_status === "passed"),
        source("Reference language", composer.reference_language, true),
        source("Requested languages", composer.supported_languages.join(", "), true),
        source("Tests", testSummary, testSummary !== "0 sample, 0 hidden"),
        source("Reference solution", composer.reference_solution),
      ];
    case "recruiter_validation":
      return [
        source("Problem statement", composer.problem_statement),
        source("Constraints", composer.constraints),
        source("Tests", testSummary, testSummary !== "0 sample, 0 hidden"),
        source("Reference solution", composer.reference_solution),
        source("Exact test targets", testTargets, true),
      ];
    case "difficulty":
    case "metadata":
      return [
        source("Title", composer.title),
        source("Problem statement", composer.problem_statement),
        source("Constraints", composer.constraints),
        source("Tests", testSummary, testSummary !== "0 sample, 0 hidden"),
        source("Reference solution", composer.reference_solution),
        source("Validation", composer.validation_status, composer.validation_status === "passed"),
      ];
    case "basics":
    default:
      return [source("Languages", composer.supported_languages.join(", "), true)];
  }
}

function buildSectionPrompt(
  scope: DraftScope,
  recruiterPrompt: string,
) {
  const taskByScope: Record<DraftScope, string> = {
    full: "Generate and validate the complete question draft.",
    basics: "Generate only the starter title and context fields.",
    problem: "Generate the title, problem statement, input format, output format, and constraints in one response.",
    problem_field: "Complete only missing or explicitly requested problem fields.",
    constraints: "Generate only I/O formats, constraints, and execution limits.",
    constraints_formats: "Generate only I/O formats, constraints, and execution limits.",
    examples: "Generate only the requested public sample testcases.",
    tests: "Generate only the requested sample and hidden testcases.",
    tests_solution: "Generate testcases, the primary solution, and validation.",
    solution: "Generate only the primary runnable reference solution.",
    other_languages: "Generate only requested non-primary language solutions.",
    recruiter_validation: "Validate the current draft without regenerating sections.",
    difficulty: "Classify final difficulty and metadata only.",
    metadata: "Classify final difficulty and metadata only.",
  };

  return JSON.stringify(
    {
      task: taskByScope[scope],
      recruiter_instruction: recruiterPrompt.trim() || null,
    },
    null,
    2,
  );
}

function answerValidationFieldsFromDraft(
  current: QuestionCreatePayload,
  draft: QuestionCreatePayload,
) {
  return {
    answer_validation_mode:
      draft.answer_validation_mode || current.answer_validation_mode,
    output_checker: draft.output_checker ?? current.output_checker,
    output_checker_explanation:
      draft.output_checker_explanation || current.output_checker_explanation,
  };
}

function mergeDraftIntoComposer(
  current: QuestionCreatePayload,
  draft: QuestionCreatePayload,
  scope: DraftScope,
  generationSettings?: GenerationSettingsState,
): QuestionCreatePayload {
  if (scope === "full") {
    return syncComposerLanguageState({
      ...cloneComposer(draft),
      status: current.status,
      creation_mode: "ai_assisted",
    });
  }

  if (scope === "basics") {
    return syncComposerLanguageState({
      ...current,
      title: draft.title || current.title,
      topics: draft.topics.length ? draft.topics : current.topics,
      tags: draft.tags.length ? draft.tags : current.tags,
      category: draft.category || current.category,
      supported_languages: draft.supported_languages.length
        ? draft.supported_languages
        : current.supported_languages,
      creation_mode: "ai_assisted",
    });
  }

  if (scope === "problem" || scope === "problem_field") {
    if (scope === "problem") {
      return {
        ...current,
        title: draft.title || current.title,
        problem_statement: draft.problem_statement || current.problem_statement,
        input_format: draft.input_format || current.input_format,
        input_explanation: draft.input_explanation || current.input_explanation,
        output_format: draft.output_format || current.output_format,
        output_explanation: draft.output_explanation || current.output_explanation,
        constraints: draft.constraints || current.constraints,
        candidate_solve_time_minutes:
          draft.candidate_solve_time_minutes || current.candidate_solve_time_minutes,
        execution_time_limit_seconds:
          draft.execution_time_limit_seconds || current.execution_time_limit_seconds,
        memory_limit_mb: draft.memory_limit_mb || current.memory_limit_mb,
        topics: draft.topics.length ? draft.topics : current.topics,
        tags: draft.tags.length ? draft.tags : current.tags,
        category: draft.category || current.category,
        ...answerValidationFieldsFromDraft(current, draft),
        creation_mode: "ai_assisted",
      };
    }

    return {
      ...current,
      title: draft.title || current.title,
      problem_statement: draft.problem_statement || current.problem_statement,
      input_format: draft.input_format || current.input_format,
      input_explanation: draft.input_explanation || current.input_explanation,
      output_format: draft.output_format || current.output_format,
      output_explanation: draft.output_explanation || current.output_explanation,
      constraints: draft.constraints || current.constraints,
      sample_test_cases: draft.sample_test_cases.length
        ? draft.sample_test_cases.map((item) => ({ ...item, is_sample: true }))
        : current.sample_test_cases,
      ...answerValidationFieldsFromDraft(current, draft),
      creation_mode: "ai_assisted",
    };
  }

  if (scope === "constraints" || scope === "constraints_formats") {
    return {
      ...current,
      input_format:
        scope === "constraints_formats" ? draft.input_format || current.input_format : current.input_format,
      input_explanation: scope === "constraints_formats" ? "" : current.input_explanation,
      output_format:
        scope === "constraints_formats"
          ? draft.output_format || current.output_format
          : current.output_format,
      output_explanation: scope === "constraints_formats" ? "" : current.output_explanation,
      constraints: draft.constraints || current.constraints,
      candidate_solve_time_minutes:
        draft.candidate_solve_time_minutes || current.candidate_solve_time_minutes,
      execution_time_limit_seconds:
        draft.execution_time_limit_seconds || current.execution_time_limit_seconds,
      memory_limit_mb: draft.memory_limit_mb || current.memory_limit_mb,
      ...answerValidationFieldsFromDraft(current, draft),
      creation_mode: "ai_assisted",
    };
  }

  if (scope === "examples" || scope === "tests" || scope === "tests_solution") {
    const sampleTarget = generationSettings?.sample_test_case_count;
    const hiddenTarget = generationSettings?.hidden_test_case_count;
    return syncComposerLanguageState({
      ...current,
      constraints: draft.constraints || current.constraints,
      sample_test_cases: draft.sample_test_cases.length
        ? normalizeGeneratedTestCases(draft.sample_test_cases, true, sampleTarget)
        : current.sample_test_cases,
      hidden_test_cases: draft.hidden_test_cases.length
        ? normalizeGeneratedTestCases(draft.hidden_test_cases, false, hiddenTarget)
        : current.hidden_test_cases,
      reference_solution: draft.reference_solution || current.reference_solution,
      reference_language: draft.reference_language || current.reference_language,
      validation_report: draft.validation_report || current.validation_report,
      validation_status: draft.validation_status || current.validation_status,
      validation_updated_at: draft.validation_updated_at || current.validation_updated_at,
      ...answerValidationFieldsFromDraft(current, draft),
      reference_solutions:
        Object.keys(draft.reference_solutions).length > 0
          ? draft.reference_solutions
          : current.reference_solutions,
      solution_approach: draft.solution_approach || current.solution_approach,
      time_complexity: draft.time_complexity || current.time_complexity,
      space_complexity: draft.space_complexity || current.space_complexity,
      creation_mode: "ai_assisted",
    });
  }

  if (scope === "solution") {
    return syncComposerLanguageState({
      ...current,
      reference_solution: draft.reference_solution || current.reference_solution,
      reference_language: draft.reference_language || current.reference_language,
      supported_languages: draft.supported_languages.length
        ? draft.supported_languages
        : current.supported_languages,
      reference_solutions:
        Object.keys(draft.reference_solutions).length > 0
          ? {
              ...current.reference_solutions,
              ...draft.reference_solutions,
            }
          : current.reference_solutions,
      solution_approach: draft.solution_approach || current.solution_approach,
      time_complexity: draft.time_complexity || current.time_complexity,
      space_complexity: draft.space_complexity || current.space_complexity,
      validation_status: current.validation_status === "not_run" ? "not_run" : "stale",
      creation_mode: "ai_assisted",
    });
  }

  if (scope === "other_languages") {
    return syncComposerLanguageState({
      ...current,
      supported_languages: current.supported_languages,
      reference_solutions:
        Object.keys(draft.reference_solutions).length > 0
          ? {
              ...current.reference_solutions,
              ...draft.reference_solutions,
            }
          : current.reference_solutions,
      creation_mode: "ai_assisted",
    });
  }

  if (scope === "recruiter_validation") {
    return syncComposerLanguageState({
      ...current,
      sample_test_cases: draft.sample_test_cases.length
        ? normalizeGeneratedTestCases(
            draft.sample_test_cases,
            true,
            generationSettings?.sample_test_case_count,
          )
        : current.sample_test_cases,
      hidden_test_cases: draft.hidden_test_cases.length
        ? normalizeGeneratedTestCases(
            draft.hidden_test_cases,
            false,
            generationSettings?.hidden_test_case_count,
          )
        : current.hidden_test_cases,
      reference_solution: draft.reference_solution || current.reference_solution,
      validation_report: draft.validation_report || current.validation_report,
      validation_status: draft.validation_status || current.validation_status,
      validation_updated_at: draft.validation_updated_at || current.validation_updated_at,
      ...answerValidationFieldsFromDraft(current, draft),
      reference_solutions:
        Object.keys(draft.reference_solutions).length > 0
          ? {
              ...current.reference_solutions,
              ...draft.reference_solutions,
            }
          : current.reference_solutions,
      creation_mode: "ai_assisted",
    });
  }

  if (scope === "difficulty" || scope === "metadata") {
    return syncComposerLanguageState({
      ...current,
      difficulty: draft.difficulty,
      topics: draft.topics.length ? draft.topics : current.topics,
      tags: draft.tags.length ? draft.tags : current.tags,
      category: draft.category || current.category,
      candidate_solve_time_minutes:
        draft.candidate_solve_time_minutes || current.candidate_solve_time_minutes,
      metadata_status: draft.metadata_status,
      difficulty_source: draft.difficulty_source,
      solution_approach: draft.solution_approach || current.solution_approach,
      time_complexity: draft.time_complexity || current.time_complexity,
      space_complexity: draft.space_complexity || current.space_complexity,
      creation_mode: "ai_assisted",
    });
  }

  return syncComposerLanguageState({
    ...current,
    constraints: draft.constraints || current.constraints,
    sample_test_cases: draft.sample_test_cases.length
      ? draft.sample_test_cases.map((item) => ({ ...item, is_sample: true }))
      : current.sample_test_cases,
    hidden_test_cases: draft.hidden_test_cases.length
      ? draft.hidden_test_cases.map((item) => ({ ...item, is_sample: false }))
      : current.hidden_test_cases,
    reference_solution: draft.reference_solution || current.reference_solution,
    reference_language: draft.reference_language || current.reference_language,
    difficulty: draft.difficulty,
    topics: draft.topics.length ? draft.topics : current.topics,
    tags: draft.tags.length ? draft.tags : current.tags,
    category: draft.category || current.category,
    supported_languages: draft.supported_languages.length
      ? draft.supported_languages
      : current.supported_languages,
    candidate_solve_time_minutes:
      draft.candidate_solve_time_minutes || current.candidate_solve_time_minutes,
    execution_time_limit_seconds:
      draft.execution_time_limit_seconds || current.execution_time_limit_seconds,
    memory_limit_mb: draft.memory_limit_mb || current.memory_limit_mb,
    metadata_status: draft.metadata_status || current.metadata_status,
    difficulty_source: draft.difficulty_source || current.difficulty_source,
    validation_report: draft.validation_report || current.validation_report,
    validation_status: draft.validation_status || current.validation_status,
    validation_updated_at: draft.validation_updated_at || current.validation_updated_at,
    ...answerValidationFieldsFromDraft(current, draft),
    reference_solutions:
      Object.keys(draft.reference_solutions).length > 0
        ? draft.reference_solutions
        : current.reference_solutions,
    solution_approach: draft.solution_approach || current.solution_approach,
    time_complexity: draft.time_complexity || current.time_complexity,
    space_complexity: draft.space_complexity || current.space_complexity,
    creation_mode: "ai_assisted",
  });
}

function questionStatusTone(status: QuestionStatus) {
  switch (status) {
    case "validated":
      return "validated";
    case "blocked":
      return "blocked";
    case "archived":
      return "archived";
    default:
      return "draft";
  }
}

function questionDifficultyTone(difficulty: DifficultyLevel) {
  return difficulty;
}

function formatCount(value: number) {
  return value.toLocaleString();
}

export function QuestionManagementPage() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [saveSuccess, setSaveSuccess] = useState(
    () => (location.state as { questionSaveSuccess?: string } | null)?.questionSaveSuccess ?? "",
  );
  const bulkImportQuestions = useBulkImportQuestionBankQuestions(currentUser);
  const { data, isLoading } = useQuestionBank(currentUser, {
    search: "",
    difficulty: "",
    status: "",
    tag: "",
  });
  const { data: groupData, isLoading: groupsLoading } = useQuestionGroups(currentUser, {
    search: "",
    status: "",
  });

  const questionItems = data?.items;
  const questions = useMemo(() => questionItems ?? [], [questionItems]);
  const groupItems = groupData?.items;
  const groups = useMemo(() => groupItems ?? [], [groupItems]);
  const [view, setView] = useState<DashboardView>("questions");
  const [search, setSearch] = useState("");
  const [expandedGroupId, setExpandedGroupId] = useState<string | null>(null);
  const [showBulkImportModal, setShowBulkImportModal] = useState(false);
  const [bulkCsvText, setBulkCsvText] = useState("");
  const [bulkCsvFileName, setBulkCsvFileName] = useState("");
  const [bulkImportError, setBulkImportError] = useState("");
  const [bulkImportResult, setBulkImportResult] =
    useState<QuestionBulkImportResponse | null>(null);
  const [generationSession, setGenerationSession] = useState(
    getQuestionGenerationSession,
  );

  useEffect(() => {
    setGenerationSession(getQuestionGenerationSession());
    return subscribeQuestionGenerationSession(setGenerationSession);
  }, []);

  useEffect(() => {
    if (!saveSuccess) {
      return;
    }
    navigate(location.pathname, { replace: true, state: null });
    const timerId = window.setTimeout(() => setSaveSuccess(""), 5000);
    return () => window.clearTimeout(timerId);
  }, [location.pathname, navigate, saveSuccess]);

  const filteredQuestions = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) {
      return questions;
    }

    return questions.filter((question) => {
      const haystack = [
        question.title,
        question.problem_statement,
        question.difficulty,
        question.status,
        question.creation_mode,
        question.visibility,
        question.tags.join(" "),
        question.validation_status,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [questions, search]);
  const runningGeneration =
    generationSession?.status === "running" ? generationSession : null;
  const runningQuestionIsVisible = Boolean(
    runningGeneration?.questionId &&
      filteredQuestions.some((question) => question.id === runningGeneration.questionId),
  );
  const showTemporaryGenerationRow = Boolean(
    runningGeneration && !runningQuestionIsVisible,
  );
  const generationProgress =
    runningGeneration?.events[runningGeneration.events.length - 1]?.progress ?? 0;

  const metrics = useMemo(() => {
    const validated = questions.filter((item) => item.status === "validated").length;
    const drafts = questions.filter((item) => item.status === "draft").length;
    const avgScore = questions.length
      ? Math.round(
          questions.reduce((sum, item) => sum + scoreComposer(fromRecord(item)).readiness, 0) /
            questions.length,
        )
      : 0;

    return {
      questions: questions.length,
      validated,
      drafts,
      groups: groups.length,
      avgScore,
    };
  }, [groups.length, questions]);

  function openQuestion(question: QuestionRecord) {
    navigate(`/recruiter/question-management/new?questionId=${encodeURIComponent(question.id)}`);
  }

  function openRunningGeneration() {
    const target = runningGeneration?.questionId
      ? `/recruiter/question-management/new?questionId=${encodeURIComponent(runningGeneration.questionId)}`
      : "/recruiter/question-management/new";
    navigate(target);
  }

  function closeBulkImportModal() {
    setShowBulkImportModal(false);
    setBulkImportError("");
  }

  async function readBulkImportFile(file: File | undefined) {
    if (!file) {
      return;
    }

    try {
      setBulkImportError("");
      setBulkCsvFileName(file.name);
      setBulkCsvText(await file.text());
      setBulkImportResult(null);
    } catch {
      setBulkImportError("Unable to read the selected CSV file.");
    }
  }

  async function runBulkImport() {
    if (!bulkCsvText.trim()) {
      setBulkImportError("Choose a CSV file or paste CSV content before importing.");
      return;
    }

    try {
      setBulkImportError("");
      const result = await bulkImportQuestions.mutateAsync({ csv_text: bulkCsvText });
      setBulkImportResult(result);
      if (result.created_count > 0) {
        setView("questions");
      }
    } catch (error) {
      setBulkImportError(
        error instanceof Error ? error.message : "Unable to import questions.",
      );
    }
  }

  return (
    <main className="question-management-page">
      {saveSuccess ? (
        <div className="question-save-success" role="status">
          <CheckCircle2 size={20} />
          <div>
            <strong>Saved successfully</strong>
            <span>{saveSuccess}</span>
          </div>
          <button type="button" onClick={() => setSaveSuccess("")} aria-label="Dismiss success message">
            Close
          </button>
        </div>
      ) : null}
      <section className="management-hero management-hero-compact">
        <div>
          <p>Question management</p>
          <h1>Question library</h1>
        </div>
        <div className="assessment-hero-metrics">
          <span>
            <strong>{formatCount(metrics.questions)}</strong>
            Total
          </span>
          <span>
            <strong>{formatCount(metrics.validated)}</strong>
            Validated
          </span>
          <span>
            <strong>{formatCount(metrics.drafts)}</strong>
            Drafts
          </span>
          <span>
            <strong>{formatCount(metrics.groups)}</strong>
            Groups
          </span>
        </div>
        <div className="management-hero-actions">
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              setShowBulkImportModal(true);
              setBulkImportResult(null);
              setBulkImportError("");
            }}
          >
            Bulk CSV Upload
          </Button>
          <Button type="button" variant="secondary" onClick={() => navigate("/recruiter/question-management/groups/new")}>
            New Group
          </Button>
          <Button type="button" onClick={() => navigate("/recruiter/question-management/new")}>
            New Question
          </Button>
        </div>
      </section>

      <section className="management-grid">
        <Card className="management-panel">
          <div className="panel-head question-library-panel-head">
            <div className="question-library-controls">
              <div className="segmented-control" role="tablist" aria-label="Management view">
                <button
                  type="button"
                  className={view === "questions" ? "is-active" : ""}
                  onClick={() => setView("questions")}
                >
                  Questions
                </button>
                <button
                  type="button"
                  className={view === "groups" ? "is-active" : ""}
                  onClick={() => setView("groups")}
                >
                  Groups
                </button>
              </div>

              <label className="field search-field question-library-search">
                <span>Search</span>
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search title, tag, status, or mode"
                />
              </label>
            </div>
            <span>
              {view === "questions"
                ? filteredQuestions.length + (showTemporaryGenerationRow ? 1 : 0)
                : groups.length}{" "}
              rows
            </span>
          </div>

          {view === "questions" ? (
            <div className="table-shell">
              <table className="data-table question-library-table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Tags</th>
                    <th>Difficulty</th>
                    <th>Question Status</th>
                    <th>Visibility</th>
                    <th>Updated</th>
                    <th>Options</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr>
                      <td colSpan={7} className="table-empty">
                        Loading questions...
                      </td>
                    </tr>
                  ) : filteredQuestions.length === 0 && !showTemporaryGenerationRow ? (
                    <tr>
                      <td colSpan={7} className="table-empty">
                        No questions yet. Start with a new question flow.
                      </td>
                    </tr>
                  ) : (
                    <>
                      {showTemporaryGenerationRow && runningGeneration ? (
                        <tr className="data-row question-row-compact question-row-generating">
                          <td>
                            <div className="question-title-cell">
                              <strong>
                                {runningGeneration.baseDraft.title.trim() || "Untitled question"}
                              </strong>
                              <span className="question-generation-status" role="status">
                                <i aria-hidden="true" />
                                Generating... {generationProgress}%
                              </span>
                            </div>
                          </td>
                          <td>
                            <div className="tag-list">
                              {runningGeneration.baseDraft.tags.length ? (
                                runningGeneration.baseDraft.tags.slice(0, 6).map((tag) => (
                                  <span key={`generating-${tag}`}>{tag}</span>
                                ))
                              ) : (
                                <span className="is-empty">AI draft in progress</span>
                              )}
                            </div>
                          </td>
                          <td>
                            <span className="pill pending">Pending AI</span>
                          </td>
                          <td>
                            <span className="pill draft">Draft</span>
                          </td>
                          <td>
                            <span className="pill private">Private</span>
                          </td>
                          <td>Now</td>
                          <td className="row-actions">
                            <Button
                              type="button"
                              variant="secondary"
                              onClick={openRunningGeneration}
                            >
                              View live
                            </Button>
                          </td>
                        </tr>
                      ) : null}
                      {filteredQuestions.map((question) => {
                        const isGenerating = runningGeneration?.questionId === question.id;
                        const isOwned = question.recruiter_uid === currentUser?.uid;
                        return (
                          <tr
                            key={question.id}
                            className={`data-row question-row-compact${isGenerating ? " question-row-generating" : ""}`}
                          >
                        <td>
                          <div className="question-title-cell">
                            <strong>{question.title}</strong>
                            {isGenerating ? (
                              <span className="question-generation-status" role="status">
                                <i aria-hidden="true" />
                                Generating... {generationProgress}%
                              </span>
                            ) : null}
                          </div>
                        </td>
                        <td>
                          <div className="tag-list">
                            {question.tags.length ? (
                              question.tags.slice(0, 6).map((tag) => (
                                <span key={`${question.id}-${tag}`}>{tag}</span>
                              ))
                            ) : (
                              <span className="is-empty">No tags</span>
                            )}
                          </div>
                        </td>
                        <td>
                          {question.metadata_status === "classified" ? (
                            <span className={`question-difficulty-text ${questionDifficultyTone(question.difficulty)}`}>
                              {question.difficulty}
                            </span>
                          ) : (
                            <span className="question-difficulty-text pending">Pending AI</span>
                          )}
                        </td>
                        <td>
                          <span className={`pill ${questionStatusTone(question.status)}`}>
                            {question.status}
                          </span>
                        </td>
                        <td>
                          <span className={`pill ${question.visibility}`}>
                            {question.visibility}
                          </span>
                        </td>
                        <td>{new Date(question.updated_at).toLocaleDateString()}</td>
                        <td className="row-actions">
                          <Button
                            type="button"
                            variant="secondary"
                            onClick={() => openQuestion(question)}
                            disabled={!isOwned}
                            title={isOwned ? undefined : "Public questions from other recruiters are read-only"}
                          >
                            {isOwned ? (isGenerating ? "View live" : "Edit") : "Shared"}
                          </Button>
                        </td>
                          </tr>
                        );
                      })}
                    </>
                  )}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="table-shell">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Group</th>
                    <th>Questions</th>
                    <th>Difficulty mix</th>
                    <th>Topics</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {groupsLoading ? (
                    <tr>
                      <td colSpan={6} className="table-empty">
                        Loading groups...
                      </td>
                    </tr>
                  ) : groups.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="table-empty">
                        No groups yet. Create a group from real question bank items.
                      </td>
                    </tr>
                  ) : groups.map((group) => {
                    const expanded = expandedGroupId === group.id;
                    return (
                      <Fragment key={group.id}>
                        <tr
                          className="data-row"
                          onClick={() => setExpandedGroupId(expanded ? null : group.id)}
                        >
                          <td>
                            <strong>{group.name}</strong>
                          </td>
                          <td>{group.question_count}</td>
                          <td>
                            {group.difficulty_breakdown.easy} Easy, {group.difficulty_breakdown.medium} Medium, {group.difficulty_breakdown.hard} Hard
                          </td>
                          <td>{group.topics.slice(0, 3).join(" • ") || "No topics yet"}</td>
                          <td>
                            <span className={`pill ${group.status}`}>{group.status}</span>
                          </td>
                          <td className="row-actions">
                            <Button
                              type="button"
                              variant="secondary"
                              onClick={(event) => {
                                event.stopPropagation();
                                navigate(
                                  `/recruiter/question-management/groups/new?groupId=${encodeURIComponent(group.id)}`,
                                );
                              }}
                            >
                              Edit
                            </Button>
                            <Button
                              type="button"
                              variant="secondary"
                              onClick={(event) => {
                                event.stopPropagation();
                                setExpandedGroupId(expanded ? null : group.id);
                              }}
                            >
                              View
                            </Button>
                          </td>
                        </tr>
                        {expanded ? (
                          <tr className="detail-row">
                            <td colSpan={6}>
                              <div className="detail-grid">
                                <div>
                                  <span>Total marks</span>
                                  <p>{group.total_marks}</p>
                                </div>
                                <div>
                                  <span>Languages</span>
                                  <p>{group.languages.join(", ") || "No languages yet"}</p>
                                </div>
                                <div>
                                  <span>Questions</span>
                                  <p>{group.questions.map((item) => item.title).join(" • ")}</p>
                                </div>
                                <div>
                                  <span>Updated</span>
                                  <p>{new Date(group.updated_at).toLocaleDateString()}</p>
                                </div>
                              </div>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

      </section>

      {showBulkImportModal ? (
        <div className="modal-backdrop" onClick={closeBulkImportModal}>
          <div
            className="bulk-import-dialog"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="bulk-import-title"
          >
            <Card className="bulk-import-modal">
              <div className="panel-head">
                <div>
                  <p>Bulk CSV upload</p>
                  <h2 id="bulk-import-title">Import questions without spreadsheet stress.</h2>
                </div>
                <Button type="button" variant="secondary" onClick={closeBulkImportModal}>
                  Close
                </Button>
              </div>

              <div className="bulk-import-grid">
                <div className="bulk-upload-box">
                  <label className="field">
                    <span>
                      CSV file <em>Recommended</em>
                    </span>
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      onChange={(event) => void readBulkImportFile(event.target.files?.[0])}
                    />
                  </label>

                  <div className="bulk-template-actions">
                    <Button type="button" variant="secondary" onClick={downloadBulkImportTemplate}>
                      Download Template
                    </Button>
                    <Button
                      type="button"
                      onClick={() => void runBulkImport()}
                      disabled={bulkImportQuestions.isPending}
                    >
                      {bulkImportQuestions.isPending ? "Importing..." : "Import Questions"}
                    </Button>
                  </div>

                  {bulkCsvFileName ? (
                    <p className="bulk-file-name">Selected file: {bulkCsvFileName}</p>
                  ) : (
                    <p className="bulk-file-name">
                      Upload a CSV, or paste rows directly if you are copying from Sheets.
                    </p>
                  )}
                </div>

                <label className="field bulk-paste-field">
                  <span>
                    CSV content <em>Paste fallback</em>
                  </span>
                  <textarea
                    rows={10}
                    value={bulkCsvText}
                    onChange={(event) => {
                      setBulkCsvText(event.target.value);
                      setBulkCsvFileName("");
                      setBulkImportResult(null);
                    }}
                    placeholder="Paste CSV content here if you do not want to choose a file."
                  />
                </label>
              </div>

              <div className="bulk-format-note">
                <strong>Accepted columns</strong>
                <p>{BULK_IMPORT_COLUMNS.join(", ")}</p>
                <span>
                  Required: title, problem_statement, difficulty. Test cases can be JSON arrays or
                  compact pairs like input=&gt;expected separated by ||.
                </span>
              </div>

              {bulkImportError ? <div className="inline-alert">{bulkImportError}</div> : null}

              {bulkImportResult ? (
                <div className="bulk-result-panel">
                  <div className="bulk-result-grid" aria-label="Bulk import result">
                    <div>
                      <span>Total rows</span>
                      <strong>{bulkImportResult.total_rows}</strong>
                    </div>
                    <div>
                      <span>Created</span>
                      <strong>{bulkImportResult.created_count}</strong>
                    </div>
                    <div>
                      <span>Needs review</span>
                      <strong>{bulkImportResult.failed_count}</strong>
                    </div>
                  </div>

                  {bulkImportResult.created.length > 0 ? (
                    <div className="bulk-created-list">
                      <span>Created questions</span>
                      <ul>
                        {bulkImportResult.created.slice(0, 8).map((question) => (
                          <li key={question.id}>
                            <strong>{question.title}</strong>
                            <p>
                              {question.difficulty} · {question.status} ·{" "}
                              {question.sample_test_cases.length + question.hidden_test_cases.length}{" "}
                              tests
                            </p>
                          </li>
                        ))}
                      </ul>
                      {bulkImportResult.created.length > 8 ? (
                        <p className="bulk-file-name">
                          Showing 8 of {bulkImportResult.created.length} created questions.
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  {bulkImportResult.errors.length > 0 ? (
                    <div className="bulk-error-list">
                      <span>Rows to fix</span>
                      <ul>
                        {bulkImportResult.errors.map((rowError) => (
                          <li key={`${rowError.row_number}-${rowError.title || "untitled"}`}>
                            <strong>
                              Row {rowError.row_number}
                              {rowError.title ? ` · ${rowError.title}` : ""}
                            </strong>
                            <p>{rowError.errors.join(" ")}</p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </Card>
          </div>
        </div>
      ) : null}
    </main>
  );
}

export function QuestionCreationFlowPage() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const questionId = searchParams.get("questionId");
  const generationOwnerIdRef = useRef(
    `question-page-${Date.now()}-${Math.random().toString(36).slice(2)}`,
  );
  const mountedRef = useRef(true);
  const generationSessionIdRef = useRef<string | null>(null);
  const restoredGenerationIdRef = useRef<string | null>(null);
  const initialGenerationSession = getQuestionGenerationSession();
  const resumableGenerationSession =
    initialGenerationSession?.questionId === questionId
      ? initialGenerationSession
      : null;

  const createQuestion = useCreateQuestionBankQuestion(currentUser);
  const updateQuestion = useUpdateQuestionBankQuestion(currentUser);
  const deleteQuestion = useDeleteQuestionBankQuestion(currentUser);
  const streamDraftQuestion = useStreamQuestionBankDraft(currentUser);
  const validateDraft = useValidateQuestionBankDraft(currentUser);
  const refineTestCases = useRefineQuestionBankTestCases(currentUser);
  const refineSolution = useRefineQuestionBankSolution(currentUser);
  const { data } = useQuestionBank(currentUser, {
    search: "",
    difficulty: "",
    status: "",
    tag: "",
  });

  const questionItems = data?.items;
  const questions = useMemo(() => questionItems ?? [], [questionItems]);
  const editingQuestion = useMemo(
    () => questions.find((item) => item.id === questionId) ?? null,
    [questionId, questions],
  );

  const [composer, setComposer] = useState<QuestionCreatePayload>(() =>
    resumableGenerationSession
      ? cloneComposer(resumableGenerationSession.baseDraft)
      : createEmptyComposer(),
  );
  const [persistedQuestionId, setPersistedQuestionId] = useState<string | null>(questionId);
  const [generationSettings, setGenerationSettings] = useState<GenerationSettingsState>(() =>
    resumableGenerationSession
      ? structuredClone(resumableGenerationSession.settings)
      : createEmptyGenerationSettings(),
  );
  const [activeStep, setActiveStep] = useState<WizardStep>(1);
  const [statusConfirmed, setStatusConfirmed] = useState(() => Boolean(questionId));
  const [visibilityConfirmed, setVisibilityConfirmed] = useState(() => Boolean(questionId));
  const [visitedSteps, setVisitedSteps] = useState<Set<WizardStep>>(() => new Set([1]));
  const [advanceAttemptedSteps, setAdvanceAttemptedSteps] = useState<Set<WizardStep>>(
    () => new Set(),
  );
  const [assistantMessage, setAssistantMessage] = useState(
    "Move step by step. Each AI action uses the fields already in the builder.",
  );
  const [activityLog, setActivityLog] = useState<ActivityEntry[]>([
    createTimelineEntry("Workspace ready", "Start from any section.", "info"),
  ]);
  const [toolbarBusy, setToolbarBusy] = useState<BusyScope | null>(() =>
    resumableGenerationSession?.status === "running"
      ? (resumableGenerationSession.scope as BusyScope)
      : null,
  );
  const [historyStack, setHistoryStack] = useState<QuestionCreatePayload[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [, setFieldError] = useState("");
  const [showActivityPanel, setShowActivityPanel] = useState(false);
  const [showPublishModal, setShowPublishModal] = useState(false);
  const [checkerInfoOpen, setCheckerInfoOpen] = useState(false);
  const [aiPromptRequest, setAiPromptRequest] = useState<AiPromptRequest | null>(null);
  const [solutionValidation, setSolutionValidation] = useState<SolutionValidationReport | null>(
    null,
  );
  const [solutionValidationStale, setSolutionValidationStale] = useState(false);
  const [singleTestResults, setSingleTestResults] = useState<
    Record<string, SolutionValidationCaseResult>
  >({});
  const [singleTestRunningKey, setSingleTestRunningKey] = useState<string | null>(null);
  const [testCaseEditor, setTestCaseEditor] = useState<TestCaseEditorState | null>(null);
  const [languageValidationReports, setLanguageValidationReports] = useState<
    Record<string, SolutionValidationReport>
  >({});
  const [languageTestRunningKey, setLanguageTestRunningKey] = useState<string | null>(null);
  const [generationProgress, setGenerationProgress] = useState<
    QuestionAIDraftProgressEvent[]
  >(() => resumableGenerationSession?.events ?? []);
  const [fieldToasts, setFieldToasts] = useState<FieldToast[]>([]);
  const latestGenerationEvent = generationProgress[generationProgress.length - 1] ?? null;
  const toastTimerIdsRef = useRef<number[]>([]);
  const dismissFieldToast = useCallback((toastId: number) => {
    setFieldToasts((current) => current.filter((toast) => toast.id !== toastId));
  }, []);
  const notifyFieldError = useCallback((
    message: string,
    tone: FieldToastTone = "warning",
  ) => {
    setFieldError(message);
    const toastId = Date.now() + Math.floor(Math.random() * 1000);
    setFieldToasts((current) => [...current.slice(-2), { id: toastId, message, tone }]);
    const timerId = window.setTimeout(() => {
      dismissFieldToast(toastId);
      toastTimerIdsRef.current = toastTimerIdsRef.current.filter((item) => item !== timerId);
    }, 4500);
    toastTimerIdsRef.current.push(timerId);
  }, [dismissFieldToast]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!toolbarBusy) {
      return;
    }
    document.body.classList.add("question-generation-locked");
    return () => document.body.classList.remove("question-generation-locked");
  }, [toolbarBusy]);

  useEffect(() => {
    return () => {
      toastTimerIdsRef.current.forEach((timerId) => window.clearTimeout(timerId));
    };
  }, []);

  useEffect(() => {
    function restoreGenerationSession(
      session: ReturnType<typeof getQuestionGenerationSession>,
    ) {
      if (
        !session ||
        session.questionId !== questionId ||
        session.ownerId === generationOwnerIdRef.current
      ) {
        return;
      }
      generationSessionIdRef.current = session.id;
      setGenerationProgress(session.events);
      setGenerationSettings(structuredClone(session.settings));
      if (session.status === "running") {
        setToolbarBusy(session.scope as BusyScope);
        return;
      }
      setToolbarBusy(null);
      if (session.status === "failed") {
        if (restoredGenerationIdRef.current !== session.id) {
          restoredGenerationIdRef.current = session.id;
          setAssistantMessage(session.error || "AI generation could not complete.");
          notifyFieldError(session.error || "AI generation could not complete.", "error");
        }
        clearQuestionGenerationSession(session.id);
        return;
      }
      if (
        !session.response ||
        restoredGenerationIdRef.current === session.id ||
        (questionId && !editingQuestion)
      ) {
        return;
      }

      restoredGenerationIdRef.current = session.id;
      const scope = session.scope as DraftScope;
      const response = session.response;
      let restoredComposer = response.draft
        ? mergeDraftIntoComposer(
            session.baseDraft,
            response.draft,
            scope,
            session.settings,
          )
        : cloneComposer(session.baseDraft);
      if (response.solution_validation) {
        restoredComposer = {
          ...restoredComposer,
          validation_report: response.solution_validation,
          validation_status: response.solution_validation.status,
          validation_updated_at: new Date().toISOString(),
        };
        setSolutionValidation(response.solution_validation);
        setSingleTestResults(buildSingleTestResultMap(response.solution_validation));
        setSolutionValidationStale(false);
      }
      setComposer(restoredComposer);
      setAssistantMessage(response.summary || "AI generation completed.");
      const nextStep = nextStepAfterGeneration(scope);
      if (nextStep) {
        setActiveStep(nextStep);
      }
      clearQuestionGenerationSession(session.id);
    }

    const unsubscribe = subscribeQuestionGenerationSession(restoreGenerationSession);
    restoreGenerationSession(getQuestionGenerationSession());
    return unsubscribe;
  }, [editingQuestion, notifyFieldError, questionId]);

  useEffect(() => {
    setVisitedSteps((current) => new Set(current).add(activeStep));
  }, [activeStep]);

  useEffect(() => {
    if (editingQuestion) {
      setComposer(fromRecord(editingQuestion));
      setGenerationSettings((current) => ({
        ...current,
        sample_test_case_count: Math.max(1, editingQuestion.sample_test_cases.length),
        hidden_test_case_count: Math.max(1, editingQuestion.hidden_test_cases.length),
      }));
      setPersistedQuestionId(editingQuestion.id);
      setAssistantMessage(`Editing ${editingQuestion.title}.`);
      setActivityLog((current) => [
        createTimelineEntry("Question loaded", editingQuestion.title, "info"),
        ...current,
      ]);
      setSolutionValidation(editingQuestion.validation_report ?? null);
      setSingleTestResults(buildSingleTestResultMap(editingQuestion.validation_report));
      setLanguageValidationReports({});
      setLanguageTestRunningKey(null);
      setSolutionValidationStale(false);
      setAiPromptRequest(null);
      setStatusConfirmed(false);
      setVisibilityConfirmed(false);
    }
  }, [editingQuestion]);

  const scores = useMemo(() => scoreComposer(composer), [composer]);
  const difficultyIsAgentSet =
    composer.metadata_status === "classified" && composer.difficulty_source === "ai";
  const selectedStep = activeStep;
  const activePromptCopy = aiPromptRequest
    ? getAiPromptCopy(aiPromptRequest.scope, composer)
    : null;
  const activePromptSources = aiPromptRequest
    ? getPromptContextSources(aiPromptRequest.scope, composer, generationSettings)
    : [];
  const generatedLanguageSolutions = useMemo(
    () =>
      Object.entries(composer.reference_solutions ?? {}).filter(
        ([language]) =>
          language.toLowerCase() !== composer.reference_language.toLowerCase(),
      ),
    [composer.reference_language, composer.reference_solutions],
  );
  const draftSaving = createQuestion.isPending || updateQuestion.isPending;
  const singleTestResultValues = useMemo(
    () => Object.values(singleTestResults),
    [singleTestResults],
  );
  const executedTestCount =
    solutionValidation?.results.length ?? singleTestResultValues.length;
  const passedTestCount =
    solutionValidation?.passed_count ??
    singleTestResultValues.filter((result) => result.passed).length;
  const failedTestCount =
    solutionValidation?.failed_count ??
    singleTestResultValues.filter((result) => !result.passed).length;

  function pushActivity(label: string, detail: string, tone: ActivityEntry["tone"]) {
    setActivityLog((current) => [createTimelineEntry(label, detail, tone), ...current].slice(0, 6));
  }

  function assertCanGenerate(scope: DraftScope) {
    const message = getGenerationPrerequisiteError(scope, composer, generationSettings);
    if (message) {
      notifyFieldError(message);
      return false;
    }
    setFieldError("");
    return true;
  }

  function openAiPrompt(scope: DraftScope) {
    if (!assertCanGenerate(scope)) {
      return;
    }
    setFieldError("");
    setAiPromptRequest({
      scope,
      prompt: "",
    });
  }

  function closeAiPrompt() {
    if (toolbarBusy) {
      return;
    }
    setAiPromptRequest(null);
  }

  async function submitAiPrompt() {
    if (!aiPromptRequest) {
      return;
    }

    const request = aiPromptRequest;
    setAiPromptRequest(null);
    await generateDraft(request.scope, request.prompt.trim());
  }

  function invalidateSolutionValidation() {
    setSolutionValidationStale(true);
    setSingleTestResults({});
    setLanguageValidationReports({});
    setComposer((current) => ({
      ...current,
      validation_status:
        current.validation_status === "not_run" ? "not_run" : "stale",
    }));
  }

  function updateLanguageSolutionCode(language: string, sourceCode: string) {
    const normalizedLanguage = languageKey(language);
    setLanguageValidationReports((current) => {
      if (!current[normalizedLanguage]) {
        return current;
      }
      const next = { ...current };
      delete next[normalizedLanguage];
      return next;
    });
    setComposer((current) => {
      const existing = current.reference_solutions[normalizedLanguage];
      if (existing?.source_code === sourceCode) {
        return current;
      }

      const nextStatus: ValidationStatus =
        existing?.validation_status === "not_run" ? "not_run" : "stale";
      const nextArtifact: ReferenceSolutionArtifact = {
        language: normalizedLanguage,
        source_code: sourceCode,
        validation_status: nextStatus,
        time_complexity: existing?.time_complexity || current.time_complexity,
        space_complexity: existing?.space_complexity || current.space_complexity,
        notes: sourceCode.trim()
          ? ["Edited locally. Run tests to refresh this language result."]
          : ["Paste a complete runnable program before running tests."],
      };

      return {
        ...current,
        reference_solutions: {
          ...current.reference_solutions,
          [normalizedLanguage]: nextArtifact,
        },
      };
    });
  }

  function updateField<K extends keyof QuestionCreatePayload>(
    key: K,
    value: QuestionCreatePayload[K],
  ) {
    if (
      [
        "problem_statement",
        "constraints",
        "input_format",
        "input_explanation",
        "output_format",
        "output_explanation",
        "reference_solution",
        "reference_language",
        "answer_validation_mode",
        "output_checker",
        "output_checker_explanation",
      ].includes(String(key))
    ) {
      invalidateSolutionValidation();
    }
    setComposer((current) => ({ ...current, [key]: value }));
  }

  function updateAnswerValidationMode(mode: AnswerValidationMode) {
    invalidateSolutionValidation();
    setComposer((current) => {
      const currentDefault = answerValidationOption(current.answer_validation_mode).detail;
      const nextDefault = answerValidationOption(mode).detail;
      const shouldReplaceExplanation =
        !current.output_checker_explanation.trim() ||
        current.output_checker_explanation.trim() === currentDefault;
      return {
        ...current,
        answer_validation_mode: mode,
        output_checker_explanation: shouldReplaceExplanation
          ? nextDefault
          : current.output_checker_explanation,
        output_checker: answerValidationNeedsCustomChecker(mode)
          ? current.output_checker
          : "",
      };
    });
  }

  function addTestCase(bucket: "sample_test_cases" | "hidden_test_cases") {
    invalidateSolutionValidation();
    setComposer((current) => ({
      ...current,
      [bucket]: [...current[bucket], createEmptyTestCase(bucket === "sample_test_cases")],
    }));
  }

  function removeTestCase(bucket: "sample_test_cases" | "hidden_test_cases", index: number) {
    invalidateSolutionValidation();
    setComposer((current) => ({
      ...current,
      [bucket]: current[bucket].filter((_, testCaseIndex) => testCaseIndex !== index),
    }));
  }

  function openTestCaseEditor(bucket: TestBucket, index: number) {
    const testCase = composer[bucket][index];
    if (!testCase) {
      return;
    }
    setTestCaseEditor({
      bucket,
      index,
      draft: { ...testCase },
      originalResult: singleTestResults[`${bucket}-${index}`] ?? null,
      undoStack: [],
      redoStack: [],
    });
  }

  function closeTestCaseEditor() {
    if (!testCaseEditor) {
      return;
    }
    const resultKey = `${testCaseEditor.bucket}-${testCaseEditor.index}`;
    setSingleTestResults((current) => {
      const next = { ...current };
      if (testCaseEditor.originalResult) {
        next[resultKey] = testCaseEditor.originalResult;
      } else {
        delete next[resultKey];
      }
      return next;
    });
    setTestCaseEditor(null);
  }

  function updateTestCaseEditor(
    field: "input" | "expected_output" | "explanation",
    value: string,
  ) {
    setTestCaseEditor((current) => {
      if (!current || current.draft[field] === value) {
        return current;
      }
      return {
        ...current,
        draft: { ...current.draft, [field]: value },
        undoStack: [...current.undoStack.slice(-49), current.draft],
        redoStack: [],
      };
    });
  }

  function undoTestCaseEdit() {
    setTestCaseEditor((current) => {
      if (!current?.undoStack.length) {
        return current;
      }
      const previous = current.undoStack[current.undoStack.length - 1];
      return {
        ...current,
        draft: previous,
        undoStack: current.undoStack.slice(0, -1),
        redoStack: [current.draft, ...current.redoStack].slice(0, 50),
      };
    });
  }

  function redoTestCaseEdit() {
    setTestCaseEditor((current) => {
      if (!current?.redoStack.length) {
        return current;
      }
      const [next, ...remaining] = current.redoStack;
      return {
        ...current,
        draft: next,
        undoStack: [...current.undoStack.slice(-49), current.draft],
        redoStack: remaining,
      };
    });
  }

  function saveTestCaseEditor() {
    if (!testCaseEditor) {
      return;
    }
    const { bucket, index, draft } = testCaseEditor;
    const resultKey = `${bucket}-${index}`;
    const savedResult = singleTestResults[resultKey];
    const resultMatchesDraft =
      savedResult?.stdin === draft.input &&
      savedResult.expected_output === draft.expected_output;
    invalidateSolutionValidation();
    setComposer((current) => ({
      ...current,
      [bucket]: current[bucket].map((testCase, testCaseIndex) =>
        testCaseIndex === index ? { ...draft } : testCase,
      ),
    }));
    if (savedResult && resultMatchesDraft) {
      setSingleTestResults({ [resultKey]: savedResult });
    }
    setTestCaseEditor(null);
  }

  function removeEditedTestCase() {
    if (!testCaseEditor) {
      return;
    }
    removeTestCase(testCaseEditor.bucket, testCaseEditor.index);
    setTestCaseEditor(null);
  }

  function toggleLanguage(language: (typeof AVAILABLE_LANGUAGES)[number]) {
    const normalizedLanguage = languageKey(language);
    const currentLanguages = normalizeLanguageList(composer.supported_languages);
    const isRemovingLanguage = currentLanguages.includes(normalizedLanguage);
    const nextLanguages = isRemovingLanguage
      ? currentLanguages.filter((item) => item !== normalizedLanguage)
      : [...currentLanguages, normalizedLanguage];
    const safeNextLanguages = nextLanguages.length ? nextLanguages : ["python"];
    const currentReferenceLanguage = languageKey(composer.reference_language);
    const nextReferenceLanguage =
      isRemovingLanguage && normalizedLanguage === currentReferenceLanguage
        ? safeNextLanguages[0] ?? "python"
        : currentReferenceLanguage;

    if (nextReferenceLanguage !== currentReferenceLanguage) {
      invalidateSolutionValidation();
    }
    if (isRemovingLanguage) {
      setLanguageValidationReports((current) => {
        if (!current[normalizedLanguage]) {
          return current;
        }
        const next = { ...current };
        delete next[normalizedLanguage];
        return next;
      });
    }
    setComposer((current) => {
      return syncComposerLanguageState({
        ...current,
        supported_languages: safeNextLanguages,
        reference_language: nextReferenceLanguage,
      });
    });
  }

  function getTestCaseStatusMeta(
    bucket: TestBucket,
    index: number,
    testCase: TestCase,
  ) {
    const result = singleTestResults[`${bucket}-${index}`];
    if (result) {
      return {
        detail: `Last run: ${result.status}`,
        label: result.passed ? "Passed" : "Failed",
        toneClass: result.passed ? "is-passed" : "is-failed",
      };
    }

    if (testCase.input.trim() && testCase.expected_output.trim()) {
      return {
        detail: "Ready for execution",
        label: "Ready",
        toneClass: "is-ready",
      };
    }

    return {
      detail: "Add input and expected output",
      label: "Needs input/output",
      toneClass: "is-needed",
    };
  }

  function validateBasics() {
    const message = getBasicsSetupError(composer, generationSettings);
    setFieldError(message);
    if (message) {
      notifyFieldError(message);
    }
    return !message;
  }

  function getStepNavigationError(step: WizardStep) {
    if (step === 1) {
      return getBasicsSetupError(composer, generationSettings);
    }
    if (step === 2) {
      if (!composer.problem_statement.trim() || composer.problem_statement.trim().length <= 20) {
        return "Add a clear problem statement before moving forward.";
      }
      if (!composer.input_format.trim() || !composer.output_format.trim()) {
        return "Add both input and output formats before moving forward.";
      }
      if (!composer.constraints.trim()) {
        return "Add constraints before moving forward.";
      }
      return "";
    }
    if (step === 3) {
      if (!exactTestCountsSatisfied(composer, generationSettings)) {
        return "Match the requested sample and hidden testcase counts before moving forward.";
      }
      if (!composer.reference_solution.trim()) {
        return "Add or generate the reference solution before moving forward.";
      }
      if (composer.validation_status !== "passed") {
        return "Run all test cases and pass validation before moving forward.";
      }
      return "";
    }
    if (step === 4) {
      return stepIsComplete(4, composer) ? "" : "Generate the selected other language solutions before moving forward.";
    }
    if (!difficultyIsAgentSet) {
      return "Classify difficulty and metadata before final save.";
    }
    return "";
  }

  function getStepVisualState(step: WizardStep) {
    if (!visitedSteps.has(step)) {
      return "untouched";
    }
    if (advanceAttemptedSteps.has(step) && stepIsComplete(step, composer, generationSettings)) {
      return "complete";
    }
    return "in-progress";
  }

  function moveToStep(step: WizardStep) {
    if (step === 6) {
      void saveAndMoveNext(6);
      return;
    }
    setActiveStep(step);
  }

  function goToPreviousStep() {
    if (activeStep === 1) {
      return;
    }
    setActiveStep((activeStep - 1) as WizardStep);
  }

  function goToNextStep() {
    if (activeStep >= 6) {
      return;
    }
    void saveAndMoveNext((activeStep + 1) as WizardStep);
  }

  function draftPersistencePayload(): QuestionCreatePayload {
    return {
      ...cloneComposer(composer),
      status: "draft",
      sample_test_cases: persistableTestCases(composer.sample_test_cases),
      hidden_test_cases: persistableTestCases(composer.hidden_test_cases),
    };
  }

  async function persistQuestionDraft() {
    if (editingQuestion && editingQuestion.status !== "draft") {
      return;
    }

    const payload = draftPersistencePayload();
    const existingId = persistedQuestionId || editingQuestion?.id || null;
    if (existingId) {
      await updateQuestion.mutateAsync({ questionId: existingId, payload });
      return;
    }

    const created = await createQuestion.mutateAsync(payload);
    setPersistedQuestionId(created.id);
  }

  async function saveAndMoveNext(nextStep: WizardStep) {
    const message = getStepNavigationError(activeStep);
    setAdvanceAttemptedSteps((current) => new Set(current).add(activeStep));
    setVisitedSteps((current) => new Set(current).add(activeStep));
    if (message) {
      notifyFieldError(message);
      return;
    }

    try {
      await persistQuestionDraft();
      setAssistantMessage(`Draft saved after Page ${activeStep}.`);
      pushActivity("Draft saved", `Page ${activeStep} changes are stored.`, "success");
      if (nextStep === 6) {
        setStatusConfirmed(false);
        setVisibilityConfirmed(false);
      }
      setActiveStep(nextStep);
    } catch (error) {
      notifyFieldError(
        error instanceof Error ? error.message : "Unable to save the question draft.",
        "error",
      );
      pushActivity("Draft save failed", `Page ${activeStep} was not stored.`, "warning");
    }
  }

  function goToProblemStatement() {
    void saveAndMoveNext(2);
  }

  function generateWholeQuestionFromBasics() {
    if (!validateBasics()) {
      return;
    }

    openAiPrompt("full");
  }

  function snapshotForUndo() {
    setHistoryStack((current) => [composer, ...current].slice(0, 5));
  }

  function undoAiChanges() {
    setHistoryStack((current) => {
      const [previous, ...rest] = current;
      if (!previous) {
        setAssistantMessage("Nothing to undo yet.");
        return current;
      }

      setComposer(previous);
      setAssistantMessage("Restored the previous version.");
      pushActivity("Undo applied", "Reverted the most recent AI change.", "warning");
      return rest;
    });
  }

  function beginTrackedGeneration(
    scope: DraftScope,
    baseDraft: QuestionCreatePayload,
  ) {
    const initialEvent = createInitialGenerationProgressEvent(scope);
    setGenerationProgress([initialEvent]);
    const sessionId = startQuestionGenerationSession({
      ownerId: generationOwnerIdRef.current,
      questionId: persistedQuestionId,
      scope,
      baseDraft,
      settings: generationSettings,
      initialEvent,
    });
    generationSessionIdRef.current = sessionId;
    return sessionId;
  }

  function appendTrackedGenerationEvent(event: QuestionAIDraftProgressEvent) {
    setGenerationProgress((current) => [...current.slice(-119), event]);
    const sessionId = generationSessionIdRef.current;
    if (sessionId) {
      appendQuestionGenerationProgress(sessionId, event);
    }
  }

  async function generateOtherLanguageDrafts(
    recruiterPrompt: string,
    options: LanguageGenerationOptions = {},
  ): Promise<QuestionAIDraftResponse> {
    const progressStart = options.progressStart ?? 5;
    const progressSpan = options.progressSpan ?? 90;
    const appendFinalCompleteEvent = options.appendFinalCompleteEvent ?? true;
    const sourceDraft = syncComposerLanguageState(options.baseDraft ?? composer);
    const primaryLanguage = languageKey(sourceDraft.reference_language);
    const requestedLanguages = normalizeLanguageList(
      options.requestedLanguages ?? sourceDraft.supported_languages,
      primaryLanguage,
    );
    const syncedComposer = syncComposerLanguageState({
      ...sourceDraft,
      supported_languages: requestedLanguages,
    });
    const targetLanguages = requestedLanguages.filter(
      (language) => language !== primaryLanguage,
    );
    let workingDraft = cloneComposer(syncedComposer);
    const failedLanguages: string[] = [];

    if (!targetLanguages.length) {
      return {
        draft: workingDraft,
        summary: "No additional language solutions were requested.",
        notes: ["The primary reference language is already available."],
        solution_validation: workingDraft.validation_report,
      };
    }

    for (const [index, targetLanguage] of targetLanguages.entries()) {
      const displayName = languageDisplayName(targetLanguage);
      const segmentSize = progressSpan / targetLanguages.length;
      const segmentStart = progressStart + index * segmentSize;
      const appendProgress = (event: QuestionAIDraftProgressEvent) => {
        appendTrackedGenerationEvent(event);
      };

      const existing = workingDraft.reference_solutions[targetLanguage];
      if (existing?.source_code.trim() && existing.validation_status === "passed") {
        appendProgress({
          type: "node_complete",
          scope: "other_languages",
          message: `${displayName} solution is already generated and passed validation. Skipping generation.`,
          current_node: `${targetLanguage}_code_generation`,
          next_node: null,
          progress: Math.round(segmentStart + segmentSize),
        });
        continue;
      }

      appendProgress({
        type: "node_start",
        scope: "other_languages",
        message: `${displayName} code is being generated.`,
        current_node: `${targetLanguage}_code_generation`,
        next_node: null,
        progress: Math.round(segmentStart),
      });

      try {
        const requestDraft = cloneComposer(workingDraft);
        requestDraft.supported_languages = [primaryLanguage, targetLanguage];
        const response = await streamDraftQuestion.mutateAsync({
          payload: {
            prompt: buildSingleLanguagePrompt(targetLanguage, recruiterPrompt),
            generation_scope: "other_languages",
            reference_language: primaryLanguage,
            target_language: targetLanguage,
            title_hint: workingDraft.title.trim() || undefined,
            focus_tags: workingDraft.tags,
            current_draft: requestDraft,
            generation_settings: {
              question_count: generationSettings.question_count,
              easy_count: generationSettings.easy_count,
              medium_count: generationSettings.medium_count,
              hard_count: generationSettings.hard_count,
              topics: splitList(generationSettings.topics_text),
              supported_languages: [primaryLanguage, targetLanguage],
              interview_style: generationSettings.interview_style,
              company_style: generationSettings.company_style,
              time_limit_minutes: generationSettings.time_limit_minutes,
              candidate_solve_time_minutes:
                generationSettings.candidate_solve_time_minutes,
              execution_time_limit_seconds:
                generationSettings.execution_time_limit_seconds,
              memory_limit_mb: generationSettings.memory_limit_mb,
              sample_test_case_count: generationSettings.sample_test_case_count,
              hidden_test_case_count: generationSettings.hidden_test_case_count,
              edge_case_count: generationSettings.edge_case_count,
              stress_test_count: generationSettings.stress_test_count,
            },
          },
          onProgress: (event) => {
            const progressWithinLanguage = Math.max(0, Math.min(100, event.progress));
            appendProgress({
              ...event,
              message:
                event.type === "complete" || event.type === "node_complete"
                  ? `${displayName} code response received.`
                  : `${displayName} code is being generated.`,
              current_node: `${targetLanguage}_code_generation`,
              next_node: null,
              progress: Math.round(
                segmentStart + (progressWithinLanguage / 100) * segmentSize,
              ),
            });
          },
          signal: options.signal,
        });

        if (response.error || !response.draft) {
          throw new Error(response.error || `${displayName} generation returned no code.`);
        }

        workingDraft = mergeDraftIntoComposer(
          workingDraft,
          response.draft,
          "other_languages",
          generationSettings,
        );
        setComposer(cloneComposer(workingDraft));
        const artifact = workingDraft.reference_solutions[targetLanguage];
        const generated = Boolean(artifact?.source_code.trim());
        const passed = artifact?.validation_status === "passed";
        if (!generated || !passed) {
          failedLanguages.push(displayName);
        }
        appendProgress({
          type: "node_complete",
          scope: "other_languages",
          message: !generated
            ? `${displayName} code could not be generated.`
            : passed
              ? `${displayName} code generated and validation passed.`
              : `${displayName} code generated, but validation did not pass.`,
          current_node: `${targetLanguage}_code_generation`,
          next_node: null,
          progress: Math.round(segmentStart + segmentSize),
        });
      } catch (error) {
        const message =
          error instanceof Error ? error.message : `${displayName} generation failed.`;
        if (
          message.includes("Security") ||
          message.includes("Data sanitation") ||
          message.includes("Guardrail") ||
          message.includes("violation") ||
          message.includes("alert")
        ) {
          notifyFieldError(message, "error");
        }
        failedLanguages.push(displayName);
        workingDraft.reference_solutions[targetLanguage] = {
          language: targetLanguage,
          source_code: "",
          validation_status: "skipped",
          time_complexity: workingDraft.time_complexity,
          space_complexity: workingDraft.space_complexity,
          notes: [`Generation failed: ${message}`],
        };
        setComposer(cloneComposer(workingDraft));
        appendProgress({
          type: "error",
          scope: "other_languages",
          message: `${displayName} code generation failed. Continuing with the next language.`,
          current_node: `${targetLanguage}_code_generation`,
          next_node: null,
          progress: Math.round(segmentStart + segmentSize),
        });
      }
    }

    const allSucceeded = failedLanguages.length === 0;
    const summary = allSucceeded
      ? "Generated and validated every requested language solution."
      : `Completed language generation. Review: ${failedLanguages.join(", ")}.`;
    if (appendFinalCompleteEvent) {
      appendTrackedGenerationEvent({
        type: "complete",
        scope: "other_languages",
        message: summary,
        current_node: "language_generation_complete",
        next_node: "END",
        progress: 100,
      });
    }

    return {
      draft: workingDraft,
      summary,
      notes: allSucceeded
        ? ["Each language was generated with a separate AI request."]
        : [`Some language solutions need review: ${failedLanguages.join(", ")}.`],
      solution_validation: workingDraft.validation_report,
    };
  }

  async function generateDraft(
    scope: DraftScope,
    recruiterPrompt = "",
  ) {
    let trackedSessionId: string | null = null;
    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      setFieldError("");
      if (!assertCanGenerate(scope)) {
        return;
      }
      setToolbarBusy(scope);
      snapshotForUndo();
      pushActivity(
        "AI prompt submitted",
        getAiPromptCopy(scope, composer).question,
        "info",
      );
      if (scope === "tests_solution" || scope === "full") {
        setSolutionValidation(null);
        setSolutionValidationStale(false);
      }

      const requestComposer = syncComposerLanguageState(composer);
      const primaryLanguage = languageKey(requestComposer.reference_language);
      const selectedLanguages = normalizeLanguageList(
        requestComposer.supported_languages,
        primaryLanguage,
      );
      const fullNeedsAdditionalLanguages =
        scope === "full" && selectedLanguages.some((language) => language !== primaryLanguage);
      const primaryOnlyComposer = fullNeedsAdditionalLanguages
        ? syncComposerLanguageState({
            ...requestComposer,
            supported_languages: [primaryLanguage],
          })
        : requestComposer;
      trackedSessionId = beginTrackedGeneration(scope, requestComposer);
      let response: QuestionAIDraftResponse;
      if (scope === "other_languages") {
        response = await generateOtherLanguageDrafts(recruiterPrompt, { signal: controller.signal });
      } else {
        response = await streamDraftQuestion.mutateAsync({
          payload: {
            prompt: buildSectionPrompt(scope, recruiterPrompt),
            generation_scope: scope,
            reference_language: primaryOnlyComposer.reference_language,
            title_hint: primaryOnlyComposer.title.trim() || undefined,
            focus_tags: primaryOnlyComposer.tags,
            current_draft: primaryOnlyComposer,
            generation_settings: {
              question_count: generationSettings.question_count,
              easy_count: generationSettings.easy_count,
              medium_count: generationSettings.medium_count,
              hard_count: generationSettings.hard_count,
              topics: splitList(generationSettings.topics_text),
              supported_languages: primaryOnlyComposer.supported_languages,
              interview_style: generationSettings.interview_style,
              company_style: generationSettings.company_style,
              time_limit_minutes: generationSettings.time_limit_minutes,
              candidate_solve_time_minutes:
                generationSettings.candidate_solve_time_minutes,
              execution_time_limit_seconds:
                generationSettings.execution_time_limit_seconds,
              memory_limit_mb: generationSettings.memory_limit_mb,
              sample_test_case_count: generationSettings.sample_test_case_count,
              hidden_test_case_count: generationSettings.hidden_test_case_count,
              edge_case_count: generationSettings.edge_case_count,
              stress_test_count: generationSettings.stress_test_count,
            },
          },
          onProgress: (event) => {
            const progressWithinPrimary = Math.max(0, Math.min(100, event.progress));
            const nextEvent = fullNeedsAdditionalLanguages
              ? {
                  ...event,
                  message:
                    event.type === "complete"
                      ? "Primary question is ready. Preparing selected language solutions."
                      : event.message,
                  progress: Math.round(4 + (progressWithinPrimary / 100) * 68),
                }
              : event;
            appendTrackedGenerationEvent(nextEvent);
          },
          signal: controller.signal,
        });
      }

      if (fullNeedsAdditionalLanguages && response.draft && !response.error) {
        const primaryDraft = syncComposerLanguageState({
          ...response.draft,
          supported_languages: selectedLanguages,
        });
        const languageResponse = await generateOtherLanguageDrafts(recruiterPrompt, {
          baseDraft: primaryDraft,
          requestedLanguages: selectedLanguages,
          progressStart: 72,
          progressSpan: 26,
          appendFinalCompleteEvent: false,
          signal: controller.signal,
        });
        const languageDraft = languageResponse.draft ?? primaryDraft;
        const combinedDraft = syncComposerLanguageState({
          ...languageDraft,
          supported_languages: selectedLanguages,
        });
        response = {
          ...response,
          draft: combinedDraft,
          summary: `${response.summary} ${languageResponse.summary}`,
          notes: [...response.notes, ...languageResponse.notes],
          solution_validation:
            response.solution_validation ?? languageResponse.solution_validation,
        };
        appendTrackedGenerationEvent({
          type: "complete",
          scope: "full",
          message: response.summary,
          current_node: "full_generation_complete",
          next_node: "END",
          progress: 100,
          response,
        });
      }

      // Check if generation failed
      if (response.error) {
        if (trackedSessionId) {
          failQuestionGenerationSession(trackedSessionId, response.error);
        }
        notifyFieldError(response.error, "error");
        setAssistantMessage("AI generation failed");
        pushActivity("AI draft failed", response.error, "error");
        return;
      }

      if (trackedSessionId) {
        completeQuestionGenerationSession(trackedSessionId, response);
      }

      // Only merge draft if it was successfully generated
      if (response.draft) {
        const generatedDraft = response.draft;
        if (
          (scope === "solution" || scope === "tests_solution") &&
          !generatedDraft.reference_solution.trim()
        ) {
          notifyFieldError(
            "AI returned tests but did not return runnable solution code. Try Regenerate Solution Code or add a more specific instruction.",
            "warning",
          );
          pushActivity(
            "Solution code missing",
            "The AI response did not include reference solution source code.",
            "warning",
          );
        }
        setComposer((current) =>
          mergeDraftIntoComposer(current, generatedDraft, scope, generationSettings),
        );
        pushActivity("AI draft generated", response.summary, "success");
      }

      if (
        response.solution_validation &&
        (scope === "solution" ||
          scope === "tests" ||
          scope === "examples" ||
          scope === "tests_solution" ||
          scope === "recruiter_validation" ||
          scope === "full")
      ) {
        setSolutionValidation(response.solution_validation);
        setSingleTestResults(buildSingleTestResultMap(response.solution_validation));
        setSolutionValidationStale(false);
        setComposer((current) => ({
          ...current,
          validation_report: response.solution_validation ?? null,
          validation_status: response.solution_validation?.status ?? "not_run",
          validation_updated_at: new Date().toISOString(),
        }));
        pushActivity(
          "Execution validation",
          response.solution_validation.summary,
          response.solution_validation.status === "passed" ? "success" : "warning",
        );
      }

      setAssistantMessage(response.summary);
      if (response.notes.length > 0) {
        pushActivity("AI note", response.notes[0], "info");
      }

      const nextStep = nextStepAfterGeneration(scope);
      if (nextStep) {
        setActiveStep(nextStep);
      }

    } catch (error) {
      const isAbort = error instanceof Error && (error.name === "AbortError" || error.message?.includes("canceled") || error.message?.includes("aborted"));
      if (isAbort) {
        if (trackedSessionId) {
          failQuestionGenerationSession(trackedSessionId, "Generation stopped by user.");
        }
        pushActivity("AI action canceled", "User stopped the generation process.", "warning");
        setAssistantMessage("Generation stopped by user.");
        return;
      }
      const message = error instanceof Error ? error.message : "Unable to generate draft.";
      if (trackedSessionId) {
        failQuestionGenerationSession(trackedSessionId, message);
      }
      notifyFieldError(message, "error");
      setAssistantMessage("AI generation could not complete.");
      pushActivity("AI draft failed", message, "error");
    } finally {
      setToolbarBusy(null);
      if (trackedSessionId && mountedRef.current) {
        clearQuestionGenerationSession(trackedSessionId);
      }
      abortControllerRef.current = null;
    }
  }

  function handleStopGeneration() {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }

  async function validateCurrentDraft() {
    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      setFieldError("");
      const validationError = getValidationPrerequisiteError(composer, generationSettings);
      if (validationError) {
        notifyFieldError(validationError);
        return;
      }
      const requestComposer = cloneComposer(syncComposerLanguageState(composer));
      setGenerationProgress([]);
      setToolbarBusy("validation");
      pushActivity(
        "Test run started",
        "Running the latest saved testcase values against the current reference solution.",
        "info",
      );

      const response = await validateDraft.mutateAsync({
        draft: requestComposer,
        signal: controller.signal,
      });
      const report = response.validation_report;
      setSolutionValidation(report);
      setSingleTestResults(buildSingleTestResultMap(report));
      setSolutionValidationStale(false);
      setComposer((current) => ({
        ...current,
        validation_report: report,
        validation_status: report.status,
        validation_updated_at: new Date().toISOString(),
      }));
      pushActivity(
        "Test run complete",
        report.summary,
        report.status === "passed" ? "success" : "warning",
      );
      setAssistantMessage(report.summary);
      setActiveStep(3);
    } catch (error) {
      const isAbort = error instanceof Error && (error.name === "AbortError" || error.message?.includes("canceled") || error.message?.includes("aborted"));
      if (isAbort) {
        pushActivity("AI action canceled", "User stopped the validation process.", "warning");
        setAssistantMessage("Validation stopped by user.");
        return;
      }
      const message = error instanceof Error ? error.message : "Unable to run test cases.";
      notifyFieldError(message, "error");
      pushActivity("Test run failed", message, "error");
    } finally {
      setToolbarBusy(null);
      abortControllerRef.current = null;
    }
  }

  async function validateLanguageSolution(language: string) {
    const normalizedLanguage = languageKey(language);
    const displayName = languageDisplayName(normalizedLanguage);
    const artifact = composer.reference_solutions[normalizedLanguage];
    const sourceCode = artifact?.source_code ?? "";
    if (!sourceCode.trim()) {
      notifyFieldError(`Add ${displayName} code before running tests.`);
      return;
    }
    if (!exactTestCountsSatisfied(composer, generationSettings)) {
      notifyFieldError("Match the requested sample and hidden testcase counts before running this language.");
      return;
    }

    const languageDraft = cloneComposer(composer);
    languageDraft.reference_solution = sourceCode;
    languageDraft.reference_language = normalizedLanguage;
    languageDraft.validation_report = null;
    languageDraft.validation_status = "not_run";
    languageDraft.supported_languages = Array.from(
      new Set([...languageDraft.supported_languages.map(languageKey), normalizedLanguage]),
    );

    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      setLanguageTestRunningKey(normalizedLanguage);
      setFieldError("");
      pushActivity(
        `${displayName} tests started`,
        "Running this edited solution against the question test cases.",
        "info",
      );
      const response = await validateDraft.mutateAsync({
        draft: languageDraft,
        signal: controller.signal,
      });
      const report = response.validation_report;
      setLanguageValidationReports((current) => ({
        ...current,
        [normalizedLanguage]: report,
      }));
      setComposer((current) => {
        const currentArtifact = current.reference_solutions[normalizedLanguage];
        const nextArtifact: ReferenceSolutionArtifact = {
          language: normalizedLanguage,
          source_code: currentArtifact?.source_code ?? sourceCode,
          validation_status: report.status,
          time_complexity: currentArtifact?.time_complexity || current.time_complexity,
          space_complexity: currentArtifact?.space_complexity || current.space_complexity,
          notes: [
            report.summary,
            ...report.runner_notes.slice(0, 2),
          ].filter(Boolean),
        };
        return {
          ...current,
          reference_solutions: {
            ...current.reference_solutions,
            [normalizedLanguage]: nextArtifact,
          },
        };
      });
      pushActivity(
        `${displayName} tests complete`,
        report.summary,
        report.status === "passed" ? "success" : "warning",
      );
    } catch (error) {
      const isAbort = error instanceof Error && (error.name === "AbortError" || error.message?.includes("canceled") || error.message?.includes("aborted"));
      if (isAbort) {
        pushActivity("AI action canceled", "User stopped the tests process.", "warning");
        return;
      }
      const message =
        error instanceof Error ? error.message : `Unable to validate ${displayName} code.`;
      notifyFieldError(message, "error");
      setComposer((current) => {
        const currentArtifact = current.reference_solutions[normalizedLanguage];
        if (!currentArtifact) {
          return current;
        }
        return {
          ...current,
          reference_solutions: {
            ...current.reference_solutions,
            [normalizedLanguage]: {
              ...currentArtifact,
              validation_status: "failed",
              notes: [`Validation failed: ${message}`],
            },
          },
        };
      });
      pushActivity(`${displayName} tests failed`, message, "error");
    } finally {
      setLanguageTestRunningKey(null);
      abortControllerRef.current = null;
    }
  }

  function applyRefinementReport(response: QuestionDraftRefinementResponse) {
    const report = response.validation_report;
    setSolutionValidation(report);
    setSingleTestResults(buildSingleTestResultMap(report));
    setSolutionValidationStale(false);
    return report;
  }

  function refinementGenerationSettingsPayload() {
    return {
      question_count: generationSettings.question_count,
      easy_count: generationSettings.easy_count,
      medium_count: generationSettings.medium_count,
      hard_count: generationSettings.hard_count,
      topics: splitList(generationSettings.topics_text),
      supported_languages: composer.supported_languages,
      interview_style: generationSettings.interview_style,
      company_style: generationSettings.company_style,
      time_limit_minutes: generationSettings.time_limit_minutes,
      candidate_solve_time_minutes:
        generationSettings.candidate_solve_time_minutes,
      execution_time_limit_seconds:
        generationSettings.execution_time_limit_seconds,
      memory_limit_mb: generationSettings.memory_limit_mb,
      sample_test_case_count: generationSettings.sample_test_case_count,
      hidden_test_case_count: generationSettings.hidden_test_case_count,
      edge_case_count: generationSettings.edge_case_count,
      stress_test_count: generationSettings.stress_test_count,
    };
  }

  async function refineExistingTestCases() {
    const validationError = getTestcaseRepairPrerequisiteError(composer);
    if (validationError) {
      notifyFieldError(validationError);
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      setFieldError("");
      setGenerationProgress([]);
      setToolbarBusy("tests");
      snapshotForUndo();
      pushActivity(
        "Testcase refinement started",
        "Executing existing cases and reviewing expected-output mismatches.",
        "info",
      );
      const response = await refineTestCases.mutateAsync({
        draft: composer,
        generation_settings: refinementGenerationSettingsPayload(),
        signal: controller.signal,
      });
      const report = applyRefinementReport(response);
      setComposer((current) => ({
        ...current,
        sample_test_cases: response.draft.sample_test_cases,
        hidden_test_cases: response.draft.hidden_test_cases,
        reference_solution: response.draft.reference_solution,
        reference_solutions: response.draft.reference_solutions,
        solution_approach: response.draft.solution_approach,
        time_complexity: response.draft.time_complexity,
        space_complexity: response.draft.space_complexity,
        validation_report: report,
        validation_status: report.status,
        validation_updated_at: new Date().toISOString(),
      }));
      setAssistantMessage(response.summary);
      pushActivity(
        "Testcase refinement complete",
        response.summary,
        report.status === "passed" ? "success" : "warning",
      );
    } catch (error) {
      const isAbort = error instanceof Error && (error.name === "AbortError" || error.message?.includes("canceled") || error.message?.includes("aborted"));
      if (isAbort) {
        pushActivity("AI action canceled", "User stopped testcase refinement.", "warning");
        setAssistantMessage("Refinement stopped by user.");
        return;
      }
      const message =
        error instanceof Error ? error.message : "Unable to refine test cases.";
      notifyFieldError(message, "error");
      pushActivity("Testcase refinement failed", message, "error");
    } finally {
      setToolbarBusy(null);
      abortControllerRef.current = null;
    }
  }

  async function refineExistingSolution() {
    const validationError = getValidationPrerequisiteError(
      composer,
      generationSettings,
    );
    if (validationError) {
      notifyFieldError(validationError);
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      setFieldError("");
      setGenerationProgress([]);
      setToolbarBusy("solution");
      snapshotForUndo();
      pushActivity(
        "Solution refinement started",
        "Repairing from the problem contract with failures as diagnostic evidence.",
        "info",
      );
      const response = await refineSolution.mutateAsync({
        draft: composer,
        generation_settings: refinementGenerationSettingsPayload(),
        signal: controller.signal,
      });
      const report = applyRefinementReport(response);
      setComposer((current) => ({
        ...current,
        reference_solution: response.draft.reference_solution,
        validation_report: report,
        validation_status: report.status,
        validation_updated_at: new Date().toISOString(),
      }));
      setAssistantMessage(response.summary);
      pushActivity(
        "Solution refinement complete",
        response.summary,
        report.status === "passed" ? "success" : "warning",
      );
    } catch (error) {
      const isAbort = error instanceof Error && (error.name === "AbortError" || error.message?.includes("canceled") || error.message?.includes("aborted"));
      if (isAbort) {
        pushActivity("AI action canceled", "User stopped solution refinement.", "warning");
        setAssistantMessage("Refinement stopped by user.");
        return;
      }
      const message =
        error instanceof Error ? error.message : "Unable to refine the solution.";
      notifyFieldError(message, "error");
      pushActivity("Solution refinement failed", message, "error");
    } finally {
      setToolbarBusy(null);
      abortControllerRef.current = null;
    }
  }

  async function validateSingleTestCase(
    bucket: TestBucket,
    index: number,
    testCaseOverride?: TestCase,
  ) {
    const testCase = testCaseOverride ?? composer[bucket][index];
    if (!testCase?.input.trim() || !testCase.expected_output.trim()) {
      notifyFieldError("Add input and expected output before running this test case.");
      return;
    }
    if (!composer.reference_solution.trim()) {
      notifyFieldError("Generate or paste a runnable reference solution before running this test case.");
      return;
    }

    const resultKey = `${bucket}-${index}`;
    const singleCaseDraft = cloneComposer(composer);
    singleCaseDraft.sample_test_cases =
      bucket === "sample_test_cases" ? [{ ...testCase, is_sample: true }] : [];
    singleCaseDraft.hidden_test_cases =
      bucket === "hidden_test_cases" ? [{ ...testCase, is_sample: false }] : [];

    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      setSingleTestRunningKey(resultKey);
      setFieldError("");
      const response = await validateDraft.mutateAsync({
        draft: singleCaseDraft,
        signal: controller.signal,
      });
      const result = response.validation_report.results[0];
      if (result) {
        const normalizedResult: SolutionValidationCaseResult = {
          ...result,
          bucket: (bucket === "sample_test_cases" ? "sample" : "hidden") as ValidationBucket,
          index: index + 1,
        };
        setSingleTestResults((current) => ({
          ...current,
          [resultKey]: normalizedResult,
        }));
        pushActivity(
          "Single test executed",
          `${bucket === "sample_test_cases" ? "Sample" : "Hidden"} ${index + 1}: ${normalizedResult.status}`,
          normalizedResult.passed ? "success" : "warning",
        );
      }
    } catch (error) {
      const isAbort = error instanceof Error && (error.name === "AbortError" || error.message?.includes("canceled") || error.message?.includes("aborted"));
      if (isAbort) {
        pushActivity("AI action canceled", "User stopped the single test run.", "warning");
        return;
      }
      const message = error instanceof Error ? error.message : "Unable to run this test case.";
      notifyFieldError(message, "error");
      pushActivity("Single test failed", message, "error");
    } finally {
      setSingleTestRunningKey(null);
      abortControllerRef.current = null;
    }
  }

  function renderSingleTestResult(resultKey: string) {
    const result = singleTestResults[resultKey];
    if (!result) {
      return null;
    }
    return (
      <div className={`single-test-result ${result.passed ? "passed" : "failed"}`}>
        <div className="single-test-result-head">
          <div>
            <span>Last execution</span>
            <strong>{result.passed ? "Passed" : "Failed"}</strong>
          </div>
          <span className="single-test-result-pill">{result.status}</span>
        </div>
        <div className="single-test-result-grid">
          <div>
            <span>Expected</span>
            <pre>{result.expected_output || "(empty)"}</pre>
          </div>
          <div>
            <span>Actual</span>
            <pre>{result.actual_output || "(empty)"}</pre>
          </div>
          <div>
            <span>Runtime</span>
            <pre>{result.execution_time || "n/a"}</pre>
          </div>
        </div>
        {result.stderr || result.compile_output || result.message || result.checker_message ? (
          <div className="single-test-diagnostics">
            {result.checker_message ? (
              <div>
                <span>Checker</span>
                <pre>{result.checker_message}</pre>
              </div>
            ) : null}
            {result.message ? (
              <div>
                <span>Message</span>
                <pre>{result.message}</pre>
              </div>
            ) : null}
            {result.stderr ? (
              <div>
                <span>stderr</span>
                <pre>{result.stderr}</pre>
              </div>
            ) : null}
            {result.compile_output ? (
              <div>
                <span>Compile output</span>
                <pre>{result.compile_output}</pre>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  function renderCompactTestCaseCard(
    bucket: TestBucket,
    testCase: TestCase,
    index: number,
  ) {
    const resultKey = `${bucket}-${index}`;
    const result = singleTestResults[resultKey];
    const statusMeta = getTestCaseStatusMeta(bucket, index, testCase);
    const toneClass = result
      ? result.passed ? "is-passed" : "is-failed"
      : "is-pending";
    const label = bucket === "sample_test_cases" ? "Sample" : "Hidden";

    return (
      <button
        key={`${bucket}-${index}`}
        type="button"
        className={`testcase-summary-card ${toneClass}`}
        onClick={() => openTestCaseEditor(bucket, index)}
        aria-label={`Open ${label} test case ${index + 1}`}
      >
        <div className="testcase-summary-head">
          <div>
            <span>{label} testcase</span>
            <strong>TC {index + 1}</strong>
          </div>
          <em>{statusMeta.label}</em>
        </div>
        <div className="testcase-summary-io">
          <div>
            <span>Input</span>
            <pre>{testCase.input || "(empty)"}</pre>
          </div>
          <div>
            <span>Expected output</span>
            <pre>{testCase.expected_output || "(empty)"}</pre>
          </div>
          <div>
            <span>Actual output</span>
            <pre>{result?.actual_output || (result ? "(empty)" : "Not run yet")}</pre>
          </div>
        </div>
        <div className="testcase-summary-foot">
          <span>{result?.execution_time ? `Runtime ${result.execution_time}` : statusMeta.detail}</span>
          <strong>View details</strong>
        </div>
      </button>
    );
  }

  function renderLanguageValidationReport(report: SolutionValidationReport | undefined) {
    if (!report) {
      return null;
    }

    const firstFailedResult = report.results.find((result) => !result.passed);
    return (
      <div className={`language-test-result ${report.status === "passed" ? "passed" : "failed"}`}>
        <div className="language-test-result-head">
          <div>
            <span>Latest test run</span>
            <strong>{report.status === "passed" ? "Passed" : "Needs fixes"}</strong>
          </div>
          <span className="single-test-result-pill">
            {report.passed_count} passed / {report.failed_count} failed
          </span>
        </div>
        <p>{report.summary}</p>
        {firstFailedResult ? (
          <div className="language-test-brief-grid">
            <div>
              <span>Input</span>
              <pre>{firstFailedResult.stdin || "(empty)"}</pre>
            </div>
            <div>
              <span>Expected</span>
              <pre>{firstFailedResult.expected_output || "(empty)"}</pre>
            </div>
            <div>
              <span>Actual</span>
              <pre>{firstFailedResult.actual_output || "(empty)"}</pre>
            </div>
            <div>
              <span>Diagnostic</span>
              <pre>
                {firstFailedResult.compile_output ||
                  firstFailedResult.stderr ||
                  firstFailedResult.checker_message ||
                  firstFailedResult.message ||
                  firstFailedResult.status}
              </pre>
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  function renderAnswerValidationBadge(compact = false) {
    const option = answerValidationOption(composer.answer_validation_mode);
    const highlighted = composer.answer_validation_mode !== "exact";
    return (
      <button
        type="button"
        className={[
          "answer-validation-badge",
          highlighted ? "is-highlighted" : "",
          compact ? "is-compact" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={() => setCheckerInfoOpen(true)}
      >
        <CheckCircle2 size={16} aria-hidden="true" />
        <span>Answer checker</span>
        <strong>{option.label}</strong>
      </button>
    );
  }

  async function saveQuestion() {
    if (!statusConfirmed) {
      notifyFieldError("Select and confirm the final question status before saving.");
      return;
    }
    if (!visibilityConfirmed) {
      notifyFieldError("Choose whether the question is public or private before saving.");
      return;
    }
    const saveError = getQuestionSaveError(
      composer,
      solutionValidation,
      solutionValidationStale,
    );
    if (saveError) {
      notifyFieldError(saveError);
      return;
    }
    if (
      composer.status === "validated" &&
      !exactTestCountsSatisfied(composer, generationSettings)
    ) {
      notifyFieldError(
        "Validated questions require the sample and hidden testcase counts to match Step 1.",
        "warning",
      );
      return;
    }

    try {
      setFieldError("");
      const existingId = persistedQuestionId || editingQuestion?.id || null;
      if (existingId) {
        await updateQuestion.mutateAsync({
          questionId: existingId,
          payload: composer,
        });
        setAssistantMessage(`Updated ${composer.title}.`);
        pushActivity("Question updated", composer.title, "success");
        navigate("/recruiter/question-management", {
          state: { questionSaveSuccess: `“${composer.title}” was updated with status ${composer.status}.` },
        });
        return;
      }

      const created = await createQuestion.mutateAsync(composer);
      setAssistantMessage(`Created ${created.title}.`);
      pushActivity("Question created", created.title, "success");
      navigate("/recruiter/question-management", {
        state: { questionSaveSuccess: `“${created.title}” was created with status ${created.status}.` },
      });
    } catch (error) {
      notifyFieldError(
        error instanceof Error ? error.message : "Unable to save question.",
        "error",
      );
      pushActivity("Save failed", "Could not persist the question.", "warning");
    }
  }

  function saveQuestionFromWizard() {
    setVisitedSteps((current) => new Set(current).add(6));
    setAdvanceAttemptedSteps((current) => new Set(current).add(6));
    void saveQuestion();
  }

  async function deleteEditingQuestion() {
    if (!editingQuestion) {
      return;
    }

    if (!window.confirm(`Delete "${editingQuestion.title}"?`)) {
      return;
    }

    try {
      setFieldError("");
      await deleteQuestion.mutateAsync(editingQuestion.id);
      navigate("/recruiter/question-management");
    } catch (error) {
      notifyFieldError(
        error instanceof Error ? error.message : "Unable to delete question.",
        "error",
      );
      pushActivity("Delete failed", "Could not delete this question.", "warning");
    }
  }

  return (
    <main className="question-flow-page">
      {fieldToasts.length ? (
        <div className="question-flow-toast-stack" aria-live="polite" aria-label="Question flow notifications">
          {fieldToasts.map((toast) => (
            <div
              key={toast.id}
              className={`question-flow-toast is-${toast.tone}`}
              role="alert"
            >
              <div>
                <strong>{fieldToastTitle(toast)}</strong>
                <p>{toast.message}</p>
              </div>
              <button
                type="button"
                className="question-flow-toast-dismiss"
                onClick={() => dismissFieldToast(toast.id)}
                aria-label="Dismiss notification"
              >
                Close
              </button>
            </div>
          ))}
        </div>
      ) : null}
      <section className="flow-hero flow-hero-compact">
        <div>
          <p>{editingQuestion ? "Edit question" : "New question"}</p>
          <h1>{editingQuestion ? composer.title || "Edit question" : "Create question"}</h1>
        </div>
        <div className="flow-hero-actions">
          <Button type="button" variant="secondary" onClick={() => navigate("/recruiter/question-management")}>
            <ArrowLeft size={16} />
            Back to dashboard
          </Button>
          <Button type="button" variant="secondary" onClick={() => setShowActivityPanel(true)}>
            <Activity size={16} />
            Activity
          </Button>
          {editingQuestion ? (
            <Button
              type="button"
              variant="secondary"
              className="danger-button"
              onClick={() => void deleteEditingQuestion()}
              disabled={deleteQuestion.isPending}
            >
              <Trash2 size={16} />
              {deleteQuestion.isPending ? "Deleting..." : "Delete"}
            </Button>
          ) : null}
        </div>
      </section>

      <section className="flow-grid question-builder-grid">
        <Card className="flow-workbench">
          <div className="question-page-wizard">
            <div className="question-page-rail" aria-label="Question creation pages">
              {STEP_DEFINITIONS.map((step) => {
                const state = getStepVisualState(step.id);
                return (
                  <button
                    key={step.id}
                    type="button"
                    className={[
                      "question-page-step",
                      activeStep === step.id ? "is-active" : "",
                      `is-${state}`,
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    onClick={() => moveToStep(step.id)}
                    aria-current={activeStep === step.id ? "step" : undefined}
                  >
                    <span>{step.id}</span>
                    <strong>{step.title}</strong>
                    <em>
                      {activeStep === step.id
                        ? "Current section"
                        : state === "complete"
                        ? "Done"
                        : state === "untouched"
                          ? "Not visited"
                          : "In progress"}
                    </em>
                  </button>
                );
              })}
            </div>

            <div className="question-page-shell">
          {selectedStep === 1 ? (
          <StepCard
            step={STEP_DEFINITIONS[0]}
            busy={toolbarBusy === "basics"}
          >
            <div className="field-grid">
              <label className="field">
                <span>
                  Title <em>Required</em>
                </span>
                <input
                  value={composer.title}
                  onChange={(event) => updateField("title", event.target.value)}
                  placeholder="Longest Palindromic Substring"
                />
              </label>
            </div>
            <div className="field-grid">
              <div className="field">
                <span>
                  Languages <em>Required</em>
                </span>
                <div className="chip-row">
                  {AVAILABLE_LANGUAGES.map((language) => {
                    const active = composer.supported_languages.includes(language);
                    return (
                      <button
                        key={language}
                        type="button"
                        className={active ? "chip is-active" : "chip"}
                        onClick={() => toggleLanguage(language)}
                      >
                        {language.toUpperCase()}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="field-grid basic-count-grid">
              <label className="field">
                <span>
                  Sample test count <em>Required</em>
                </span>
                <input
                  type="number"
                  min={1}
                  value={generationSettings.sample_test_case_count}
                  onChange={(event) =>
                    setGenerationSettings((current) => ({
                      ...current,
                      sample_test_case_count: Number(event.target.value) || 1,
                    }))
                  }
                />
              </label>
              <label className="field">
                <span>
                  Hidden test count <em>Required</em>
                </span>
                <input
                  type="number"
                  min={1}
                  value={generationSettings.hidden_test_case_count}
                  onChange={(event) =>
                    setGenerationSettings((current) => ({
                      ...current,
                      hidden_test_case_count: Number(event.target.value) || 1,
                    }))
                  }
                />
              </label>
              <label className="field">
                <span>
                  Execution time limit (seconds) <em>Judge0</em>
                </span>
                <input
                  type="number"
                  min={1}
                  value={generationSettings.execution_time_limit_seconds}
                  onChange={(event) => {
                    const value = Number(event.target.value) || 2;
                    updateField("execution_time_limit_seconds", value);
                    setGenerationSettings((current) => ({
                      ...current,
                      execution_time_limit_seconds: value,
                    }));
                  }}
                />
              </label>
            </div>

            <div className="basic-action-row">
              <Button type="button" variant="secondary" onClick={goToProblemStatement}>
                <ArrowRight size={16} />
                Go to Problem Statement
              </Button>
              <Button
                type="button"
                onClick={generateWholeQuestionFromBasics}
                disabled={Boolean(toolbarBusy)}
              >
                <Sparkles size={16} />
                {toolbarBusy === "full" ? "Generating..." : "Generate Full Question Draft"}
              </Button>
            </div>
          </StepCard>
          ) : null}

          {selectedStep === 2 ? (
          <StepCard
            step={STEP_DEFINITIONS[1]}
            busy={toolbarBusy === "problem" || toolbarBusy === "constraints_formats"}
            onGenerate={() => openAiPrompt("problem")}
          >
            <label className="field">
              <span>
                Problem statement <em>Required</em>
              </span>
              <textarea
                rows={8}
                value={composer.problem_statement}
                onChange={(event) => updateField("problem_statement", event.target.value)}
                placeholder="Write the statement the candidate should solve."
              />
            </label>
            <div className="section-action-strip">
              <Button
                type="button"
                variant="secondary"
                onClick={() => void generateDraft("problem")}
                disabled={Boolean(toolbarBusy)}
              >
                <FileText size={16} />
                {toolbarBusy === "problem" ? "Generating..." : "Generate Step 2 Contract"}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => void generateDraft("constraints_formats")}
                disabled={Boolean(toolbarBusy)}
              >
                <Wand2 size={16} />
                {toolbarBusy === "constraints_formats"
                  ? "Generating..."
                  : "Generate Constraints & Formats"}
              </Button>
            </div>
            <div className="field-grid">
              <label className="field">
                <span>
                  Input format <em>Required</em>
                </span>
                <textarea
                  rows={4}
                  value={composer.input_format}
                  onChange={(event) => updateField("input_format", event.target.value)}
                />
              </label>
              <label className="field">
                <span>
                  Output format <em>Required</em>
                </span>
                <textarea
                  rows={4}
                  value={composer.output_format}
                  onChange={(event) => updateField("output_format", event.target.value)}
                />
              </label>
            </div>
            <label className="field">
              <span>
                Constraints <em>Required</em>
              </span>
              <textarea
                rows={4}
                value={composer.constraints}
                onChange={(event) => updateField("constraints", event.target.value)}
                placeholder="0 <= age <= 120"
              />
            </label>
            <div className="question-status-strip" aria-label="Problem readiness">
              <span className={composer.problem_statement.trim().length > 20 ? "is-ready" : "is-needed"}>
                Problem {composer.problem_statement.trim().length > 20 ? "ready" : "needed"}
              </span>
              <span
                className={
                  composer.input_format.trim() && composer.output_format.trim()
                    ? "is-ready"
                    : "is-needed"
                }
              >
                Formats{" "}
                {composer.input_format.trim() && composer.output_format.trim()
                  ? "ready"
                  : "needed"}
              </span>
              <span className={composer.constraints.trim() ? "is-ready" : "is-needed"}>
                Constraints {composer.constraints.trim() ? "ready" : "needed"}
              </span>
            </div>
          </StepCard>
          ) : null}

          {selectedStep === 3 ? (
          <StepCard
            step={STEP_DEFINITIONS[2]}
            busy={
              toolbarBusy === "tests" ||
              toolbarBusy === "tests_solution" ||
              toolbarBusy === "solution" ||
              toolbarBusy === "validation"
            }
          >
            <div className="mode-card-row">
              <Button
                type="button"
                onClick={() => void generateDraft("tests_solution")}
                disabled={Boolean(toolbarBusy)}
              >
                <Sparkles size={16} />
                {toolbarBusy === "tests_solution"
                  ? "Generating..."
                  : "Generate Test Cases & Solution"}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => void refineExistingTestCases()}
                disabled={Boolean(toolbarBusy)}
              >
                <Wand2 size={16} />
                {toolbarBusy === "tests" ? "Refining..." : "Refine Test Cases"}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => void refineExistingSolution()}
                disabled={Boolean(toolbarBusy)}
              >
                <FileText size={16} />
                {toolbarBusy === "solution" ? "Refining..." : "Refine Solution Code"}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => void validateCurrentDraft()}
                disabled={Boolean(toolbarBusy)}
              >
                <Play size={16} />
                {toolbarBusy === "validation" ? "Executing..." : "Run All Test Cases"}
              </Button>
            </div>

            <div className="question-status-strip" aria-label="Test readiness">
              <span
                className={
                  countCompleteTestCases(composer.sample_test_cases) ===
                  generationSettings.sample_test_case_count
                    ? "is-ready"
                    : "is-needed"
                }
              >
                Samples {countCompleteTestCases(composer.sample_test_cases)} /{" "}
                {generationSettings.sample_test_case_count}
              </span>
              <span
                className={
                  countCompleteTestCases(composer.hidden_test_cases) ===
                  generationSettings.hidden_test_case_count
                    ? "is-ready"
                    : "is-needed"
                }
              >
                Hidden {countCompleteTestCases(composer.hidden_test_cases)} /{" "}
                {generationSettings.hidden_test_case_count}
              </span>
              <span
                className={
                  exactTestCountsSatisfied(composer, generationSettings)
                    ? "is-ready"
                    : "is-needed"
                }
              >
                Counts{" "}
                {exactTestCountsSatisfied(composer, generationSettings)
                  ? "matched"
                  : "pending"}
              </span>
            </div>

            <div className="answer-validation-row">
              {renderAnswerValidationBadge()}
            </div>

            <div className="step-three-status-grid">
              <div
                className={[
                  "validation-status-banner",
                  solutionValidation?.status || composer.validation_status || "not_run",
                  solutionValidationStale ? "is-stale" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <span>Execution status</span>
                <strong>
                  {solutionValidation
                    ? solutionValidation.status === "passed"
                      ? "Execution validation passed"
                      : solutionValidation.status === "failed"
                        ? "Execution validation failed"
                        : "Execution validation skipped"
                    : "Execution validation not run"}
                </strong>
                <p>
                  {solutionValidation
                    ? solutionValidation.summary
                    : "Run the reference program against the testcase cards below to see outputs, failures, and diagnostics inline."}
                </p>
                {solutionValidationStale || composer.validation_status === "stale" ? (
                  <span>Results are stale because the solution or testcase values changed.</span>
                ) : null}
              </div>

              <div className="quality-summary">
                <span>Executed</span>
                <strong>{executedTestCount}</strong>
              </div>
              <div className="quality-summary">
                <span>Passed</span>
                <strong>{passedTestCount}</strong>
              </div>
              <div className="quality-summary">
                <span>Failed</span>
                <strong>{failedTestCount}</strong>
              </div>
            </div>

            {solutionValidation?.runner_notes.length ? (
              <div className="runner-note-panel">
                <span>Runner notes</span>
                <div className="runner-note-list">
                  {solutionValidation.runner_notes.map((note) => (
                    <p key={note}>{note}</p>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="section-head">
              <div>
                <h3>Sample tests</h3>
              </div>
              <Button type="button" variant="secondary" onClick={() => addTestCase("sample_test_cases")}>
                <Plus size={16} />
                Add sample
              </Button>
            </div>

            <div className="testcase-stack testcase-summary-grid">
              {composer.sample_test_cases.map((testCase, index) =>
                renderCompactTestCaseCard("sample_test_cases", testCase, index),
              )}
            </div>

            <div className="section-head">
              <div>
                <h3>Hidden tests</h3>
              </div>
              <Button type="button" variant="secondary" onClick={() => addTestCase("hidden_test_cases")}>
                <Plus size={16} />
                Add hidden
              </Button>
            </div>

            <div className="testcase-stack testcase-summary-grid">
              {composer.hidden_test_cases.map((testCase, index) =>
                renderCompactTestCaseCard("hidden_test_cases", testCase, index),
              )}
            </div>

            <div className="field-grid solution-entry-grid step-three-solution-grid">
              <label className="field">
                <span>
                  Reference solution <em>Required</em>
                </span>
                <textarea
                  rows={14}
                  value={composer.reference_solution}
                  onChange={(event) => updateField("reference_solution", event.target.value)}
                  placeholder="Complete runnable program that reads STDIN and prints STDOUT."
                />
              </label>
              <div className="sub-panel step-three-side-panel">
                <label className="field">
                  <span>
                    Reference language <em>Primary</em>
                  </span>
                  <select
                    value={composer.reference_language}
                    onChange={(event) =>
                      updateField(
                        "reference_language",
                        event.target.value as QuestionCreatePayload["reference_language"],
                      )
                    }
                  >
                    {AVAILABLE_LANGUAGES.map((language) => (
                      <option key={language} value={language}>
                        {language.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="field-grid compact-limit-grid">
                  <label className="field">
                    <span>Execution time limit</span>
                    <input
                      type="number"
                      min={1}
                      value={composer.execution_time_limit_seconds}
                      onChange={(event) => {
                        const value = Number(event.target.value) || 2;
                        updateField("execution_time_limit_seconds", value);
                        setGenerationSettings((current) => ({
                          ...current,
                          execution_time_limit_seconds: value,
                        }));
                      }}
                    />
                  </label>
                  <label className="field">
                    <span>Memory limit MB</span>
                    <input
                      type="number"
                      min={64}
                      value={composer.memory_limit_mb}
                      onChange={(event) => {
                        const value = Number(event.target.value) || 64;
                        updateField("memory_limit_mb", value);
                        setGenerationSettings((current) => ({
                          ...current,
                          memory_limit_mb: value,
                        }));
                      }}
                    />
                  </label>
                </div>
                <label className="field">
                  <span>Answer validation</span>
                  <select
                    value={composer.answer_validation_mode}
                    onChange={(event) =>
                      updateAnswerValidationMode(event.target.value as AnswerValidationMode)
                    }
                  >
                    {ANSWER_VALIDATION_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Checker explanation</span>
                  <textarea
                    rows={4}
                    value={composer.output_checker_explanation}
                    onChange={(event) =>
                      updateField("output_checker_explanation", event.target.value)
                    }
                  />
                </label>
                {answerValidationNeedsCustomChecker(composer.answer_validation_mode) ? (
                  <label className="field">
                    <span>
                      Python checker <em>Required</em>
                    </span>
                    <textarea
                      rows={9}
                      value={composer.output_checker}
                      onChange={(event) =>
                        updateField("output_checker", event.target.value)
                      }
                      placeholder="def check_output(stdin, expected_output, actual_output):"
                    />
                  </label>
                ) : null}
              </div>
            </div>

          </StepCard>
          ) : null}

          {selectedStep === 4 ? (
          <StepCard
            step={STEP_DEFINITIONS[3]}
            busy={toolbarBusy === "other_languages"}
            onGenerate={() => openAiPrompt("other_languages")}
          >
            <div className="language-solution-panel">

              <div className="validation-overview-grid compact-check-grid">
                <div className="metadata-pending-box">
                  Primary validation: {composer.validation_status.replace("_", " ")}
                </div>
                <div className="metadata-pending-box">
                  Requested: {composer.supported_languages.join(", ").toUpperCase()}
                </div>
                <div className="metadata-pending-box">
                  Translation gate:{" "}
                  {otherLanguageSolutionsComplete(composer) ? "ready" : "pending"}
                </div>
                <div className="metadata-pending-box answer-validation-overview">
                  {renderAnswerValidationBadge(true)}
                </div>
              </div>

              {generatedLanguageSolutions.length ? (
                <div className="language-solution-stack">
                  {generatedLanguageSolutions.map(([language, artifact]) => {
                    const normalizedLanguage = languageKey(language);
                    const displayName = languageDisplayName(normalizedLanguage);
                    const isRunning = languageTestRunningKey === normalizedLanguage;
                    const report = languageValidationReports[normalizedLanguage];
                    const notes = artifact.notes ?? [];
                    return (
                      <div className="language-solution-card" key={normalizedLanguage}>
                        <div className="language-solution-head">
                          <div>
                            <strong>{displayName}</strong>
                            <p>{notes[0] || "Edit the generated code, then run the tests for this language."}</p>
                          </div>
                          <div className="language-solution-actions">
                            <span className={`pill ${artifact.validation_status}`}>
                              {artifact.validation_status.replace("_", " ")}
                            </span>
                            <Button
                              type="button"
                              variant="secondary"
                              onClick={() => void validateLanguageSolution(normalizedLanguage)}
                              disabled={isRunning || !artifact.source_code.trim()}
                            >
                              <Play size={14} />
                              {isRunning ? "Running..." : "Run tests"}
                            </Button>
                          </div>
                        </div>
                        <div className="language-monaco-shell">
                          <Editor
                            height="360px"
                            language={monacoLanguage(normalizedLanguage)}
                            theme="vs"
                            value={artifact.source_code}
                            loading={
                              <div className="language-editor-loading">Loading editor...</div>
                            }
                            options={{
                              automaticLayout: true,
                              fontFamily:
                                '"SFMono-Regular", Consolas, "Liberation Mono", monospace',
                              fontSize: 14,
                              lineHeight: 22,
                              minimap: { enabled: false },
                              overviewRulerBorder: false,
                              padding: { top: 16, bottom: 16 },
                              renderLineHighlight: "line",
                              renderWhitespace: "selection",
                              smoothScrolling: true,
                              scrollBeyondLastLine: false,
                              tabSize: 2,
                              wordWrap: "on",
                            }}
                            onChange={(value) =>
                              updateLanguageSolutionCode(normalizedLanguage, value || "")
                            }
                          />
                        </div>
                        {renderLanguageValidationReport(report)}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="metadata-pending-box">
                  Select Java, C++, or C in Step 1 and run this step after the primary
                  validation passes.
                </div>
              )}
            </div>
          </StepCard>
          ) : null}

          {selectedStep === 5 ? (
          <StepCard
            step={STEP_DEFINITIONS[4]}
            busy={toolbarBusy === "metadata" || toolbarBusy === "difficulty"}
            onGenerate={() => openAiPrompt("metadata")}
          >
            <div className="assistant-message">{assistantMessage}</div>
            <div className="difficulty-grid metadata-review-grid">
              <div className="difficulty-classifier">
                <p>Metadata</p>
                <h3>{difficultyIsAgentSet ? composer.difficulty.toUpperCase() : "PENDING"}</h3>
                <div className="button-row">
                  <Button
                    type="button"
                    onClick={() => openAiPrompt("metadata")}
                    disabled={Boolean(toolbarBusy)}
                  >
                    <Wand2 size={16} />
                    {toolbarBusy === "metadata" || toolbarBusy === "difficulty"
                      ? "Classifying..."
                      : "Classify Difficulty & Metadata"}
                  </Button>
                </div>
              </div>

              <div className="difficulty-summary">
                <div className="quality-summary">
                  <span>Completion</span>
                  <strong>{scores.completion}%</strong>
                </div>
                <div className="quality-summary">
                  <span>Quality</span>
                  <strong>{scores.quality}%</strong>
                </div>
                <div className="quality-summary">
                  <span>Readiness</span>
                  <strong>{scores.readiness}%</strong>
                </div>
                <div className="quality-summary">
                  <span>AI confidence</span>
                  <strong>{scores.confidence}%</strong>
                </div>
              </div>
            </div>

            <div className="metadata-chip-panel">
              <div>
                <span>Topics</span>
                <p>{composer.topics.join(", ") || "Pending AI"}</p>
              </div>
              <div>
                <span>Tags</span>
                <p>{composer.tags.join(", ") || "Pending AI"}</p>
              </div>
              <div>
                <span>Category</span>
                <p>{composer.category || "Pending AI"}</p>
              </div>
              <div>
                <span>Complexity</span>
                <p>
                  {composer.time_complexity || "Time pending"} /{" "}
                  {composer.space_complexity || "Space pending"}
                </p>
              </div>
            </div>

            <div className="final-preview-grid">
              <div className="preview-card">
                <span>Problem</span>
                <strong>{composer.title || "Untitled question"}</strong>
                <p>{compactValue(composer.problem_statement, "No statement yet")}</p>
              </div>
              <div className="preview-card">
                <span>Tests</span>
                <strong>
                  {countCompleteTestCases(composer.sample_test_cases)} sample /{" "}
                  {countCompleteTestCases(composer.hidden_test_cases)} hidden
                </strong>
                <p>{composer.sample_test_cases[0]?.explanation || "No sample explanation yet"}</p>
              </div>
              <div className="preview-card">
                <span>Validation</span>
                <strong>{composer.validation_status.replace("_", " ")}</strong>
                <p>{solutionValidation?.summary || "No validation report yet"}</p>
              </div>
              <div className="preview-card">
                <span>Solution</span>
                <strong>
                  {composer.supported_languages.length} optimized language
                  {composer.supported_languages.length === 1 ? "" : "s"}
                </strong>
                <p>
                  {composer.time_complexity || "Complexity pending"} /{" "}
                  {composer.space_complexity || "memory pending"}
                </p>
              </div>
            </div>

            <div className="publish-row publish-row-compact">
              <div className="publish-actions">
                <Button type="button" variant="secondary" onClick={undoAiChanges} disabled={!historyStack.length}>
                  Undo AI
                </Button>
              </div>
            </div>
          </StepCard>
          ) : null}

          {selectedStep === 6 ? (
            <section className="question-final-review" aria-label="Final question review">
              <div className="question-final-review-hero">
                <div>
                  <span>Final reviewer check</span>
                  <h3>{composer.title}</h3>
                  <p>{composer.difficulty} · {composer.category || "Uncategorized"}</p>
                </div>
                <div className={`pill ${questionStatusTone(composer.status)}`}>
                  {composer.status}
                </div>
              </div>

              <div className="question-review-summary-grid">
                <div><span>Languages</span><strong>{composer.supported_languages.join(", ")}</strong></div>
                <div><span>Tests</span><strong>{composer.sample_test_cases.length} sample · {composer.hidden_test_cases.length} hidden</strong></div>
                <div><span>Validation</span><strong>{composer.validation_status.replace("_", " ")}</strong></div>
                <div className="question-review-checker-cell">{renderAnswerValidationBadge(true)}</div>
                <div><span>Limits</span><strong>{composer.execution_time_limit_seconds}s · {composer.memory_limit_mb} MB</strong></div>
                <div><span>Visibility</span><strong>{composer.visibility}</strong></div>
              </div>

              <div className="question-review-section">
                <h4>Problem</h4>
                <div className="question-review-copy"><strong>Statement</strong><p>{composer.problem_statement}</p></div>
                <div className="question-review-two-column">
                  <div><strong>Input format</strong><p>{composer.input_format}</p></div>
                  <div><strong>Output format</strong><p>{composer.output_format}</p></div>
                </div>
                <div className="question-review-copy"><strong>Constraints</strong><pre>{composer.constraints}</pre></div>
              </div>

              <div className="question-review-section">
                <h4>Test cases</h4>
                <div className="question-review-test-grid">
                  {[
                    ...composer.sample_test_cases.map((testCase, index) => ({ testCase, index, label: "Sample" })),
                    ...composer.hidden_test_cases.map((testCase, index) => ({ testCase, index, label: "Hidden" })),
                  ].map(({ testCase, index, label }) => (
                    <article key={`${label}-${index}`} className="question-review-test-card">
                      <div><strong>{label} {index + 1}</strong><span>{testCase.is_sample ? "Visible" : "Private"}</span></div>
                      <label>Input<pre>{testCase.input || "(empty)"}</pre></label>
                      <label>Expected output<pre>{testCase.expected_output || "(empty)"}</pre></label>
                      {testCase.explanation ? <p>{testCase.explanation}</p> : null}
                    </article>
                  ))}
                </div>
              </div>

              <div className="question-review-section">
                <h4>Optimized solutions</h4>
                <div className="question-review-solutions">
                  {composer.supported_languages.map((language) => {
                    const normalizedLanguage = languageKey(language);
                    const artifact = composer.reference_solutions[normalizedLanguage];
                    const sourceCode =
                      normalizedLanguage === languageKey(composer.reference_language)
                        ? composer.reference_solution
                        : artifact?.source_code ?? "";
                    return (
                      <article key={language}>
                        <div><strong>{language}</strong><span>{artifact?.validation_status ?? composer.validation_status}</span></div>
                        <pre>{sourceCode || "No solution generated"}</pre>
                      </article>
                    );
                  })}
                </div>
                <div className="question-review-two-column">
                  <div><strong>Time complexity</strong><p>{composer.time_complexity || "Not classified"}</p></div>
                  <div><strong>Space complexity</strong><p>{composer.space_complexity || "Not classified"}</p></div>
                </div>
              </div>

              <div className="question-review-section">
                <h4>Metadata</h4>
                <div className="question-review-summary-grid">
                  <div><span>Difficulty</span><strong>{composer.difficulty}</strong></div>
                  <div><span>Topics</span><strong>{composer.topics.join(", ") || "None"}</strong></div>
                  <div><span>Tags</span><strong>{composer.tags.join(", ") || "None"}</strong></div>
                  <div><span>Category</span><strong>{composer.category || "Uncategorized"}</strong></div>
                </div>
              </div>

            </section>
          ) : null}

              <div className="question-page-footer-nav">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={goToPreviousStep}
                  disabled={activeStep === 1 || draftSaving}
                >
                  <ArrowLeft size={16} />
                  Previous
                </Button>
                {activeStep < 6 ? (
                  <Button type="button" onClick={goToNextStep} disabled={draftSaving || Boolean(toolbarBusy)}>
                    {activeStep === 5
                      ? editingQuestion
                        ? "Save Changes & Review"
                        : "Save & Review"
                      : "Next"}
                    <ArrowRight size={16} />
                  </Button>
                ) : (
                  <Button type="button" onClick={() => setShowPublishModal(true)} disabled={draftSaving}>
                    <Save size={16} />
                    {editingQuestion ? "Update Question" : "Create Question"}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </Card>
      </section>

      {testCaseEditor ? (() => {
        const resultKey = `${testCaseEditor.bucket}-${testCaseEditor.index}`;
        const result = singleTestResults[resultKey];
        const statusMeta = getTestCaseStatusMeta(
          testCaseEditor.bucket,
          testCaseEditor.index,
          testCaseEditor.draft,
        );
        const testLabel =
          testCaseEditor.bucket === "sample_test_cases" ? "Sample" : "Hidden";
        const isRunning = singleTestRunningKey === resultKey;
        return (
          <div
            className="testcase-detail-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget && !isRunning) {
                closeTestCaseEditor();
              }
            }}
          >
            <Card
              className="testcase-detail-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="testcase-detail-title"
            >
              <div className="testcase-detail-toolbar">
                <div className="testcase-detail-history-actions">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={closeTestCaseEditor}
                    disabled={isRunning}
                  >
                    <ArrowLeft size={16} />
                    Back
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={undoTestCaseEdit}
                    disabled={isRunning || !testCaseEditor.undoStack.length}
                    title="Undo testcase edit"
                  >
                    <Undo2 size={16} />
                    Undo
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={redoTestCaseEdit}
                    disabled={isRunning || !testCaseEditor.redoStack.length}
                    title="Redo testcase edit"
                  >
                    <Redo2 size={16} />
                    Redo
                  </Button>
                </div>
                <button
                  type="button"
                  className="testcase-detail-close"
                  onClick={closeTestCaseEditor}
                  disabled={isRunning}
                  aria-label="Close testcase details"
                >
                  <X size={20} aria-hidden="true" />
                </button>
              </div>

              <div className="testcase-detail-heading">
                <div>
                  <span>{testLabel} testcase</span>
                  <h2 id="testcase-detail-title">Test case {testCaseEditor.index + 1}</h2>
                  <p>{statusMeta.detail}</p>
                </div>
                <span className={`testcase-status ${statusMeta.toneClass}`}>
                  {statusMeta.label}
                </span>
              </div>

              <div className="testcase-detail-scroll">
                <div className="field-grid testcase-io-grid">
                  <label className="field">
                    <span>Input</span>
                    <textarea
                      rows={7}
                      value={testCaseEditor.draft.input}
                      disabled={isRunning}
                      onChange={(event) => updateTestCaseEditor("input", event.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>Expected output</span>
                    <textarea
                      rows={7}
                      value={testCaseEditor.draft.expected_output}
                      disabled={isRunning}
                      onChange={(event) =>
                        updateTestCaseEditor("expected_output", event.target.value)
                      }
                    />
                  </label>
                </div>
                <label className="field">
                  <span>Explanation</span>
                  <textarea
                    rows={4}
                    value={testCaseEditor.draft.explanation}
                    disabled={isRunning}
                    onChange={(event) =>
                      updateTestCaseEditor("explanation", event.target.value)
                    }
                  />
                </label>

                <div className="testcase-detail-run-actions">
                  <Button
                    type="button"
                    onClick={() =>
                      void validateSingleTestCase(
                        testCaseEditor.bucket,
                        testCaseEditor.index,
                        testCaseEditor.draft,
                      )
                    }
                    disabled={isRunning}
                  >
                    <Play size={16} />
                    {isRunning ? "Running..." : "Run Test Case"}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={removeEditedTestCase}
                    disabled={isRunning}
                  >
                    <Trash2 size={16} />
                    Remove Test Case
                  </Button>
                </div>

                {result ? renderSingleTestResult(resultKey) : (
                  <div className="testcase-detail-empty-result">
                    Run this testcase to see actual output, runtime, and diagnostics.
                  </div>
                )}
              </div>

              <div className="testcase-detail-footer">
                <span>Changes are applied only when you save.</span>
                <Button type="button" onClick={saveTestCaseEditor} disabled={isRunning}>
                  <Save size={16} />
                  Save Test Case
                </Button>
              </div>
            </Card>
          </div>
        );
      })() : null}

      {toolbarBusy ? (
        <AgentRunOverlay
          scope={toolbarBusy}
          commentary={agentCommentary(toolbarBusy)}
          lines={buildAgentThinkingLines(toolbarBusy)}
          progressEvents={generationProgress}
          latestEvent={latestGenerationEvent}
          onStop={handleStopGeneration}
        />
      ) : null}

      {checkerInfoOpen ? (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setCheckerInfoOpen(false);
            }
          }}
        >
          <Card
            className="answer-checker-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="answer-checker-title"
          >
            <div className="answer-checker-modal-head">
              <div>
                <span>Answer validation</span>
                <h3 id="answer-checker-title">
                  {answerValidationOption(composer.answer_validation_mode).label}
                </h3>
              </div>
              <button
                type="button"
                className="testcase-detail-close"
                onClick={() => setCheckerInfoOpen(false)}
                aria-label="Close answer checker details"
              >
                <X size={20} aria-hidden="true" />
              </button>
            </div>
            <div className="answer-checker-modal-body">
              <p>{answerValidationDescription(composer)}</p>
              <div className="answer-checker-rule-grid">
                <div>
                  <span>Mode</span>
                  <strong>
                    {answerValidationOption(composer.answer_validation_mode).label}
                  </strong>
                </div>
                <div>
                  <span>Expected output role</span>
                  <strong>
                    {composer.answer_validation_mode === "exact"
                      ? "Canonical answer"
                      : "Valid exemplar"}
                  </strong>
                </div>
              </div>
              {composer.output_checker.trim() ? (
                <div className="answer-checker-code">
                  <span>Python checker</span>
                  <pre>{composer.output_checker}</pre>
                </div>
              ) : null}
            </div>
          </Card>
        </div>
      ) : null}

      {aiPromptRequest && activePromptCopy ? (
        <div className="modal-backdrop" onClick={closeAiPrompt}>
          <div
            className="ai-prompt-dialog"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="ai-prompt-title"
          >
            <Card className="ai-prompt-modal">
              <div className="panel-head">
                <div>
                  <p>{activePromptCopy.eyebrow}</p>
                  <h2 id="ai-prompt-title">{activePromptCopy.title}</h2>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={closeAiPrompt}
                  disabled={Boolean(toolbarBusy)}
                >
                  Close
                </Button>
              </div>

              <div className="prompt-source-panel">
                <div className="prompt-source-head">
                  <div>
                    <span>AI will use</span>
                    <strong>Current section context</strong>
                  </div>
                  <p>No prompt is required.</p>
                </div>
                <div className="prompt-source-list">
                  {activePromptSources.map((source) => (
                    <div
                      key={source.label}
                      className={`prompt-source-item ${source.ready ? "is-ready" : "is-empty"}`}
                    >
                      <span>{source.label}</span>
                      <p>{source.value}</p>
                    </div>
                  ))}
                </div>
              </div>

              <label className="field ai-prompt-field">
                <span>
                  Optional instructions <em>Only if needed</em>
                </span>
                <textarea
                  rows={5}
                  value={aiPromptRequest.prompt}
                  onChange={(event) =>
                    setAiPromptRequest((current) =>
                      current ? { ...current, prompt: event.target.value } : current,
                    )
                  }
                  placeholder={activePromptCopy.placeholder}
                />
              </label>

              <div className="prompt-modal-actions">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={closeAiPrompt}
                  disabled={Boolean(toolbarBusy)}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  onClick={() => void submitAiPrompt()}
                  disabled={Boolean(toolbarBusy)}
                >
                  {toolbarBusy === aiPromptRequest.scope
                    ? "Working..."
                    : activePromptCopy.actionLabel}
                </Button>
              </div>
            </Card>
          </div>
        </div>
      ) : null}

      {showActivityPanel ? (
        <div className="modal-backdrop" onClick={() => setShowActivityPanel(false)}>
          <div onClick={(event) => event.stopPropagation()}>
            <Card className="activity-modal">
              <div className="panel-head">
                <div>
                  <p>Activity</p>
                  <h2>Execution timeline</h2>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setShowActivityPanel(false)}
                >
                  Close
                </Button>
              </div>
              <div className="timeline-list timeline-list-modal">
                {activityLog.map((entry) => (
                  <div
                    key={`${entry.label}-${entry.timestamp}`}
                    className={`timeline-item ${entry.tone}`}
                  >
                    <div className="timeline-dot" />
                    <div>
                      <strong>{entry.label}</strong>
                      <p>
                        {entry.detail} <span>{entry.timestamp}</span>
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      ) : null}
      {showPublishModal ? (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !draftSaving) {
              setShowPublishModal(false);
            }
          }}
        >
          <Card
            className="publish-confirmation-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="publish-modal-title"
          >
            <div className="publish-modal-header">
              <h3 id="publish-modal-title">
                {editingQuestion ? "Update Question Details" : "Publish Question"}
              </h3>
              <p>Configure visibility and status for "{composer.title}" before saving.</p>
            </div>

            <div className="publish-modal-body">
              <div className="question-status-manager">
                <div className="question-status-manager-head">
                  <div>
                    <span>Required final decision</span>
                    <strong>Select the question status</strong>
                  </div>
                  {statusConfirmed ? <CheckCircle2 size={20} style={{ color: "#16a34a" }} /> : null}
                </div>
                <div className="question-status-options" role="radiogroup" aria-label="Question status">
                  {[
                    { value: "draft", label: "Draft", detail: "Keep working" },
                    { value: "validated", label: "Validated", detail: "Ready for assessments" },
                    { value: "blocked", label: "Blocked", detail: "Exclude from assessments" },
                    { value: "archived", label: "Archived", detail: "Retain but hide" },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={[
                        "question-status-option",
                        `status-${option.value}`,
                        composer.status === option.value && statusConfirmed ? "is-active" : "",
                      ].filter(Boolean).join(" ")}
                      onClick={() => {
                        updateField("status", option.value as QuestionStatus);
                        setStatusConfirmed(true);
                      }}
                      role="radio"
                      aria-checked={composer.status === option.value && statusConfirmed}
                    >
                      <strong>{option.label}</strong>
                      <span>{option.detail}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="question-status-manager question-visibility-manager" style={{ marginTop: "20px" }}>
                <div className="question-status-manager-head">
                  <div>
                    <span>Required sharing decision</span>
                    <strong>Who can use this question?</strong>
                  </div>
                  {visibilityConfirmed ? <CheckCircle2 size={20} style={{ color: "#16a34a" }} /> : null}
                </div>
                <div className="question-status-options" role="radiogroup" aria-label="Question visibility">
                  {[
                    {
                      value: "private",
                      label: "Private",
                      detail: "Only you can use this question in assessments",
                    },
                    {
                      value: "public",
                      label: "Public",
                      detail: "All recruiters can use this question in assessments",
                    },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={[
                        "question-status-option",
                        `visibility-${option.value}`,
                        composer.visibility === option.value && visibilityConfirmed ? "is-active" : "",
                      ].filter(Boolean).join(" ")}
                      onClick={() => {
                        updateField("visibility", option.value as QuestionVisibility);
                        setVisibilityConfirmed(true);
                      }}
                      role="radio"
                      aria-checked={composer.visibility === option.value && visibilityConfirmed}
                    >
                      <strong>{option.label}</strong>
                      <span>{option.detail}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="publish-modal-footer">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setShowPublishModal(false)}
                disabled={draftSaving}
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={saveQuestionFromWizard}
                disabled={draftSaving || !statusConfirmed || !visibilityConfirmed}
              >
                {draftSaving ? "Saving..." : editingQuestion ? "Save & Update" : "Confirm & Create"}
              </Button>
            </div>
          </Card>
        </div>
      ) : null}
    </main>
  );
}

export function QuestionGroupCreationFlowPage() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedGroupId = searchParams.get("groupId");
  const { data, isLoading } = useQuestionBank(currentUser, {
    search: "",
    difficulty: "",
    status: "",
    tag: "",
  });
  const createGroup = useCreateQuestionGroup(currentUser);
  const updateGroup = useUpdateQuestionGroup(currentUser);
  const { data: groupsData, isLoading: groupsLoading } = useQuestionGroups(
    currentUser,
    {
      search: "",
      status: "",
    },
  );
  const questionItems = data?.items;
  const questions = useMemo(() => questionItems ?? [], [questionItems]);
  const groupItems = groupsData?.items;
  const groups = useMemo(() => groupItems ?? [], [groupItems]);
  const [search, setSearch] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<QuestionGroupStatus>("active");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
  const [sideTab, setSideTab] = useState<GroupSideTab>("selected");
  const [fieldError, setFieldError] = useState("");
  const saving = createGroup.isPending || updateGroup.isPending;
  const editingGroup = groups.find((group) => group.id === editingGroupId);

  const filteredQuestions = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) {
      return questions;
    }
    return questions.filter((question) => {
      const haystack = [question.title, question.tags.join(" "), question.status]
        .join(" ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [questions, search]);

  function toggleQuestion(questionId: string) {
    setSelectedIds((current) =>
      current.includes(questionId)
        ? current.filter((item) => item !== questionId)
        : [...current, questionId],
    );
  }

  function resetGroupForm() {
    setEditingGroupId(null);
    setName("");
    setDescription("");
    setStatus("active");
    setSelectedIds([]);
    setFieldError("");
    setSideTab("selected");
  }

  function editGroup(group: QuestionGroupRecord) {
    setEditingGroupId(group.id);
    setName(group.name);
    setDescription(group.description);
    setStatus(group.status);
    setSelectedIds(group.question_ids);
    setFieldError("");
    setSideTab("selected");
  }

  useEffect(() => {
    if (!requestedGroupId || groupsLoading || editingGroupId === requestedGroupId) {
      return;
    }
    const group = groups.find((item) => item.id === requestedGroupId);
    if (group) {
      editGroup(group);
    }
  }, [editingGroupId, groups, groupsLoading, requestedGroupId]);

  async function saveGroup() {
    if (!name.trim()) {
      setFieldError("Group name is required.");
      return;
    }
    if (!selectedIds.length) {
      setFieldError("Select at least one question from the bank.");
      return;
    }

    try {
      setFieldError("");
      const payload = {
        name: name.trim(),
        description: description.trim(),
        question_ids: selectedIds,
        status,
      };

      if (editingGroupId) {
        await updateGroup.mutateAsync({
          groupId: editingGroupId,
          payload,
        });
      } else {
        await createGroup.mutateAsync(payload);
      }

      navigate("/recruiter/question-management");
    } catch (error) {
      setFieldError(error instanceof Error ? error.message : "Unable to save group.");
    }
  }

  return (
    <main className="question-flow-page">
      <section className="flow-hero flow-hero-compact">
        <div>
          <p>{editingGroup ? "Editing group" : "Question group"}</p>
          <h1>{editingGroup ? editingGroup.name : "Create question group"}</h1>
        </div>
        <div className="flow-hero-actions">
          {editingGroup ? (
            <Button type="button" variant="secondary" onClick={resetGroupForm}>
              New group
            </Button>
          ) : null}
          <Button type="button" variant="secondary" onClick={() => navigate("/recruiter/question-management")}>
            Back to dashboard
          </Button>
          <Button type="button" onClick={() => void saveGroup()} disabled={saving}>
            {saving ? "Saving..." : editingGroup ? "Save Changes" : "Save Group"}
          </Button>
        </div>
      </section>

      <section className="flow-grid group-builder-grid">
        <Card className="flow-workbench">
          {fieldError ? <div className="inline-alert">{fieldError}</div> : null}

          <div className="field-grid">
            <label className="field">
              <span>
                Group name <em>Required</em>
              </span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Intern DSA Set"
              />
            </label>
            <label className="field">
              <span>
                Status <em>Optional</em>
              </span>
              <select value={status} onChange={(event) => setStatus(event.target.value as QuestionGroupStatus)}>
                <option value="active">Active</option>
                <option value="draft">Draft</option>
                <option value="archived">Archived</option>
              </select>
            </label>
          </div>

          <label className="field">
            <span>
              Description <em>Optional</em>
            </span>
            <textarea
              rows={4}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Easy + medium DSA for interns"
            />
          </label>

          <label className="field search-field">
            <span>Search questions</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by title or tag"
            />
          </label>

          <div className="table-shell">
            <table className="data-table">
              <thead>
                <tr>
                  <th />
                  <th>Question</th>
                  <th>Difficulty</th>
                  <th>Status</th>
                  <th>Tags</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={5} className="table-empty">
                      Loading questions...
                    </td>
                  </tr>
                ) : filteredQuestions.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="table-empty">
                      No questions match this filter.
                    </td>
                  </tr>
                ) : (
                  filteredQuestions.map((question) => {
                    const selected = selectedIds.includes(question.id);
                    return (
                      <tr
                        key={question.id}
                        className="data-row"
                        onClick={() => toggleQuestion(question.id)}
                      >
                        <td>
                          <input
                            type="checkbox"
                            checked={selected}
                            onClick={(event) => event.stopPropagation()}
                            onChange={() => toggleQuestion(question.id)}
                          />
                        </td>
                        <td>
                          <strong>{question.title}</strong>
                        </td>
                        <td>
                          <span className={`pill ${question.difficulty}`}>{question.difficulty}</span>
                        </td>
                        <td>
                          <span className={`pill ${question.status}`}>{question.status}</span>
                        </td>
                        <td>{question.tags.slice(0, 3).join(" • ") || "No tags"}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <aside className="flow-sidebar group-flow-sidebar">
          <Card className="sidebar-card group-side-card">
            <div className="side-tabs" role="tablist" aria-label="Group side panel">
              <button
                type="button"
                className={sideTab === "selected" ? "is-active" : ""}
                onClick={() => setSideTab("selected")}
              >
                Selected <strong>{selectedIds.length}</strong>
              </button>
              <button
                type="button"
                className={sideTab === "groups" ? "is-active" : ""}
                onClick={() => setSideTab("groups")}
              >
                Groups <strong>{groups.length}</strong>
              </button>
            </div>

            <div className="panel-head">
              <div>
                <p>{sideTab === "selected" ? "Selection" : "Existing groups"}</p>
                <h2>{sideTab === "selected" ? "Chosen questions" : "Pick to edit"}</h2>
              </div>
              <span>{sideTab === "selected" ? selectedIds.length : groups.length}</span>
            </div>

            {sideTab === "selected" ? (
              <div className="summary-stack">
                {selectedIds.length === 0 ? (
                  <div className="summary-block">
                    <span>Empty</span>
                    <p>Pick at least one question from the bank.</p>
                  </div>
                ) : (
                  selectedIds.map((questionId) => {
                    const question = questions.find((item) => item.id === questionId);
                    if (!question) {
                      return null;
                    }
                    return (
                      <div key={question.id} className="summary-block">
                        <span>{question.difficulty}</span>
                        <strong>{question.title}</strong>
                        <p>{question.tags.join(", ") || "No tags"}</p>
                      </div>
                    );
                  })
                )}
              </div>
            ) : (
              <div className="group-edit-list">
                {groupsLoading ? (
                  <div className="summary-block">
                    <span>Loading</span>
                    <p>Fetching existing groups...</p>
                  </div>
                ) : groups.length === 0 ? (
                  <div className="summary-block">
                    <span>Empty</span>
                    <p>No groups created yet.</p>
                  </div>
                ) : (
                  groups.map((group) => (
                    <article
                      key={group.id}
                      className={[
                        "group-edit-item",
                        group.id === editingGroupId ? "is-selected" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                    >
                      <div>
                        <strong>{group.name}</strong>
                        <span>{group.question_count} questions</span>
                      </div>
                      <span className={`pill ${group.status}`}>{group.status}</span>
                      <Button type="button" variant="secondary" onClick={() => editGroup(group)}>
                        Edit
                      </Button>
                    </article>
                  ))
                )}
              </div>
            )}
          </Card>
        </aside>
      </section>
    </main>
  );
}


export { QuestionManagementPage as AssessmentsPage };
