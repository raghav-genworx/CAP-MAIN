import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  FileText,
  Play,
  Plus,
  Save,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { useAuth } from "../auth";
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
} from "./hooks/useQuestionBank";
import type {
  DifficultyLevel,
  QuestionBulkImportResponse,
  QuestionCreatePayload,
  QuestionDraftRefinementResponse,
  QuestionGenerationSettings,
  QuestionAIDraftProgressEvent,
  QuestionGroupRecord,
  QuestionGroupStatus,
  QuestionRecord,
  QuestionStatus,
  SolutionValidationReport,
  SolutionValidationCaseResult,
  TestCase,
} from "./types/QuestionBank";

type DashboardView = "questions" | "groups";
type GroupSideTab = "selected" | "groups";
type WizardStep = 1 | 2 | 3 | 4 | 5;
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

interface GenerationSettingsState
  extends Omit<QuestionGenerationSettings, "topics" | "supported_languages"> {
  topics_text: string;
}

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

const AVAILABLE_LANGUAGES = ["python", "java", "cpp", "c"] as const;
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
  "candidate_solve_time_minutes",
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
    optional: ["AI metadata later"],
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
    required: ["AI classification", "Final approval"],
    optional: ["Save draft"],
    actionLabel: "Classify Difficulty & Metadata",
  },
];

function createEmptyTestCase(isSample = false): TestCase {
  return { input: "", expected_output: "", is_sample: isSample, explanation: "" };
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
    solution_approach: "",
    time_complexity: "",
    space_complexity: "",
    status: "draft",
    creation_mode: "manual",
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
    candidate_solve_time_minutes: "5",
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
      "Preserving formats and constraints unless requested",
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
  return {
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
    solution_approach: question.solution_approach ?? "",
    time_complexity: question.time_complexity ?? "",
    space_complexity: question.space_complexity ?? "",
    status: question.status,
    creation_mode: question.creation_mode,
  };
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
      return 2;
    case "constraints":
    case "constraints_formats":
      return 3;
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
    countCompleteTestCases(composer.sample_test_cases) ===
      generationSettings.sample_test_case_count &&
    countCompleteTestCases(composer.hidden_test_cases) ===
      generationSettings.hidden_test_case_count
  );
}

function otherLanguageSolutionsComplete(composer: QuestionCreatePayload) {
  const primaryLanguage = composer.reference_language.toLowerCase();
  const targetLanguages = composer.supported_languages.filter(
    (language) => language.toLowerCase() !== primaryLanguage,
  );
  if (!targetLanguages.length) {
    return true;
  }

  return targetLanguages.every((language) => {
    const artifact = composer.reference_solutions[language.toLowerCase()];
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
    return "Match the sample and hidden testcase counts before running validation.";
  }
  if (!composer.reference_solution.trim()) {
    return "Generate or paste a runnable reference solution before executing tests.";
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
        title: "Generate problem statement",
        question: "Optional instructions",
        placeholder:
          "Example: Keep the statement short and beginner-friendly.",
        helper: "Leave blank to use title, tags, and languages. Only the statement section is applied.",
        actionLabel: "Generate Problem Statement",
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
    problem: "Generate only the title and problem statement.",
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

function mergeDraftIntoComposer(
  current: QuestionCreatePayload,
  draft: QuestionCreatePayload,
  scope: DraftScope,
  generationSettings?: GenerationSettingsState,
): QuestionCreatePayload {
  if (scope === "full") {
    return {
      ...cloneComposer(draft),
      status: current.status,
      creation_mode: "ai_assisted",
    };
  }

  if (scope === "basics") {
    return {
      ...current,
      title: draft.title || current.title,
      topics: draft.topics.length ? draft.topics : current.topics,
      tags: draft.tags.length ? draft.tags : current.tags,
      category: draft.category || current.category,
      supported_languages: draft.supported_languages.length
        ? draft.supported_languages
        : current.supported_languages,
      creation_mode: "ai_assisted",
    };
  }

  if (scope === "problem" || scope === "problem_field") {
    if (scope === "problem") {
      return {
        ...current,
        title: draft.title || current.title,
        problem_statement: draft.problem_statement || current.problem_statement,
        topics: draft.topics.length ? draft.topics : current.topics,
        tags: draft.tags.length ? draft.tags : current.tags,
        category: draft.category || current.category,
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
      creation_mode: "ai_assisted",
    };
  }

  if (scope === "constraints" || scope === "constraints_formats") {
    return {
      ...current,
      input_format:
        scope === "constraints_formats" ? draft.input_format || current.input_format : current.input_format,
      input_explanation:
        scope === "constraints_formats"
          ? draft.input_explanation || current.input_explanation
          : current.input_explanation,
      output_format:
        scope === "constraints_formats"
          ? draft.output_format || current.output_format
          : current.output_format,
      output_explanation:
        scope === "constraints_formats"
          ? draft.output_explanation || current.output_explanation
          : current.output_explanation,
      constraints: draft.constraints || current.constraints,
      candidate_solve_time_minutes:
        draft.candidate_solve_time_minutes || current.candidate_solve_time_minutes,
      execution_time_limit_seconds:
        draft.execution_time_limit_seconds || current.execution_time_limit_seconds,
      memory_limit_mb: draft.memory_limit_mb || current.memory_limit_mb,
      creation_mode: "ai_assisted",
    };
  }

  if (scope === "examples" || scope === "tests" || scope === "tests_solution") {
    const sampleTarget = generationSettings?.sample_test_case_count;
    const hiddenTarget = generationSettings?.hidden_test_case_count;
    return {
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
      reference_solutions:
        Object.keys(draft.reference_solutions).length > 0
          ? draft.reference_solutions
          : current.reference_solutions,
      solution_approach: draft.solution_approach || current.solution_approach,
      time_complexity: draft.time_complexity || current.time_complexity,
      space_complexity: draft.space_complexity || current.space_complexity,
      creation_mode: "ai_assisted",
    };
  }

  if (scope === "solution") {
    return {
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
    };
  }

  if (scope === "other_languages") {
    return {
      ...current,
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
      creation_mode: "ai_assisted",
    };
  }

  if (scope === "recruiter_validation") {
    return {
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
      reference_solutions:
        Object.keys(draft.reference_solutions).length > 0
          ? {
              ...current.reference_solutions,
              ...draft.reference_solutions,
            }
          : current.reference_solutions,
      creation_mode: "ai_assisted",
    };
  }

  if (scope === "difficulty" || scope === "metadata") {
    return {
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
    };
  }

  return {
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
    reference_solutions:
      Object.keys(draft.reference_solutions).length > 0
        ? draft.reference_solutions
        : current.reference_solutions,
    solution_approach: draft.solution_approach || current.solution_approach,
    time_complexity: draft.time_complexity || current.time_complexity,
    space_complexity: draft.space_complexity || current.space_complexity,
    creation_mode: "ai_assisted",
  };
}

function questionStatusTone(status: QuestionStatus) {
  switch (status) {
    case "validated":
      return "validated";
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
        question.topics.join(" "),
        question.tags.join(" "),
        question.category,
        question.validation_status,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [questions, search]);

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
      <section className="management-hero management-hero-compact">
        <div>
          <p>Question management</p>
          <h1>Question library</h1>
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

      <section className="metrics-grid" aria-label="Question management summary">
        <Card className="metric-card">
          <span>Total Questions</span>
          <strong>{formatCount(metrics.questions)}</strong>
        </Card>
        <Card className="metric-card">
          <span>Validated</span>
          <strong>{formatCount(metrics.validated)}</strong>
        </Card>
        <Card className="metric-card">
          <span>Drafts</span>
          <strong>{formatCount(metrics.drafts)}</strong>
        </Card>
        <Card className="metric-card">
          <span>Groups</span>
          <strong>{formatCount(metrics.groups)}</strong>
        </Card>
      </section>

      <section className="management-grid">
        <Card className="management-panel">
          <div className="panel-head">
            <div>
              <p>{view === "questions" ? "Question library" : "Question groups"}</p>
              <h2>{view === "questions" ? "Questions" : "Reusable groups"}</h2>
            </div>
            <span>{view === "questions" ? filteredQuestions.length : groups.length} rows</span>
          </div>

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

          <label className="field search-field">
            <span>Search</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search title, tag, status, or mode"
            />
          </label>

          {view === "questions" ? (
            <div className="table-shell">
              <table className="data-table question-library-table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Topics</th>
                    <th>Tags / Category</th>
                    <th>Difficulty</th>
                    <th>Validation</th>
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
                  ) : filteredQuestions.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="table-empty">
                        No questions yet. Start with a new question flow.
                      </td>
                    </tr>
                  ) : (
                    filteredQuestions.map((question) => (
                      <tr key={question.id} className="data-row question-row-compact">
                        <td>
                          <div className="question-title-cell">
                            <strong>{question.title}</strong>
                            <span className={`pill ${questionStatusTone(question.status)}`}>
                              {question.status}
                            </span>
                          </div>
                        </td>
                        <td>
                          <div className="tag-list">
                            {question.topics.length ? (
                              question.topics.slice(0, 3).map((topic) => (
                                <span key={`${question.id}-topic-${topic}`}>{topic}</span>
                              ))
                            ) : (
                              <span className="is-empty">Pending AI</span>
                            )}
                          </div>
                        </td>
                        <td>
                          <div className="tag-list">
                            {question.tags.length ? (
                              question.tags.slice(0, 4).map((tag) => (
                                <span key={`${question.id}-${tag}`}>{tag}</span>
                              ))
                            ) : (
                              <span className="is-empty">No tags</span>
                            )}
                            {question.category ? <strong>{question.category}</strong> : null}
                          </div>
                        </td>
                        <td>
                          {question.metadata_status === "classified" ? (
                            <span className={`pill ${questionDifficultyTone(question.difficulty)}`}>
                              {question.difficulty}
                            </span>
                          ) : (
                            <span className="pill pending">Pending AI</span>
                          )}
                        </td>
                        <td>
                          <span className={`pill ${question.validation_status}`}>
                            {question.validation_status.replace("_", " ")}
                          </span>
                        </td>
                        <td>{new Date(question.updated_at).toLocaleDateString()}</td>
                        <td className="row-actions">
                          <Button
                            type="button"
                            variant="secondary"
                            onClick={() => openQuestion(question)}
                          >
                            Edit
                          </Button>
                        </td>
                      </tr>
                    ))
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

  const [composer, setComposer] = useState<QuestionCreatePayload>(createEmptyComposer());
  const [persistedQuestionId, setPersistedQuestionId] = useState<string | null>(questionId);
  const [generationSettings, setGenerationSettings] = useState<GenerationSettingsState>(
    createEmptyGenerationSettings(),
  );
  const [activeStep, setActiveStep] = useState<WizardStep>(1);
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
  const [toolbarBusy, setToolbarBusy] = useState<BusyScope | null>(null);
  const [completedAiScopes, setCompletedAiScopes] = useState<Set<DraftScope>>(new Set());
  const [historyStack, setHistoryStack] = useState<QuestionCreatePayload[]>([]);
  const [, setFieldError] = useState("");
  const [showActivityPanel, setShowActivityPanel] = useState(false);
  const [aiPromptRequest, setAiPromptRequest] = useState<AiPromptRequest | null>(null);
  const [solutionValidation, setSolutionValidation] = useState<SolutionValidationReport | null>(
    null,
  );
  const [solutionValidationStale, setSolutionValidationStale] = useState(false);
  const [singleTestResults, setSingleTestResults] = useState<
    Record<string, SolutionValidationCaseResult>
  >({});
  const [singleTestRunningKey, setSingleTestRunningKey] = useState<string | null>(null);
  const [generationProgress, setGenerationProgress] = useState<
    QuestionAIDraftProgressEvent[]
  >([]);
  const [fieldToasts, setFieldToasts] = useState<FieldToast[]>([]);
  const latestGenerationEvent = generationProgress[generationProgress.length - 1] ?? null;
  const toastTimerIdsRef = useRef<number[]>([]);

  useEffect(() => {
    return () => {
      toastTimerIdsRef.current.forEach((timerId) => window.clearTimeout(timerId));
    };
  }, []);

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
      setCompletedAiScopes(new Set());
      setAssistantMessage(`Editing ${editingQuestion.title}.`);
      setActivityLog((current) => [
        createTimelineEntry("Question loaded", editingQuestion.title, "info"),
        ...current,
      ]);
      setSolutionValidation(editingQuestion.validation_report ?? null);
      setSingleTestResults(buildSingleTestResultMap(editingQuestion.validation_report));
      setSolutionValidationStale(false);
      setAiPromptRequest(null);
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

  function dismissFieldToast(toastId: number) {
    setFieldToasts((current) => current.filter((toast) => toast.id !== toastId));
  }

  function notifyFieldError(message: string, tone: FieldToastTone = "warning") {
    setFieldError(message);
    const toastId = Date.now() + Math.floor(Math.random() * 1000);
    setFieldToasts((current) => [...current.slice(-2), { id: toastId, message, tone }]);
    const timerId = window.setTimeout(() => {
      dismissFieldToast(toastId);
      toastTimerIdsRef.current = toastTimerIdsRef.current.filter((item) => item !== timerId);
    }, 4500);
    toastTimerIdsRef.current.push(timerId);
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

    await generateDraft(aiPromptRequest.scope, aiPromptRequest.prompt.trim());
    setAiPromptRequest(null);
  }

  function invalidateSolutionValidation() {
    setSolutionValidationStale(true);
    setSingleTestResults({});
    setComposer((current) => ({
      ...current,
      validation_status:
        current.validation_status === "not_run" ? "not_run" : "stale",
    }));
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
      ].includes(String(key))
    ) {
      invalidateSolutionValidation();
    }
    setComposer((current) => ({ ...current, [key]: value }));
  }

  function updateTestCase(
    bucket: "sample_test_cases" | "hidden_test_cases",
    index: number,
    field: keyof TestCase,
    value: string,
  ) {
    invalidateSolutionValidation();
    setComposer((current) => ({
      ...current,
      [bucket]: current[bucket].map((testCase, testCaseIndex) =>
        testCaseIndex === index ? { ...testCase, [field]: value } : testCase,
      ),
    }));
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

  function toggleLanguage(language: (typeof AVAILABLE_LANGUAGES)[number]) {
    invalidateSolutionValidation();
    setComposer((current) => {
      const next = current.supported_languages.includes(language)
        ? current.supported_languages.filter((item) => item !== language)
        : [...current.supported_languages, language];

      return {
        ...current,
        supported_languages: next.length ? next : ["python"],
        reference_language:
          current.reference_language === language ? next[0] ?? "python" : current.reference_language,
      };
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
    setActiveStep(step);
  }

  function goToPreviousStep() {
    if (activeStep === 1) {
      return;
    }
    setActiveStep((activeStep - 1) as WizardStep);
  }

  function goToNextStep() {
    if (activeStep >= 5) {
      return;
    }
    void saveAndMoveNext((activeStep + 1) as WizardStep);
  }

  async function saveAndMoveNext(nextStep: WizardStep) {
    const message = getStepNavigationError(activeStep);
    setAdvanceAttemptedSteps((current) => new Set(current).add(activeStep));
    setVisitedSteps((current) => new Set(current).add(activeStep));
    if (message) {
      notifyFieldError(message);
      return;
    }
    await saveDraftProgress(nextStep);
  }

  function goToProblemStatement() {
    if (!validateBasics()) {
      return;
    }

    setAdvanceAttemptedSteps((current) => new Set(current).add(1));
    setActiveStep(2);
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

  async function generateDraft(
    scope: DraftScope,
    recruiterPrompt = "",
  ) {
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

      setGenerationProgress([createInitialGenerationProgressEvent(scope)]);
      const response = await streamDraftQuestion.mutateAsync({
        payload: {
        prompt: buildSectionPrompt(scope, recruiterPrompt),
        generation_scope: scope,
        reference_language: composer.reference_language,
        title_hint: composer.title.trim() || undefined,
        focus_tags: composer.tags,
        current_draft: composer,
        generation_settings: {
          question_count: generationSettings.question_count,
          easy_count: generationSettings.easy_count,
          medium_count: generationSettings.medium_count,
          hard_count: generationSettings.hard_count,
          topics: splitList(generationSettings.topics_text),
          supported_languages: composer.supported_languages,
          interview_style: generationSettings.interview_style,
          company_style: generationSettings.company_style,
          time_limit_minutes: generationSettings.time_limit_minutes,
          candidate_solve_time_minutes: generationSettings.candidate_solve_time_minutes,
          execution_time_limit_seconds: generationSettings.execution_time_limit_seconds,
          memory_limit_mb: generationSettings.memory_limit_mb,
          sample_test_case_count: generationSettings.sample_test_case_count,
          hidden_test_case_count: generationSettings.hidden_test_case_count,
          edge_case_count: generationSettings.edge_case_count,
          stress_test_count: generationSettings.stress_test_count,
        },
        },
        onProgress: (event) =>
          setGenerationProgress((current) => [...current.slice(-10), event]),
      });

      // Check if generation failed
      if (response.error) {
        notifyFieldError(response.error, "error");
        setAssistantMessage("AI generation failed");
        pushActivity("AI draft failed", response.error, "error");
        return;
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
        setCompletedAiScopes((current) => {
          const next = new Set(current);
          if (scope === "full") {
            (
              [
                "basics",
                "problem",
                "constraints_formats",
                "constraints",
                "examples",
                "tests",
                "tests_solution",
                "solution",
                "recruiter_validation",
                "other_languages",
                "difficulty",
                "metadata",
              ] as DraftScope[]
            ).forEach((item) => next.add(item));
          } else {
            next.add(scope);
            if (
              scope === "tests" ||
              scope === "examples" ||
              scope === "tests_solution"
            ) {
              next.add("constraints");
              next.add("examples");
              next.add("tests");
              if (scope === "tests_solution") {
                next.add("tests_solution");
                next.add("solution");
              }
            }
            if (scope === "solution") {
              next.add("solution");
            }
            if (scope === "examples") {
              next.add("constraints");
            }
            if (scope === "constraints_formats") {
              next.add("constraints");
            }
            if (scope === "recruiter_validation") {
              next.add("solution");
            }
            if (scope === "metadata") {
              next.add("difficulty");
            }
          }
          return next;
        });
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
      const message = error instanceof Error ? error.message : "Unable to generate draft.";
      notifyFieldError(message, "error");
      setAssistantMessage("AI generation could not complete.");
      pushActivity("AI draft failed", message, "error");
    } finally {
      setToolbarBusy(null);
    }
  }

  async function validateCurrentDraft() {
    try {
      setFieldError("");
      const validationError = getValidationPrerequisiteError(composer, generationSettings);
      if (validationError) {
        notifyFieldError(validationError);
        return;
      }
      setGenerationProgress([]);
      setToolbarBusy("validation");
      pushActivity("Validation started", "Running reference solution against test cases.", "info");

      const response = await validateDraft.mutateAsync({ draft: composer });
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
        "Validation complete",
        report.summary,
        report.status === "passed" ? "success" : "warning",
      );
      setAssistantMessage(report.summary);
      setActiveStep(3);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to validate draft.";
      notifyFieldError(message, "error");
      pushActivity("Validation failed", message, "error");
    } finally {
      setToolbarBusy(null);
    }
  }

  function applyRefinementReport(response: QuestionDraftRefinementResponse) {
    const report = response.validation_report;
    setSolutionValidation(report);
    setSingleTestResults(buildSingleTestResultMap(report));
    setSolutionValidationStale(false);
    return report;
  }

  async function refineExistingTestCases() {
    const validationError = getValidationPrerequisiteError(
      composer,
      generationSettings,
    );
    if (validationError) {
      notifyFieldError(validationError);
      return;
    }

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
      const response = await refineTestCases.mutateAsync({ draft: composer });
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
      const message =
        error instanceof Error ? error.message : "Unable to refine test cases.";
      notifyFieldError(message, "error");
      pushActivity("Testcase refinement failed", message, "error");
    } finally {
      setToolbarBusy(null);
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
      const response = await refineSolution.mutateAsync({ draft: composer });
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
      const message =
        error instanceof Error ? error.message : "Unable to refine the solution.";
      notifyFieldError(message, "error");
      pushActivity("Solution refinement failed", message, "error");
    } finally {
      setToolbarBusy(null);
    }
  }

  async function validateSingleTestCase(bucket: TestBucket, index: number) {
    const testCase = composer[bucket][index];
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

    try {
      setSingleTestRunningKey(resultKey);
      setFieldError("");
      const response = await validateDraft.mutateAsync({ draft: singleCaseDraft });
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
      const message = error instanceof Error ? error.message : "Unable to run this test case.";
      notifyFieldError(message, "error");
      pushActivity("Single test failed", message, "error");
    } finally {
      setSingleTestRunningKey(null);
    }
  }

  function buildProgressPayload(): QuestionCreatePayload {
    const payload = cloneComposer(composer);
    payload.status = "draft";
    payload.creation_mode = "ai_assisted";
    if (payload.title.trim().length < 3) {
      payload.title = "Untitled question draft";
    }
    if (payload.problem_statement.trim().length < 20) {
      payload.problem_statement =
        "Draft in progress. Complete the problem statement before validation.";
    }
    return payload;
  }

  async function saveDraftProgress(nextStep?: WizardStep) {
    try {
      setFieldError("");
      const payload = buildProgressPayload();
      const existingId = persistedQuestionId || editingQuestion?.id || null;
      if (existingId) {
        const updated = await updateQuestion.mutateAsync({
          questionId: existingId,
          payload,
        });
        setPersistedQuestionId(updated.id);
        setAssistantMessage(`Saved draft progress for ${updated.title}.`);
        pushActivity("Draft saved", updated.title, "success");
      } else {
        const created = await createQuestion.mutateAsync(payload);
        setPersistedQuestionId(created.id);
        navigate(
          `/recruiter/question-management/new?questionId=${encodeURIComponent(created.id)}`,
          { replace: true },
        );
        setAssistantMessage(`Saved draft progress for ${created.title}.`);
        pushActivity("Draft saved", created.title, "success");
      }
      if (nextStep) {
        setActiveStep(nextStep);
      }
    } catch (error) {
      notifyFieldError(
        error instanceof Error ? error.message : "Unable to save draft progress.",
        "error",
      );
      pushActivity("Save failed", "Could not persist this draft step.", "warning");
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
        {result.stderr || result.compile_output || result.message ? (
          <div className="single-test-diagnostics">
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

  async function saveQuestion() {
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
        return;
      }

      const created = await createQuestion.mutateAsync(composer);
      setAssistantMessage(`Created ${created.title}.`);
      pushActivity("Question created", created.title, "success");
      navigate("/recruiter/question-management");
    } catch (error) {
      notifyFieldError(
        error instanceof Error ? error.message : "Unable to save question.",
        "error",
      );
      pushActivity("Save failed", "Could not persist the question.", "warning");
    }
  }

  function saveQuestionFromWizard() {
    setVisitedSteps((current) => new Set(current).add(5));
    setAdvanceAttemptedSteps((current) => new Set(current).add(5));
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
                <strong>{toast.tone === "error" ? "Error" : "Check this"}</strong>
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
                      {state === "complete"
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
              <div className="question-page-header">
                <div>
                  <p>Page {activeStep} of {STEP_DEFINITIONS.length}</p>
                  <h2>{STEP_DEFINITIONS[activeStep - 1].title}</h2>
                </div>
                <div className="question-page-nav">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={goToPreviousStep}
                    disabled={activeStep === 1 || draftSaving}
                  >
                    <ArrowLeft size={16} />
                    Previous
                  </Button>
                  {activeStep < 5 ? (
                    <Button type="button" onClick={goToNextStep} disabled={draftSaving || Boolean(toolbarBusy)}>
                      {draftSaving ? "Saving..." : "Next"}
                      <ArrowRight size={16} />
                    </Button>
                  ) : (
                    <Button type="button" onClick={saveQuestionFromWizard}>
                      <Save size={16} />
                      {editingQuestion ? "Save Changes" : "Save Question"}
                    </Button>
                  )}
                </div>
              </div>

          {selectedStep === 1 ? (
          <StepCard
            step={STEP_DEFINITIONS[0]}
            active={selectedStep === 1}
            visualState={getStepVisualState(1)}
            busy={toolbarBusy === "basics"}
            onToggle={() => setActiveStep(1)}
            completed={
              completedAiScopes.has("basics") ||
              stepIsComplete(1, composer, generationSettings)
            }
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
              <label className="field">
                <span>
                  AI metadata <em>Generated later</em>
                </span>
                <div className="metadata-pending-box">
                  {composer.metadata_status === "classified"
                    ? `${composer.difficulty.toUpperCase()} • ${composer.topics.join(", ") || "topics"}`
                    : "Difficulty, topics, tags, and category will be classified in Step 5."}
                </div>
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
            active={selectedStep === 2}
            visualState={getStepVisualState(2)}
            busy={toolbarBusy === "problem" || toolbarBusy === "constraints_formats"}
            onToggle={() => setActiveStep(2)}
            completed={stepIsComplete(2, composer)}
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
                {toolbarBusy === "problem" ? "Generating..." : "Generate Problem Statement Alone"}
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
                  Input explanation <em>Recommended</em>
                </span>
                <textarea
                  rows={4}
                  value={composer.input_explanation}
                  onChange={(event) => updateField("input_explanation", event.target.value)}
                  placeholder="Explain what every input value represents."
                />
              </label>
            </div>
            <div className="field-grid">
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
              <label className="field">
                <span>
                  Output explanation <em>Recommended</em>
                </span>
                <textarea
                  rows={4}
                  value={composer.output_explanation}
                  onChange={(event) => updateField("output_explanation", event.target.value)}
                  placeholder="Explain exactly what should be printed."
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
            active={selectedStep === 3}
            visualState={getStepVisualState(3)}
            busy={
              toolbarBusy === "tests" ||
              toolbarBusy === "tests_solution" ||
              toolbarBusy === "solution" ||
              toolbarBusy === "validation"
            }
            onToggle={() => setActiveStep(3)}
            completed={
              completedAiScopes.has("tests_solution") ||
              stepIsComplete(3, composer, generationSettings)
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
                <p>Keep the case data, actual output, and diagnostics together on each card.</p>
                <h3>Sample tests</h3>
              </div>
              <Button type="button" variant="secondary" onClick={() => addTestCase("sample_test_cases")}>
                <Plus size={16} />
                Add sample
              </Button>
            </div>

            <div className="testcase-stack">
              {composer.sample_test_cases.map((testCase, index) => {
                const statusMeta = getTestCaseStatusMeta(
                  "sample_test_cases",
                  index,
                  testCase,
                );

                return (
                <div key={`sample-${index}`} className="testcase-card">
                  <div className="testcase-head">
                    <div className="testcase-heading-copy">
                      <strong>Sample {index + 1}</strong>
                      <p className="testcase-caption">{statusMeta.detail}</p>
                      <span className={`testcase-status ${statusMeta.toneClass}`}>
                        {statusMeta.label}
                      </span>
                    </div>
                    <div className="testcase-actions">
                      <button
                        type="button"
                        className="link-button"
                        disabled={singleTestRunningKey === `sample_test_cases-${index}`}
                        onClick={() => void validateSingleTestCase("sample_test_cases", index)}
                      >
                        <Play size={13} />
                        {singleTestRunningKey === `sample_test_cases-${index}` ? "Running..." : "Run"}
                      </button>
                      <button type="button" className="link-button" onClick={() => removeTestCase("sample_test_cases", index)}>
                        <Trash2 size={13} />
                        Remove
                      </button>
                    </div>
                  </div>
                  <div className="field-grid testcase-io-grid">
                    <label className="field">
                      <span>Input</span>
                      <textarea
                        rows={3}
                        value={testCase.input}
                        onChange={(event) =>
                          updateTestCase("sample_test_cases", index, "input", event.target.value)
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Expected output</span>
                      <textarea
                        rows={3}
                        value={testCase.expected_output}
                        onChange={(event) =>
                          updateTestCase(
                            "sample_test_cases",
                            index,
                            "expected_output",
                            event.target.value,
                          )
                        }
                      />
                    </label>
                  </div>
                  <label className="field">
                    <span>Explanation</span>
                    <textarea
                      rows={2}
                      value={testCase.explanation}
                      onChange={(event) =>
                        updateTestCase(
                          "sample_test_cases",
                          index,
                          "explanation",
                          event.target.value,
                        )
                      }
                    />
                  </label>
                  {renderSingleTestResult(`sample_test_cases-${index}`)}
                </div>
              )})}
            </div>

            <div className="section-head">
              <div>
                <p>Hidden cases keep the same run feedback inline without moving to a separate result area.</p>
                <h3>Hidden tests</h3>
              </div>
              <Button type="button" variant="secondary" onClick={() => addTestCase("hidden_test_cases")}>
                <Plus size={16} />
                Add hidden
              </Button>
            </div>

            <div className="testcase-stack">
              {composer.hidden_test_cases.map((testCase, index) => {
                const statusMeta = getTestCaseStatusMeta(
                  "hidden_test_cases",
                  index,
                  testCase,
                );

                return (
                <div key={`hidden-${index}`} className="testcase-card subtle">
                  <div className="testcase-head">
                    <div className="testcase-heading-copy">
                      <strong>Hidden {index + 1}</strong>
                      <p className="testcase-caption">{statusMeta.detail}</p>
                      <span className={`testcase-status ${statusMeta.toneClass}`}>
                        {statusMeta.label}
                      </span>
                    </div>
                    <div className="testcase-actions">
                      <button
                        type="button"
                        className="link-button"
                        disabled={singleTestRunningKey === `hidden_test_cases-${index}`}
                        onClick={() => void validateSingleTestCase("hidden_test_cases", index)}
                      >
                        <Play size={13} />
                        {singleTestRunningKey === `hidden_test_cases-${index}` ? "Running..." : "Run"}
                      </button>
                      <button type="button" className="link-button" onClick={() => removeTestCase("hidden_test_cases", index)}>
                        <Trash2 size={13} />
                        Remove
                      </button>
                    </div>
                  </div>
                  <div className="field-grid testcase-io-grid">
                    <label className="field">
                      <span>Input</span>
                      <textarea
                        rows={3}
                        value={testCase.input}
                        onChange={(event) =>
                          updateTestCase("hidden_test_cases", index, "input", event.target.value)
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Expected output</span>
                      <textarea
                        rows={3}
                        value={testCase.expected_output}
                        onChange={(event) =>
                          updateTestCase(
                            "hidden_test_cases",
                            index,
                            "expected_output",
                            event.target.value,
                          )
                        }
                      />
                    </label>
                  </div>
                  <label className="field">
                    <span>Explanation</span>
                    <textarea
                      rows={2}
                      value={testCase.explanation}
                      onChange={(event) =>
                        updateTestCase(
                          "hidden_test_cases",
                          index,
                          "explanation",
                          event.target.value,
                        )
                      }
                    />
                  </label>
                  {renderSingleTestResult(`hidden_test_cases-${index}`)}
                </div>
              )})}
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
                <div className="contract-note">
                  <span>CodeChef-style contract</span>
                  <p>
                    Candidate and reference code must be complete programs: read STDIN,
                    print STDOUT, and never print prompts like "Enter number:".
                  </p>
                </div>
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
                    <span>Candidate solve time</span>
                    <input
                      type="number"
                      min={1}
                      value={composer.candidate_solve_time_minutes}
                      onChange={(event) => {
                        const value = Number(event.target.value) || 1;
                        updateField("candidate_solve_time_minutes", value);
                        setGenerationSettings((current) => ({
                          ...current,
                          candidate_solve_time_minutes: value,
                          time_limit_minutes: value,
                        }));
                      }}
                    />
                  </label>
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
                <div className="metadata-pending-box">
                  Each testcase card below shows the latest actual output, pass or fail state,
                  runtime, and any compiler or runtime diagnostics from the most recent run.
                </div>
              </div>
            </div>

          </StepCard>
          ) : null}

          {selectedStep === 4 ? (
          <StepCard
            step={STEP_DEFINITIONS[3]}
            active={selectedStep === 4}
            visualState={getStepVisualState(4)}
            busy={toolbarBusy === "other_languages"}
            onToggle={() => setActiveStep(4)}
            completed={stepIsComplete(4, composer)}
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
              </div>

              {generatedLanguageSolutions.length ? (
                <div className="language-solution-grid">
                  {generatedLanguageSolutions.map(([language, artifact]) => (
                    <div className="language-solution-card" key={language}>
                      <div className="language-solution-head">
                        <strong>{language.toUpperCase()}</strong>
                        <span className={`pill ${artifact.validation_status}`}>
                          {artifact.validation_status.replace("_", " ")}
                        </span>
                      </div>
                      {artifact.notes.length ? (
                        <p>{artifact.notes[0]}</p>
                      ) : (
                        <p>Generated for recruiter review.</p>
                      )}
                      <textarea
                        readOnly
                        rows={10}
                        value={artifact.source_code || "Generation failed or validation was skipped."}
                        aria-label={`${language} reference solution`}
                      />
                    </div>
                  ))}
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
            active={selectedStep === 5}
            visualState={getStepVisualState(5)}
            busy={toolbarBusy === "metadata" || toolbarBusy === "difficulty"}
            onToggle={() => setActiveStep(5)}
            completed={difficultyIsAgentSet}
            onGenerate={() => openAiPrompt("metadata")}
          >
            <div className="assistant-message">{assistantMessage}</div>
            <div className="difficulty-grid metadata-review-grid">
              <div className="difficulty-classifier">
                <p>AI metadata classifier</p>
                <h3>{difficultyIsAgentSet ? composer.difficulty.toUpperCase() : "PENDING"}</h3>
                <span>
                  Difficulty, topics, tags, and category are generated only after the
                  final problem, tests, solution, and validation result are ready.
                </span>
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

            <div className="readiness-note">
              <strong>Save rules</strong>
              <p>
                Drafts need a title and problem statement. Validated questions also need
                passing execution validation and final AI metadata classification.
              </p>
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
                <strong>{composer.reference_language.toUpperCase()}</strong>
                <p>{composer.solution_approach || "Approach pending AI classification"}</p>
              </div>
            </div>

            <div className="publish-row publish-row-compact">
              <div className="field">
                <span>
                  Status <em>Optional</em>
                </span>
                <select
                  value={composer.status}
                  onChange={(event) => updateField("status", event.target.value as QuestionStatus)}
                >
                  <option value="draft">Draft</option>
                  <option value="validated">Validated</option>
                  <option value="archived">Archived</option>
                </select>
              </div>
              <div className="field">
                <span>
                  Reference language <em>Optional</em>
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
              </div>
              <div className="publish-actions">
                <Button type="button" variant="secondary" onClick={undoAiChanges} disabled={!historyStack.length}>
                  Undo AI
                </Button>
                <Button type="button" onClick={saveQuestionFromWizard}>
                  {editingQuestion ? "Save Changes" : "Save Question"}
                </Button>
              </div>
            </div>
          </StepCard>
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
                {activeStep < 5 ? (
                  <Button type="button" onClick={goToNextStep} disabled={draftSaving || Boolean(toolbarBusy)}>
                    {draftSaving ? "Saving..." : "Next"}
                    <ArrowRight size={16} />
                  </Button>
                ) : (
                  <Button type="button" onClick={saveQuestionFromWizard}>
                    <Save size={16} />
                    {editingQuestion ? "Save Changes" : "Save Question"}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </Card>
      </section>

      {toolbarBusy ? (
        <AgentRunOverlay
          scope={toolbarBusy}
          commentary={agentCommentary(toolbarBusy)}
          lines={buildAgentThinkingLines(toolbarBusy)}
          progressEvents={generationProgress}
          latestEvent={latestGenerationEvent}
        />
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

function AgentRunOverlay({
  scope,
  commentary,
  lines,
  progressEvents,
  latestEvent,
}: {
  scope: BusyScope;
  commentary: string;
  lines: string[];
  progressEvents: QuestionAIDraftProgressEvent[];
  latestEvent: QuestionAIDraftProgressEvent | null;
}) {
  const title =
    scope === "full"
      ? "Generating full question draft"
      : scope === "validation"
        ? "Running execution validation"
        : "Generating section";
  const showLiveProgress = Boolean(latestEvent);
  const liveUpdates = progressEvents.slice(-5);
  const liveCommentary = latestEvent?.message || commentary;
  const progressValue = latestEvent?.progress ?? null;

  return (
    <div className="agent-run-backdrop" role="status" aria-live="polite">
      <Card className="agent-run-modal">
        <div className="agent-run-head">
          <div className="agent-orb" aria-hidden="true" />
          <div>
            <span>{scope === "validation" ? "Validation" : "Generation"}</span>
            <h2>{title}</h2>
            <p>{liveCommentary}</p>
          </div>
        </div>
        {showLiveProgress && progressValue !== null ? (
          <div className="agent-run-progress" aria-live="polite">
            <div className="agent-run-progress-head">
              <div>
                <span>Live progress</span>
                <strong>{latestEvent?.next_node || latestEvent?.current_node || "working"}</strong>
              </div>
              <em>{progressValue}%</em>
            </div>
            <div
              className="agent-run-progress-track"
              role="progressbar"
              aria-label="AI generation progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progressValue}
            >
              <span style={{ width: `${progressValue}%` }} />
            </div>
          </div>
        ) : null}
        {showLiveProgress ? (
          <div className="agent-thinking-list">
            {liveUpdates.map((event, index) => (
              <div
                key={`${event.type}-${event.current_node || "start"}-${index}`}
                className={[
                  "agent-thinking-line",
                  index === liveUpdates.length - 1 ? "is-active" : "is-complete",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <span aria-hidden="true" />
                <p>{event.message}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="agent-thinking-list">
            {lines.map((line, index) => (
              <div
                key={line}
                className={index === 0 ? "agent-thinking-line is-active" : "agent-thinking-line"}
              >
                <span aria-hidden="true" />
                <p>
                  {line}
                  <b className="thinking-dots" aria-hidden="true" />
                </p>
              </div>
            ))}
          </div>
        )}
        <p className="agent-run-foot">
          Keep this page open. This popup now tracks the live agent updates, and
          the builder will apply the accepted fields automatically when the run finishes.
        </p>
      </Card>
    </div>
  );
}

function StepCard({
  step,
  active,
  visualState = "untouched",
  busy = false,
  completed = false,
  onToggle,
  onGenerate,
  children,
}: {
  step: StepDefinition;
  active: boolean;
  visualState?: "untouched" | "in-progress" | "complete";
  busy?: boolean;
  completed?: boolean;
  onToggle: () => void;
  onGenerate?: () => void;
  children: React.ReactNode;
}) {
  return (
    <Card
      className={[
        "step-card",
        active ? "is-active" : "",
        completed ? "is-complete" : "",
        `is-${visualState}`,
        busy ? "is-loading" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="step-card-header">
        <button type="button" className="step-card-toggle" onClick={onToggle}>
          <div>
            <p>
              {busy
                ? "Agent loading"
                : visualState === "complete"
                  ? "Section complete"
                  : visualState === "untouched"
                    ? "Not visited"
                    : `Step ${step.id} in progress`}
            </p>
            <h3>{step.title}</h3>
          </div>
        </button>
        {onGenerate ? (
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={(event) => {
              event.stopPropagation();
              onGenerate();
            }}
          >
            <Sparkles size={16} />
            {busy ? "Working..." : step.actionLabel}
          </Button>
        ) : null}
      </div>
      {active ? (
        <div className="step-card-body">
          {children}
        </div>
      ) : null}
    </Card>
  );
}

export { QuestionManagementPage as AssessmentsPage };
