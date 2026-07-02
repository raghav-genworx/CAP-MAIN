export type AssessmentStatus = "available" | "scheduled" | "live" | "archived";
export type SlotStatus = "draft" | "scheduled" | "active" | "paused" | "closed";
export type HiddenFeedbackMode = "none" | "summary";
export type InviteEmailStatus = "pending" | "sent" | "failed";
export type CandidateAssessmentStatus =
  | "not_started"
  | "in_progress"
  | "submitted"
  | "auto_submitted"
  | "revoked";

export interface AssessmentQuestionRecord {
  question_id: string;
  title: string;
  difficulty: "easy" | "medium" | "hard";
  tags: string[];
  question_order: number;
  marks: number;
  is_mandatory: boolean;
  supported_languages: string[];
}

export interface Assessment {
  id: string;
  recruiter_uid: string;
  title: string;
  description: string;
  instructions: string;
  duration_minutes: number;
  passing_score: number;
  test_case_score_weight: number;
  coding_score_weight: number;
  ai_score_weight: number;
  allow_resume: boolean;
  shuffle_questions: boolean;
  question_count_per_candidate: number;
  difficulty_blueprint?: Array<"easy" | "medium" | "hard">;
  show_score_to_candidate: boolean;
  proctoring_mode: string;
  hidden_feedback_mode: HiddenFeedbackMode;
  max_hidden_checks: number;
  hidden_check_cooldown_seconds: number;
  supported_languages: string[];
  status: AssessmentStatus;
  questions: AssessmentQuestionRecord[];
  question_count: number;
  slots: AssessmentSlot[];
  test_count: number;
  scheduled_test_count: number;
  live_test_count: number;
  created_at: string;
  updated_at: string;
}

export interface AssessmentListResponse {
  items: Assessment[];
  total: number;
}

export interface AssessmentCreatePayload {
  title: string;
  description: string;
  instructions: string;
  duration_minutes: number;
  passing_score: number;
  test_case_score_weight: number;
  coding_score_weight: number;
  ai_score_weight: number;
  allow_resume: boolean;
  shuffle_questions: boolean;
  question_count_per_candidate: number;
  difficulty_blueprint: Array<"easy" | "medium" | "hard">;
  show_score_to_candidate: boolean;
  proctoring_mode: string;
  hidden_feedback_mode: HiddenFeedbackMode;
  max_hidden_checks: number;
  hidden_check_cooldown_seconds: number;
  supported_languages: string[];
  status: AssessmentStatus;
}

export interface AssessmentQuestionAssignment {
  question_id: string;
  question_order: number;
  marks: number;
  is_mandatory: boolean;
}

export interface AssessmentQuestionsPayload {
  questions: AssessmentQuestionAssignment[];
}

export interface AssessmentSlot {
  id: string;
  assessment_id: string;
  recruiter_uid: string;
  title: string;
  instructions_override: string;
  start_at: string;
  end_at: string;
  duration_minutes?: number;
  timezone_name: string;
  timezone_offset_minutes: number;
  status: SlotStatus;
  effective_status: SlotStatus;
  seconds_until_start: number;
  accepting_closes_in_seconds: number;
  is_accepting_responses: boolean;
  paused_at: string | null;
  total_paused_seconds: number;
  candidate_count: number;
  submitted_count: number;
  created_at: string;
  updated_at: string;
}

export interface AssessmentSlotListResponse {
  items: AssessmentSlot[];
  total: number;
}

export interface AssessmentSlotCreatePayload {
  title: string;
  start_at: string;
  end_at: string;
  duration_minutes: number;
  timezone_name: string;
  timezone_offset_minutes: number;
  instructions_override: string;
  status: SlotStatus;
}

export type AssessmentSlotUpdatePayload = Partial<AssessmentSlotCreatePayload>;

export interface AssessmentSlotActionPayload {
  action: "pause" | "continue" | "extend" | "close";
  extend_minutes?: number;
}

export interface CandidateImportPayload {
  csv_text: string;
}

export interface InviteDispatchPayload {
  candidate_assessment_ids?: string[];
}

export interface CandidateImportRowError {
  row_number: number;
  email: string;
  errors: string[];
}

export interface SlotCandidate {
  candidate_assessment_id: string;
  candidate_id: string;
  name: string;
  email: string;
  external_id: string;
  invite_status: InviteEmailStatus;
  assessment_status: CandidateAssessmentStatus;
  hidden_checks_used: number;
  submission_tag?: string;
  submission_message?: string;
  started_at: string | null;
  submitted_at: string | null;
  last_activity_at: string | null;
  total_score: number | null;
  percentage: number | null;
  rank: number | null;
}

export interface SlotCandidateListResponse {
  items: SlotCandidate[];
  total: number;
}

export interface EvaluationBackfillPayload {
  force?: boolean;
  candidate_assessment_ids?: string[];
}

export interface EvaluationBackfillCandidateResult {
  candidate_assessment_id: string;
  status: string;
  message: string;
  evaluation_job_id: string | null;
  final_score: number | null;
  rank: number | null;
}

export interface EvaluationBackfillResponse {
  assessment_id: string;
  requested_count: number;
  evaluated_count: number;
  skipped_count: number;
  failed_count: number;
  results: EvaluationBackfillCandidateResult[];
}

export interface CandidateImportResponse {
  total_rows: number;
  created_count: number;
  failed_count: number;
  created: SlotCandidate[];
  errors: CandidateImportRowError[];
}

export interface InviteDispatchResponse {
  slot_id: string;
  requested: number;
  sent: number;
  failed: number;
  message: string;
}

export interface MonitoringCandidate {
  candidate_assessment_id: string;
  name: string;
  email: string;
  status: CandidateAssessmentStatus;
  started_at: string | null;
  submitted_at: string | null;
  last_activity_at: string | null;
  questions_attempted: number;
  hidden_checks_used: number;
  submission_tag?: string;
  submission_message?: string;
  current_question_order: number;
  time_remaining_seconds: number | null;
}

export interface MonitoringResponse {
  slot_id: string;
  slot_title: string;
  assessment_title: string;
  items: MonitoringCandidate[];
  total: number;
}
