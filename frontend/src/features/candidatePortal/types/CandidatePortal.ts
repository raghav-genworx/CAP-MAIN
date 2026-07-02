export interface CandidateInviteVerificationResponse {
  candidate_name: string;
  candidate_email: string;
  assessment_id: string;
  assessment_title: string;
  slot_id: string;
  slot_title: string;
  instructions: string;
  duration_minutes: number;
  start_at: string;
  end_at: string;
  allow_resume: boolean;
  status: "not_started" | "in_progress" | "submitted" | "auto_submitted";
  can_start: boolean;
}

export interface CandidateStartResponse {
  session_token: string;
  expires_at: string;
  candidate_assessment_id: string;
  status: string;
}

export interface CandidateQuestion {
  id: string;
  title: string;
  difficulty: "easy" | "medium" | "hard";
  problem_statement: string;
  constraints: string;
  input_format: string;
  output_format: string;
  sample_test_cases: Array<{ input: string; expected_output: string }>;
  supported_languages: string[];
  question_order: number;
  marks: number;
  is_mandatory: boolean;
}

export interface CandidateDraft {
  question_id: string;
  source_language: string;
  draft_code: string;
  final_code: string;
  status: string;
  last_saved_at: string | null;
  submitted_at: string | null;
}

export interface CandidateAssessmentPortal {
  candidate_name: string;
  candidate_email: string;
  candidate_assessment_id: string;
  assessment_id: string;
  assessment_title: string;
  slot_id: string;
  slot_title: string;
  instructions: string;
  duration_minutes: number;
  allow_resume: boolean;
  proctoring_mode: "none" | "basic" | "strict";
  hidden_feedback_mode: "none" | "summary";
  max_hidden_checks: number;
  hidden_check_cooldown_seconds: number;
  started_at: string | null;
  deadline_at: string | null;
  submitted_at: string | null;
  status: "not_started" | "in_progress" | "submitted" | "auto_submitted";
  current_question_order: number;
  time_remaining_seconds: number;
  supported_languages: string[];
  questions: CandidateQuestion[];
  drafts: CandidateDraft[];
}

export interface CandidateCheckpointPayload {
  question_id: string;
  source_code: string;
  language: string;
  current_question_order: number;
}

export interface CandidateCheckpointResponse {
  question_id: string;
  saved_at: string;
  status: string;
}

export interface CandidateCodeRunPayload {
  question_id: string;
  source_code: string;
  language: string;
}

export interface CandidateExecutionCaseResult {
  index: number;
  input: string;
  expected_output: string;
  actual_output: string;
  status: string;
  passed: boolean;
  stderr: string;
  compile_output: string;
  message: string;
  execution_time: string;
  memory_kb: number | null;
  token: string;
}

export interface CandidateSampleRunResponse {
  question_id: string;
  passed_count: number;
  total_count: number;
  results: CandidateExecutionCaseResult[];
}

export interface CandidateHiddenCheckResponse {
  question_id: string;
  passed_count: number;
  total_count: number;
  remaining_attempts: number | null;
  cooldown_remaining_seconds: number;
  results: Array<{
    index: number;
    status: string;
    passed: boolean;
    execution_time: string;
    error_type: string;
  }>;
}

export interface CandidateSubmitPayload {
  answers: Array<{
    question_id: string;
    source_code: string;
    language: string;
  }>;
  auto_submit?: boolean;
  submission_tag?: string;
  submission_message?: string;
}

export interface CandidateSubmitResponse {
  candidate_assessment_id: string;
  status: "submitted" | "auto_submitted";
  submitted_at: string;
  pending_evaluation: boolean;
  submission_tag?: string;
  submission_message?: string;
}
