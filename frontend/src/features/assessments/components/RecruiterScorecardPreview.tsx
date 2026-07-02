import { Download } from "lucide-react";

import { Button } from "../../../components/ui/Button";
import type { CandidateEvaluationSummary } from "../../codeEvaluation";

interface RecruiterScorecardPreviewProps {
  candidate: CandidateEvaluationSummary | null;
  loading: boolean;
  error: string;
  downloadPending: boolean;
  onDownload: () => void;
}

export function RecruiterScorecardPreview({
  candidate,
  loading,
  error,
  downloadPending,
  onDownload,
}: RecruiterScorecardPreviewProps) {
  if (loading) {
    return (
      <div className="recruiter-scorecard-preview">
        <strong>Loading scorecard...</strong>
      </div>
    );
  }

  if (error || !candidate) {
    return (
      <div className="recruiter-scorecard-preview is-error" role="alert">
        <strong>{error || "Scorecard unavailable."}</strong>
      </div>
    );
  }

  return (
    <div className="recruiter-scorecard-preview">
      <div className="scorecard-head">
        <div>
          <span>Candidate scorecard</span>
          <h2>{candidate.candidate_name}</h2>
          <p>{candidate.candidate_email}</p>
        </div>
        <Button
          type="button"
          variant="secondary"
          disabled={downloadPending}
          onClick={onDownload}
        >
          <Download size={16} aria-hidden="true" />
          {downloadPending ? "Preparing..." : "Download PDF"}
        </Button>
      </div>
      <div className="assessment-result-summary">
        <div>
          <span>Rank</span>
          <strong>#{candidate.rank || "-"}</strong>
        </div>
        <div>
          <span>Final</span>
          <strong>{Math.round(candidate.scores.final_score)}%</strong>
        </div>
        <div>
          <span>Hidden cases</span>
          <strong>
            {candidate.hidden_passed}/{candidate.hidden_total}
          </strong>
        </div>
      </div>
      <div className="recruiter-scorecard-questions">
        {candidate.question_breakdown.map((question) => (
          <article key={question.question_id}>
            <header>
              <div>
                <strong>{question.question_title}</strong>
                <span>
                  {question.evaluation_status === "not_attempted"
                    ? "Not attempted · evaluation skipped"
                    : `${question.passed_count}/${question.total_count} cases passed`}
                </span>
              </div>
              <strong>
                {(question.earned_marks ?? 0).toFixed(1)}/{
                  (question.assigned_marks ?? question.total_points).toFixed(1)
                }
              </strong>
            </header>
            {question.evaluation_status !== "not_attempted" ? (
              <div className="question-evaluation-score-parts">
                <span>Hidden {Math.round(question.test_case_score ?? 0)}%</span>
                <span>Metrics {Math.round(question.coding_score ?? 0)}%</span>
                <span>AI quality {Math.round(question.ai_score ?? 0)}%</span>
              </div>
            ) : null}
            <pre>{question.submitted_code || "No submitted code available."}</pre>
            <div>
              {question.test_cases.map((testCase) => (
                <span key={testCase.test_case_id}>
                  {testCase.passed ? "Passed" : "Failed"} -{" "}
                  {testCase.verdict.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
