export type DifficultyLevel = "easy" | "medium" | "hard";
export type QuestionStatus = "draft" | "validated" | "blocked" | "archived";
export type QuestionCreationMode = "manual" | "ai_assisted";
export type QuestionGroupStatus = "draft" | "active" | "archived";
export type MetadataStatus = "pending" | "classified" | "failed";
export type DifficultySource = "legacy" | "ai" | "manual_override";
export type ValidationStatus = "not_run" | "passed" | "failed" | "skipped" | "stale";

export interface QuestionGenerationSettings {
  question_count: number;
  easy_count: number;
  medium_count: number;
  hard_count: number;
  topics: string[];
  supported_languages: string[];
  interview_style: string;
  company_style: string;
  time_limit_minutes: number;
  candidate_solve_time_minutes: number;
  execution_time_limit_seconds: number;
  memory_limit_mb: number;
  sample_test_case_count: number;
  hidden_test_case_count: number;
  edge_case_count: number;
  stress_test_count: number;
}

export interface TestCase {
  input: string;
  expected_output: string;
  is_sample: boolean;
  explanation: string;
}

export interface ReferenceSolutionArtifact {
  language: string;
  source_code: string;
  validation_status: ValidationStatus;
  time_complexity: string;
  space_complexity: string;
  notes: string[];
}

export interface SolutionValidationCaseResult {
  bucket: "sample" | "hidden";
  index: number;
  passed: boolean;
  status: string;
  stdin: string;
  expected_output: string;
  actual_output: string;
  stderr: string;
  compile_output: string;
  message: string;
  token: string;
  execution_time: string;
  memory_kb: number | null;
}

export interface SolutionValidationReport {
  status: ValidationStatus;
  summary: string;
  passed_count: number;
  failed_count: number;
  sample_count: number;
  hidden_count: number;
  runner_notes: string[];
  results: SolutionValidationCaseResult[];
  rounds: SolutionValidationRound[];
}

export interface SolutionValidationRound {
  round_number: number;
  status:
    | "passed"
    | "failed"
    | "repaired"
    | "solution_repaired"
    | "testcase_repaired"
    | "skipped";
  summary: string;
  challenger_summary: string;
  repair_summary: string;
  repair_target: string;
  decision_summary: string;
  added_hidden_test_cases: TestCase[];
  passed_count: number;
  failed_count: number;
  results: SolutionValidationCaseResult[];
}

export interface QuestionRecord {
  id: string;
  recruiter_uid: string;
  title: string;
  problem_statement: string;
  difficulty: DifficultyLevel;
  topics: string[];
  tags: string[];
  category: string;
  constraints: string;
  input_format: string;
  input_explanation: string;
  output_format: string;
  output_explanation: string;
  sample_test_cases: TestCase[];
  hidden_test_cases: TestCase[];
  reference_solution: string;
  reference_language: string;
  supported_languages: string[];
  candidate_solve_time_minutes: number;
  execution_time_limit_seconds: number;
  memory_limit_mb: number;
  metadata_status: MetadataStatus;
  difficulty_source: DifficultySource;
  validation_report: SolutionValidationReport | null;
  validation_status: ValidationStatus;
  validation_updated_at: string | null;
  reference_solutions: Record<string, ReferenceSolutionArtifact>;
  solution_approach: string;
  time_complexity: string;
  space_complexity: string;
  status: QuestionStatus;
  creation_mode: QuestionCreationMode;
  created_at: string;
  updated_at: string;
}

export interface QuestionListResponse {
  items: QuestionRecord[];
  total: number;
}

export interface QuestionBulkImportRequest {
  csv_text: string;
}

export interface QuestionBulkImportRowError {
  row_number: number;
  title: string;
  errors: string[];
}

export interface QuestionBulkImportResponse {
  total_rows: number;
  created_count: number;
  failed_count: number;
  created: QuestionRecord[];
  errors: QuestionBulkImportRowError[];
}

export interface QuestionCreatePayload {
  title: string;
  problem_statement: string;
  difficulty: DifficultyLevel;
  topics: string[];
  tags: string[];
  category: string;
  constraints: string;
  input_format: string;
  input_explanation: string;
  output_format: string;
  output_explanation: string;
  sample_test_cases: TestCase[];
  hidden_test_cases: TestCase[];
  reference_solution: string;
  reference_language: string;
  supported_languages: string[];
  candidate_solve_time_minutes: number;
  execution_time_limit_seconds: number;
  memory_limit_mb: number;
  metadata_status: MetadataStatus;
  difficulty_source: DifficultySource;
  validation_report: SolutionValidationReport | null;
  validation_status: ValidationStatus;
  validation_updated_at: string | null;
  reference_solutions: Record<string, ReferenceSolutionArtifact>;
  solution_approach: string;
  time_complexity: string;
  space_complexity: string;
  status: QuestionStatus;
  creation_mode: QuestionCreationMode;
}

export type QuestionUpdatePayload = QuestionCreatePayload;

export interface QuestionAIDraftRequest {
  prompt: string;
  generation_scope:
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
  difficulty?: DifficultyLevel | "";
  reference_language: string;
  target_language?: string;
  title_hint?: string;
  focus_tags: string[];
  current_draft?: QuestionCreatePayload;
  generation_settings: QuestionGenerationSettings;
}

export interface QuestionAIDraftResponse {
  draft: QuestionCreatePayload | null;
  summary: string;
  notes: string[];
  solution_validation?: SolutionValidationReport | null;
  error?: string;
}

export interface QuestionAIDraftProgressEvent {
  type:
    | "start"
    | "edge"
    | "node_start"
    | "node_complete"
    | "validation_case_start"
    | "validation_case_result"
    | "complete"
    | "error";
  scope: QuestionAIDraftRequest["generation_scope"];
  message: string;
  current_node?: string | null;
  next_node?: string | null;
  progress: number;
  validation_pass?: number;
  test_bucket?: "sample" | "hidden";
  test_index?: number;
  bucket_total?: number;
  overall_index?: number;
  overall_total?: number;
  test_language?: string;
  test_input?: string;
  expected_output?: string;
  actual_output?: string;
  error_message?: string;
  test_outcome?: "running" | "passed" | "wrong" | "error";
  test_status?: string;
  response?: QuestionAIDraftResponse;
}

export interface QuestionDraftValidationRequest {
  draft: QuestionCreatePayload;
}

export interface QuestionDraftValidationResponse {
  validation_report: SolutionValidationReport;
}

export interface QuestionDraftRefinementResponse {
  draft: QuestionCreatePayload;
  validation_report: SolutionValidationReport;
  summary: string;
  repaired_test_case_count: number;
  solution_changed: boolean;
}

export interface QuestionGroupQuestionSummary {
  id: string;
  title: string;
  difficulty: DifficultyLevel;
  status: QuestionStatus;
}

export interface QuestionGroupDifficultyBreakdown {
  easy: number;
  medium: number;
  hard: number;
}

export interface QuestionGroupRecord {
  id: string;
  recruiter_uid: string;
  name: string;
  description: string;
  question_ids: string[];
  status: QuestionGroupStatus;
  questions: QuestionGroupQuestionSummary[];
  question_count: number;
  difficulty_breakdown: QuestionGroupDifficultyBreakdown;
  topics: string[];
  languages: string[];
  total_marks: number;
  created_at: string;
  updated_at: string;
}

export interface QuestionGroupListResponse {
  items: QuestionGroupRecord[];
  total: number;
}

export interface QuestionGroupCreatePayload {
  name: string;
  description: string;
  question_ids: string[];
  status: QuestionGroupStatus;
}

export type QuestionGroupUpdatePayload = QuestionGroupCreatePayload;
