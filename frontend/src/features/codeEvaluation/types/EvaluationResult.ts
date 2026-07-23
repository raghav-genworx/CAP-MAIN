export type EvaluationJobStatus = "pending" | "processing" | "completed" | "failed";

export interface EvaluationScores {
  test_case_score: number;
  coding_score: number;
  ai_score: number;
  final_score: number;
  percentage: number;
}

export interface AICodeQualitySignal {
  score: number;
  score_breakdown?: Record<string, number>;
  approach: string;
  time_complexity: string;
  space_complexity: string;
  readability: string;
  maintainability: string;
  strengths: string[];
  weaknesses: string[];
  improvements: string[];
}

export interface QuestionTestCaseResult {
  test_case_id: string;
  passed: boolean;
  verdict: string;
  execution_time_ms: number | null;
  memory_kb: number | null;
  points: number;
  mandatory: boolean;
  input: string;
  expected_output: string;
  actual_output: string;
  message: string;
  case_category?: string;
}

export interface QuestionEvaluationBreakdown {
  question_id: string;
  question_title: string;
  language: string;
  submitted_code: string;
  evaluation_status?: "evaluated" | "not_attempted";
  passed_count: number;
  total_count: number;
  earned_points: number;
  total_points: number;
  score: number;
  assigned_marks?: number;
  earned_marks?: number;
  test_case_score?: number;
  coding_score?: number;
  ai_score?: number;
  ai_quality?: AICodeQualitySignal | null;
  difficulty?: string;
  tags?: string[];
  problem_statement?: string;
  input_format?: string;
  output_format?: string;
  constraints?: string;
  suggested_solution?: string;
  suggested_improvement_notes?: string[];
  mandatory_failed: boolean;
  test_cases: QuestionTestCaseResult[];
}

export interface CandidateEvaluationSummary {
  assessment_id: string;
  candidate_assessment_id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string;
  submission_id: string;
  language: string;
  status: EvaluationJobStatus;
  rank: number | null;
  scores: EvaluationScores;
  hidden_passed: number;
  hidden_total: number;
  weights?: {
    test_case_weight: number;
    coding_weight: number;
    ai_weight: number;
  };
  total_execution_time_ms: number;
  peak_memory_kb: number;
  ai_quality: AICodeQualitySignal;
  question_breakdown: QuestionEvaluationBreakdown[];
  activity?: {
    started_at: string | null;
    submitted_at: string | null;
    total_time_seconds: number | null;
    question_time_seconds: Record<string, number>;
  } | null;
  integrity?: {
    proctoring_mode: string;
    tab_switches: number | null;
    copy_paste_count: number | null;
    fullscreen_exits: number | null;
    suspicious_activity: string[];
    plagiarism_similarity_score: number | null;
  } | null;
  submitted_at: string;
  evaluated_at: string | null;
  time_taken_seconds: number | null;
}

export interface CandidateBenchmarkContext {
  candidate_rank: number | null;
  total_candidates: number;
  average_score: number | null;
  average_completion_time_seconds: number | null;
  percentile: number | null;
}

export interface CandidateEvaluationReport {
  assessment_id: string;
  candidate_assessment_id: string;
  candidate: CandidateEvaluationSummary;
  benchmark: CandidateBenchmarkContext | null;
  generated_at: string;
  download_label: string;
}

export interface EvaluationJobResponse {
  job_id: string;
  assessment_id: string;
  candidate_assessment_id: string;
  status: EvaluationJobStatus;
  attempt_count: number;
  created_at: string;
  updated_at: string;
  error_message: string | null;
  result: CandidateEvaluationSummary | null;
}

export interface RetryEvaluationResponse {
  job: EvaluationJobResponse;
  message: string;
}

export interface AssessmentEvaluationOverview {
  assessment_id: string;
  title: string;
  total_candidates: number;
  completed_candidates: number;
  pending_jobs: number;
  failed_jobs: number;
  average_score: number;
  average_test_case_score: number;
  average_coding_score: number;
  average_ai_score: number;
  pass_rate: number;
  highest_score: number;
  report_status: string;
  generated_at: string;
}

export interface AssessmentEvaluationDashboard {
  overview: AssessmentEvaluationOverview;
  leaderboard: CandidateEvaluationSummary[];
  jobs: EvaluationJobResponse[];
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
