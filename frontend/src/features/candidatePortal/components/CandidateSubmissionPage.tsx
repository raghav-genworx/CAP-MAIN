import { CheckCircle2 } from "lucide-react";

import { Card } from "../../../components/ui/Card";
import { readSubmissionResult } from "../utils/sessionStorage";

function formatDateTime(value: string | undefined) {
  if (!value) {
    return "Just now";
  }
  return new Date(value).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function CandidateSubmissionPage() {
  const result = readSubmissionResult();
  const wasAutoSubmitted = Boolean(result?.auto);
  const submissionTag = result?.submission_tag || "";
  const submissionMessage = result?.submission_message || "";
  const pendingEvaluation = result?.pending_evaluation !== false;

  return (
    <main className="candidate-shell candidate-shell-branded">
      <Card className="candidate-card candidate-status-card">
        <div className="candidate-access-heading candidate-submission-heading">
          <span className="candidate-access-icon" aria-hidden="true">
            <CheckCircle2 size={24} />
          </span>
          <div>
            <span className="candidate-kicker">Submission Complete</span>
            <h1>{wasAutoSubmitted ? "Time is up, your work was submitted" : "Submission received"}</h1>
            <p>
              {pendingEvaluation
                ? "Your answers are safely recorded and queued for the evaluation workflow."
                : "Your answers are safely recorded. Detailed evaluation is not queued because the initial pass mark was not met."}
            </p>
          </div>
        </div>

        <div className="submission-summary">
          <div>
            <span>Status</span>
            <strong>{result?.status || "submitted"}</strong>
          </div>
          {submissionTag ? (
            <div>
              <span>Tag</span>
              <strong>{submissionTag}</strong>
            </div>
          ) : null}
          <div>
            <span>Submitted at</span>
            <strong>{formatDateTime(result?.submitted_at)}</strong>
          </div>
          <div>
            <span>Evaluation</span>
            <strong>{pendingEvaluation ? "pending" : "not queued"}</strong>
          </div>
        </div>

        {submissionMessage ? (
          <p className="candidate-submission-message">{submissionMessage}</p>
        ) : null}

        <p className="candidate-muted">
          You can close this tab. The recruiter will see your submission status in their monitoring dashboard.
        </p>
      </Card>
    </main>
  );
}
