import { CheckCircle2, Clock3, FileCheck2 } from "lucide-react";

import { Card } from "../../../components/ui/Card";
import { CandidatePageShell } from "./CandidatePageShell";
import { readSubmissionResult } from "../utils/sessionStorage";
import { formatDateTime } from "../utils/format";

/**
 * Candidate-facing labels for the auto-submission tags the workspace sends.
 * Internal tag values are never rendered directly.
 */
const AUTO_SUBMISSION_REASONS: Record<string, string> = {
  timer_expired: "Your time ran out, so your work was submitted automatically.",
  tab_switch_lock:
    "Your assessment was submitted automatically after repeated tab-switch warnings.",
  fullscreen_exit:
    "Your assessment was submitted automatically because fullscreen mode was exited.",
};

function autoSubmissionReason(tag: string, message: string) {
  return AUTO_SUBMISSION_REASONS[tag] || message || "";
}

export function CandidateSubmissionPage() {
  const receipt = readSubmissionResult();

  if (!receipt) {
    return (
      <CandidatePageShell>
        <Card className="cap-panel cap-panel-narrow" aria-labelledby="cap-no-receipt">
          <div className="cap-state-icon" aria-hidden="true">
            <FileCheck2 size={22} />
          </div>
          <div className="cap-panel-intro">
            <h1 id="cap-no-receipt">No active assessment</h1>
            <p>
              There is no assessment open in this browser. If you have just
              submitted, your responses were recorded and you can close this tab.
            </p>
          </div>
          <p className="cap-muted">
            To open an assessment, use the link or code from your invitation email.
          </p>
        </Card>
      </CandidatePageShell>
    );
  }

  const wasAutoSubmitted = Boolean(receipt.auto) || receipt.status === "auto_submitted";
  const reason = wasAutoSubmitted
    ? autoSubmissionReason(receipt.submission_tag || "", receipt.submission_message || "")
    : "";

  return (
    <CandidatePageShell footnote="You can safely close this tab. Nothing else is required from you.">
      <Card className="cap-panel" aria-labelledby="cap-receipt-title">
        <div className="cap-receipt-head">
          <span className="cap-state-icon is-success" aria-hidden="true">
            <CheckCircle2 size={24} />
          </span>
          <div className="cap-panel-intro">
            <p className="cap-eyebrow">Assessment complete</p>
            <h1 id="cap-receipt-title">
              {wasAutoSubmitted
                ? "Your assessment was submitted automatically"
                : "Your assessment has been submitted"}
            </h1>
            <p className="cap-lead">
              All of your responses were saved and recorded successfully.
            </p>
            {reason ? <p className="cap-muted">{reason}</p> : null}
          </div>
        </div>

        <dl className="cap-facts">
          {receipt.assessment_title ? (
            <div>
              <dt>Assessment</dt>
              <dd>{receipt.assessment_title}</dd>
            </div>
          ) : null}
          {receipt.slot_title ? (
            <div>
              <dt>Session</dt>
              <dd>{receipt.slot_title}</dd>
            </div>
          ) : null}
          {receipt.candidate_name ? (
            <div>
              <dt>Candidate</dt>
              <dd>{receipt.candidate_name}</dd>
            </div>
          ) : null}
          <div>
            <dt>Submitted</dt>
            <dd>{formatDateTime(receipt.submitted_at, "Just now")}</dd>
          </div>
          <div>
            <dt>Submission</dt>
            <dd>
              {wasAutoSubmitted
                ? "Received — submitted automatically"
                : "Received — submitted by you"}
            </dd>
          </div>
          <div>
            <dt>Reference ID</dt>
            <dd className="cap-facts-wrap cap-numeric">
              {receipt.candidate_assessment_id}
            </dd>
          </div>
        </dl>

        <section className="cap-subsection" aria-labelledby="cap-whats-next">
          <h2 id="cap-whats-next">What happens next</h2>
          <ul className="cap-checklist">
            <li>
              {receipt.pending_evaluation
                ? "Your submission has been received and is awaiting review."
                : "Your submission has been received."}
            </li>
            <li>
              The hiring team will contact you about next steps. Results are not
              shown here.
            </li>
            <li>
              Keep your reference ID if you need to get in touch about this
              assessment.
            </li>
          </ul>
        </section>

        <p className="cap-note">
          <Clock3 size={15} aria-hidden="true" />
          <span>
            You can close this tab now. Nothing further is required from you.
          </span>
        </p>
      </Card>
    </CandidatePageShell>
  );
}
