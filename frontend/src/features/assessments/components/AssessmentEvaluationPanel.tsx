import { useQuery } from "@tanstack/react-query";
import { Activity, Download, FileText, Users } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { StatusBadge } from "../../../components/common/StatusBadge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { useAuth } from "../../auth";
import {
  downloadAssessmentEvaluationReport,
  downloadCandidateEvaluationReport,
  fetchAssessmentEvaluationDashboard,
  type CandidateEvaluationSummary,
} from "../../codeEvaluation";
import type { EvaluationBackfillResponse } from "../types/Assessment";
import type { Assessment, AssessmentSlot } from "../types/Assessment";
import { RecruiterScorecardPreview } from "./RecruiterScorecardPreview";

interface AssessmentEvaluationPanelProps {
  assessment: Assessment;
  slots: AssessmentSlot[];
  backfillPending: boolean;
  backfillError: string;
  backfillResult: EvaluationBackfillResponse | null;
  onBackfill: () => Promise<unknown> | void;
  onOpenTest: (slotId: string) => void;
}

interface QuestionAnalytics {
  id: string;
  title: string;
  candidates: number;
  score: number;
  passed: number;
  total: number;
}

export function AssessmentEvaluationPanel({
  assessment,
  slots,
  backfillPending,
  backfillError,
  backfillResult,
  onBackfill,
  onOpenTest,
}: AssessmentEvaluationPanelProps) {
  const { currentUser } = useAuth();
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [downloadTarget, setDownloadTarget] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState("");
  const dashboardQuery = useQuery({
    queryKey: ["code-evaluation-dashboard", assessment.id],
    queryFn: async () => {
      if (!currentUser) {
        throw new Error("Recruiter session is required.");
      }
      return fetchAssessmentEvaluationDashboard(
        await currentUser.getIdToken(),
        assessment.id,
      );
    },
    enabled: Boolean(currentUser),
    retry: 1,
  });
  const dashboard = dashboardQuery.data;
  const selectedCandidate =
    dashboard?.leaderboard.find(
      (candidate) => candidate.candidate_assessment_id === selectedCandidateId,
    ) ?? dashboard?.leaderboard[0] ?? null;
  const questionAnalytics = useMemo(
    () => buildQuestionAnalytics(dashboard?.leaderboard ?? []),
    [dashboard?.leaderboard],
  );

  async function downloadAssessmentReport() {
    setDownloadError("");
    setDownloadTarget("assessment");
    try {
      if (!currentUser) {
        throw new Error("Recruiter session is required.");
      }
      await downloadAssessmentEvaluationReport(
        await currentUser.getIdToken(),
        assessment.id,
      );
    } catch (error: unknown) {
      setDownloadError(
        error instanceof Error ? error.message : "Unable to download report.",
      );
    } finally {
      setDownloadTarget(null);
    }
  }

  async function downloadCandidateReport(candidateAssessmentId: string) {
    setDownloadError("");
    setDownloadTarget(candidateAssessmentId);
    try {
      if (!currentUser) {
        throw new Error("Recruiter session is required.");
      }
      await downloadCandidateEvaluationReport(
        await currentUser.getIdToken(),
        assessment.id,
        candidateAssessmentId,
      );
    } catch (error: unknown) {
      setDownloadError(
        error instanceof Error ? error.message : "Unable to download scorecard.",
      );
    } finally {
      setDownloadTarget(null);
    }
  }

  if (dashboardQuery.isLoading) {
    return <PanelState label="Loading evaluation workspace..." />;
  }

  if (dashboardQuery.isError || !dashboard) {
    return <PanelState label="Evaluation data is temporarily unavailable." />;
  }

  const overview = dashboard.overview;
  const completionPercentage = overview.total_candidates
    ? (overview.completed_candidates / overview.total_candidates) * 100
    : 0;

  return (
    <div className="assessment-evaluation-view">
      <section className="assessment-evaluation-header">
        <div>
          <span className="panel-eyebrow">Evaluation command center</span>
          <h2>Assessment performance</h2>
          <p>
            Track scoring quality, investigate question difficulty, and open
            evidence-backed candidate scorecards.
          </p>
        </div>
        <div className="assessment-row-actions">
          <Button
            type="button"
            variant="secondary"
            disabled={backfillPending}
            onClick={() => void onBackfill()}
          >
            <Activity size={16} aria-hidden="true" />
            {backfillPending ? "Evaluating..." : "Evaluate previous"}
          </Button>
          <Button
            type="button"
            disabled={downloadTarget !== null || !overview.completed_candidates}
            onClick={() => void downloadAssessmentReport()}
          >
            <Download size={16} aria-hidden="true" />
            {downloadTarget === "assessment" ? "Preparing..." : "Assessment PDF"}
          </Button>
        </div>
      </section>

      {backfillError || backfillResult ? (
        <p
          className={`test-feedback-message ${
            backfillError ? "is-error" : "is-success"
          }`}
        >
          {backfillError ||
            `Evaluated ${backfillResult?.evaluated_count ?? 0}, skipped ${
              backfillResult?.skipped_count ?? 0
            }, failed ${backfillResult?.failed_count ?? 0}.`}
        </p>
      ) : null}
      {downloadError ? (
        <p className="test-feedback-message is-error" role="alert">
          {downloadError}
        </p>
      ) : null}

      <div className="assessment-evaluation-metrics">
        <MetricTile
          label="Evaluated"
          value={`${overview.completed_candidates}/${overview.total_candidates}`}
        />
        <MetricTile
          label="Average score"
          value={`${Math.round(overview.average_score)}%`}
        />
        <MetricTile label="Pass rate" value={`${Math.round(overview.pass_rate)}%`} />
        <MetricTile
          label="Highest score"
          value={`${Math.round(overview.highest_score)}%`}
        />
      </div>

      <div className="assessment-evaluation-grid">
        <section className="assessment-evaluation-main">
          <EvaluationSection eyebrow="Tests" title="Scheduled test performance">
            <div className="assessment-test-report-list">
              {slots.map((slot) => (
                <button
                  key={slot.id}
                  type="button"
                  onClick={() => onOpenTest(slot.id)}
                >
                  <FileText size={18} aria-hidden="true" />
                  <span>
                    <strong>{slot.title}</strong>
                    <small>
                      {slot.submitted_count}/{slot.candidate_count} submitted
                    </small>
                  </span>
                  <StatusBadge value={slot.effective_status} />
                </button>
              ))}
              {!slots.length ? <p className="empty-state">No scheduled tests yet.</p> : null}
            </div>
          </EvaluationSection>

          <EvaluationSection eyebrow="Question analytics" title="Difficulty and pass signals">
            <div className="evaluation-analytics-grid">
              {questionAnalytics.map((question) => {
                const passRate = question.total
                  ? (question.passed / question.total) * 100
                  : 0;
                return (
                  <article key={question.id} className="evaluation-analytics-card">
                    <div>
                      <strong>{question.title}</strong>
                      <span>{question.candidates} evaluated</span>
                    </div>
                    <dl>
                      <div>
                        <dt>Average</dt>
                        <dd>{Math.round(question.score / question.candidates)}%</dd>
                      </div>
                      <div>
                        <dt>Pass rate</dt>
                        <dd>{Math.round(passRate)}%</dd>
                      </div>
                      <div>
                        <dt>Cases</dt>
                        <dd>{question.passed}/{question.total}</dd>
                      </div>
                    </dl>
                  </article>
                );
              })}
              {!questionAnalytics.length ? (
                <p className="empty-state">Question analytics appear after evaluation.</p>
              ) : null}
            </div>
          </EvaluationSection>

          <EvaluationSection eyebrow="Leaderboard" title="Candidate ranking">
            <div className="assessment-table-shell">
              <table className="assessment-table compact-table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Candidate</th>
                    <th>Final</th>
                    <th>Hidden cases</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {dashboard.leaderboard.map((candidate) => (
                    <tr
                      key={candidate.candidate_assessment_id}
                      className={
                        selectedCandidate?.candidate_assessment_id ===
                        candidate.candidate_assessment_id
                          ? "is-selected"
                          : ""
                      }
                    >
                      <td>#{candidate.rank ?? "-"}</td>
                      <td>
                        <button
                          type="button"
                          className="table-link-button"
                          onClick={() =>
                            setSelectedCandidateId(candidate.candidate_assessment_id)
                          }
                        >
                          {candidate.candidate_name}
                        </button>
                        <small>{candidate.candidate_email}</small>
                      </td>
                      <td>{Math.round(candidate.scores.final_score)}%</td>
                      <td>{candidate.hidden_passed}/{candidate.hidden_total}</td>
                      <td>
                        <button
                          type="button"
                          className="table-link-button"
                          onClick={() =>
                            setSelectedCandidateId(candidate.candidate_assessment_id)
                          }
                        >
                          Scorecard
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!dashboard.leaderboard.length ? (
                    <tr><td colSpan={5}>No completed evaluations yet.</td></tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </EvaluationSection>
        </section>

        <aside className="assessment-evaluation-side">
          {selectedCandidate ? (
            <RecruiterScorecardPreview
              candidate={selectedCandidate}
              loading={false}
              error=""
              downloadPending={
                downloadTarget === selectedCandidate.candidate_assessment_id
              }
              onDownload={() =>
                void downloadCandidateReport(
                  selectedCandidate.candidate_assessment_id,
                )
              }
            />
          ) : (
            <div className="evaluation-empty-state">
              <Users size={22} aria-hidden="true" />
              <strong>No scorecard yet</strong>
              <p>Completed candidates will appear here.</p>
            </div>
          )}
          <div className="evaluation-pipeline-summary">
            <span>Evaluation pipeline</span>
            <strong>
              {overview.pending_jobs} pending · {overview.failed_jobs} failed
            </strong>
            <div
              role="progressbar"
              aria-label="Evaluation completion"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(completionPercentage)}
            >
              <i style={{ width: `${completionPercentage}%` }} />
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function buildQuestionAnalytics(
  leaderboard: CandidateEvaluationSummary[],
): QuestionAnalytics[] {
  const rows = new Map<string, QuestionAnalytics>();
  leaderboard.forEach((candidate) => {
    candidate.question_breakdown.forEach((question) => {
      const row = rows.get(question.question_id) ?? {
        id: question.question_id,
        title: question.question_title,
        candidates: 0,
        score: 0,
        passed: 0,
        total: 0,
      };
      row.candidates += 1;
      row.score += question.score;
      row.passed += question.passed_count;
      row.total += question.total_count;
      rows.set(question.question_id, row);
    });
  });
  return Array.from(rows.values());
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="assessment-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EvaluationSection({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="evaluation-section-block">
      <div className="card-head">
        <div><span>{eyebrow}</span><h2>{title}</h2></div>
      </div>
      {children}
    </div>
  );
}

function PanelState({ label }: { label: string }) {
  return (
    <Card className="assessment-panel assessment-panel-wide">
      <p className="empty-state">{label}</p>
    </Card>
  );
}
