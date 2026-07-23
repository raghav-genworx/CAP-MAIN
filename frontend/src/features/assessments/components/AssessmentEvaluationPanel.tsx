import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { StatusBadge } from "../../../components/common/StatusBadge";
import { Card } from "../../../components/ui/Card";
import { useAuth } from "../../auth";
import {
  fetchAssessmentEvaluationDashboard,
  type CandidateEvaluationSummary,
} from "../../codeEvaluation";
import { fetchSlotCandidates } from "../services/assessmentService";
import { generateAssessmentAnalyticsPdf } from "../services/pdfReportService";
import type { EvaluationBackfillResponse } from "../types/Assessment";
import type { Assessment, AssessmentSlot, SlotCandidate } from "../types/Assessment";
import { assessmentTestPath } from "../utils/assessmentRoutes";

interface AssessmentEvaluationPanelProps {
  assessment: Assessment;
  slots: AssessmentSlot[];
  backfillPending: boolean;
  backfillError: string;
  backfillResult: EvaluationBackfillResponse | null;
  onBackfill: () => Promise<unknown> | void;
  downloadError?: string;
  pdfTrigger?: number;
}

interface SlotCandidateLookup {
  [slotId: string]: SlotCandidate[];
}

interface SlotAnalytics {
  id: string;
  title: string;
  status: AssessmentSlot["effective_status"];
  startsAt: string;
  candidateCount: number;
  submittedCount: number;
  evaluatedCount: number;
  averageScore: number;
  topScore: number;
  passRate: number;
  submissionRate: number;
  evaluationRate: number;
  hiddenPassRate: number;
  averageCodingScore: number;
  averageAiScore: number;
  averageDurationSeconds: number | null;
  bands: {
    excellent: number;
    pass: number;
    review: number;
  };
}

export function AssessmentEvaluationPanel({
  assessment,
  slots,
  backfillError,
  backfillResult,
  downloadError,
  pdfTrigger,
}: AssessmentEvaluationPanelProps) {
  const { currentUser } = useAuth();
  const slotIds = useMemo(() => slots.map((slot) => slot.id), [slots]);
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
  const slotCandidatesQuery = useQuery({
    queryKey: ["assessment-analytics-slot-candidates", currentUser?.uid, assessment.id, slotIds],
    queryFn: async (): Promise<SlotCandidateLookup> => {
      if (!currentUser) {
        throw new Error("Recruiter session is required.");
      }
      const idToken = await currentUser.getIdToken();
      const entries = await Promise.all(
        slots.map(async (slot) => {
          const response = await fetchSlotCandidates(idToken, slot.id);
          return [slot.id, response.items] as const;
        }),
      );
      return Object.fromEntries(entries);
    },
    enabled: Boolean(currentUser && slots.length),
    retry: 1,
  });
  const dashboard = dashboardQuery.data;
  const slotAnalytics = useMemo(
    () =>
      buildSlotAnalytics(
        assessment.passing_score,
        slots,
        slotCandidatesQuery.data ?? {},
        dashboard?.leaderboard ?? [],
      ),
    [assessment.passing_score, dashboard?.leaderboard, slotCandidatesQuery.data, slots],
  );

  const maxDuration = useMemo(() => {
    const durations = slotAnalytics
      .map((slot) => slot.averageDurationSeconds)
      .filter((duration): duration is number => duration !== null);
    return durations.length ? Math.max(...durations) : 0;
  }, [slotAnalytics]);

  // PDF generation trigger
  const pdfTriggerRef = useRef(pdfTrigger ?? 0);
  useEffect(() => {
    if (pdfTrigger !== undefined && pdfTrigger > pdfTriggerRef.current && dashboard) {
      pdfTriggerRef.current = pdfTrigger;
      const candidateLookup: Record<string, { candidate_assessment_id: string; assessment_status: string }[]> = {};
      const rawLookup = slotCandidatesQuery.data ?? {};
      for (const [slotId, candidates] of Object.entries(rawLookup)) {
        candidateLookup[slotId] = candidates.map((c) => ({
          candidate_assessment_id: c.candidate_assessment_id,
          assessment_status: c.assessment_status,
        }));
      }
      generateAssessmentAnalyticsPdf(assessment, slots, dashboard, candidateLookup);
    }
  }, [pdfTrigger, assessment, slots, dashboard, slotCandidatesQuery.data]);

  if (dashboardQuery.isLoading || (slots.length > 0 && slotCandidatesQuery.isLoading)) {
    return <PanelState label="Loading assessment analytics..." />;
  }

  if (dashboardQuery.isError || !dashboard) {
    return <PanelState label="Assessment analytics are temporarily unavailable." />;
  }

  const overview = dashboard.overview;
  const completionPercentage = overview.total_candidates
    ? (overview.completed_candidates / overview.total_candidates) * 100
    : 0;

  return (
    <div className="assessment-evaluation-view">

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
      {slotCandidatesQuery.isError ? (
        <p className="test-feedback-message is-error" role="alert">
          Slot comparison could not load candidate totals. Showing available
          assessment-level analytics.
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
          <EvaluationSection eyebrow="Comparative analysis" title="Slot performance overview">
            <div className="evaluation-slot-grid">
              {slotAnalytics.map((slot) => (
                <article key={slot.id} className="evaluation-slot-card">
                  <header>
                    <div>
                      <span>{formatDateTime(slot.startsAt)}</span>
                      <strong>{slot.title}</strong>
                    </div>
                    <StatusBadge value={slot.status} />
                  </header>
                  <div className="evaluation-slot-score">
                    <strong>{formatPercent(slot.averageScore)}</strong>
                    <span>average final score</span>
                  </div>
                  <dl>
                    <div>
                      <dt>Submissions</dt>
                      <dd>
                        {slot.submittedCount}/{slot.candidateCount}
                        <small>{formatPercent(slot.submissionRate)}</small>
                      </dd>
                    </div>
                    <div>
                      <dt>Evaluated</dt>
                      <dd>
                        {slot.evaluatedCount}/{slot.submittedCount}
                        <small>{formatPercent(slot.evaluationRate)}</small>
                      </dd>
                    </div>
                    <div>
                      <dt>Pass rate</dt>
                      <dd>{formatPercent(slot.passRate)}</dd>
                    </div>
                    <div>
                      <dt>Avg time</dt>
                      <dd>{formatDuration(slot.averageDurationSeconds)}</dd>
                    </div>
                    <div>
                      <dt>Hidden cases</dt>
                      <dd>{formatPercent(slot.hiddenPassRate)}</dd>
                    </div>
                    <div>
                      <dt>Coding score</dt>
                      <dd>{formatPercent(slot.averageCodingScore)}</dd>
                    </div>
                    <div>
                      <dt>AI score</dt>
                      <dd>{formatPercent(slot.averageAiScore)}</dd>
                    </div>
                  </dl>
                  <div className="evaluation-band-stack" aria-label={`${slot.title} score distribution`}>
                    <span
                      className="is-excellent"
                      style={{ width: `${bandWidth(slot.bands.excellent, slot.evaluatedCount)}%` }}
                    />
                    <span
                      className="is-pass"
                      style={{ width: `${bandWidth(slot.bands.pass, slot.evaluatedCount)}%` }}
                    />
                    <span
                      className="is-review"
                      style={{ width: `${bandWidth(slot.bands.review, slot.evaluatedCount)}%` }}
                    />
                  </div>
                  <Link
                    className="assessment-test-report-link evaluation-slot-link"
                    to={assessmentTestPath(assessment.id, slot.id, assessment.title, slot.title)}
                  >
                    <FileText size={17} aria-hidden="true" />
                    <span>Open test analytics</span>
                  </Link>
                </article>
              ))}
              {!slotAnalytics.length ? (
                <p className="empty-state">Create test slots to compare analytics.</p>
              ) : null}
            </div>
          </EvaluationSection>

          {slotAnalytics.length > 0 ? (
            <EvaluationSection eyebrow="Visual comparisons" title="Key metrics by test slot">
              <div className="analytics-charts-grid">
                
                {/* Average Final Score Comparison */}
                <div className="analytics-chart-card">
                  <h3>Average Final Score</h3>
                  <div className="chart-bars-container">
                    {slotAnalytics.map((slot) => (
                      <div key={slot.id} className="chart-bar-row">
                        <div className="chart-bar-label">
                          <span className="chart-bar-title">{slot.title}</span>
                          <span className="chart-bar-value">{formatPercent(slot.averageScore)}</span>
                        </div>
                        <div className="chart-bar-bg">
                          <div
                            className="chart-bar-fill score-fill"
                            style={{ width: `${slot.averageScore}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Participation / Submission Rate Comparison */}
                <div className="analytics-chart-card">
                  <h3>Participation Rate</h3>
                  <div className="chart-bars-container">
                    {slotAnalytics.map((slot) => (
                      <div key={slot.id} className="chart-bar-row">
                        <div className="chart-bar-label">
                          <span className="chart-bar-title">{slot.title}</span>
                          <span className="chart-bar-value">{formatPercent(slot.submissionRate)}</span>
                        </div>
                        <div className="chart-bar-bg">
                          <div
                            className="chart-bar-fill participation-fill"
                            style={{ width: `${slot.submissionRate}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Average Duration Comparison */}
                <div className="analytics-chart-card">
                  <h3>Average Duration</h3>
                  <div className="chart-bars-container">
                    {slotAnalytics.map((slot) => {
                      const widthPercent = maxDuration && slot.averageDurationSeconds
                        ? (slot.averageDurationSeconds / maxDuration) * 100
                        : 0;
                      return (
                        <div key={slot.id} className="chart-bar-row">
                          <div className="chart-bar-label">
                            <span className="chart-bar-title">{slot.title}</span>
                            <span className="chart-bar-value">
                              {slot.averageDurationSeconds !== null
                                ? formatDuration(slot.averageDurationSeconds)
                                : "N/A"}
                            </span>
                          </div>
                          <div className="chart-bar-bg">
                            <div
                              className="chart-bar-fill duration-fill"
                              style={{ width: `${widthPercent}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

              </div>
            </EvaluationSection>
          ) : null}
        </section>

        <aside className="assessment-evaluation-side">
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

function buildSlotAnalytics(
  passingScore: number,
  slots: AssessmentSlot[],
  slotCandidates: SlotCandidateLookup,
  leaderboard: CandidateEvaluationSummary[],
): SlotAnalytics[] {
  const evaluationByCandidateId = new Map(
    leaderboard.map((candidate) => [
      candidate.candidate_assessment_id,
      candidate,
    ]),
  );

  return slots.map((slot) => {
    const candidates = slotCandidates[slot.id] ?? [];
    const submittedFromCandidates = candidates.filter((candidate) =>
      ["submitted", "auto_submitted"].includes(candidate.assessment_status),
    ).length;
    const evaluated = candidates
      .map((candidate) => evaluationByCandidateId.get(candidate.candidate_assessment_id))
      .filter((candidate): candidate is CandidateEvaluationSummary => Boolean(candidate));
    const candidateCount = Math.max(slot.candidate_count, candidates.length);
    const submittedCount = Math.max(slot.submitted_count, submittedFromCandidates);
    const scoreTotal = evaluated.reduce(
      (sum, candidate) => sum + candidate.scores.final_score,
      0,
    );
    const codingTotal = evaluated.reduce(
      (sum, candidate) => sum + candidate.scores.coding_score,
      0,
    );
    const aiTotal = evaluated.reduce(
      (sum, candidate) => sum + candidate.scores.ai_score,
      0,
    );
    const hiddenPassed = evaluated.reduce(
      (sum, candidate) => sum + candidate.hidden_passed,
      0,
    );
    const hiddenTotal = evaluated.reduce(
      (sum, candidate) => sum + candidate.hidden_total,
      0,
    );
    const durations = evaluated
      .map((candidate) => candidate.time_taken_seconds ?? candidate.activity?.total_time_seconds)
      .filter((duration): duration is number => typeof duration === "number");
    const bands = evaluated.reduce(
      (accumulator, candidate) => {
        const score = candidate.scores.final_score;
        if (score >= Math.max(90, passingScore + 15)) {
          accumulator.excellent += 1;
        } else if (score >= passingScore) {
          accumulator.pass += 1;
        } else {
          accumulator.review += 1;
        }
        return accumulator;
      },
      { excellent: 0, pass: 0, review: 0 },
    );

    return {
      id: slot.id,
      title: slot.title,
      status: slot.effective_status,
      startsAt: slot.start_at,
      candidateCount,
      submittedCount,
      evaluatedCount: evaluated.length,
      averageScore: average(scoreTotal, evaluated.length),
      topScore: evaluated.length
        ? Math.max(...evaluated.map((candidate) => candidate.scores.final_score))
        : 0,
      passRate: percentage(
        evaluated.filter((candidate) => candidate.scores.final_score >= passingScore)
          .length,
        evaluated.length,
      ),
      submissionRate: percentage(submittedCount, candidateCount),
      evaluationRate: percentage(evaluated.length, submittedCount),
      hiddenPassRate: percentage(hiddenPassed, hiddenTotal),
      averageCodingScore: average(codingTotal, evaluated.length),
      averageAiScore: average(aiTotal, evaluated.length),
      averageDurationSeconds: durations.length
        ? average(
            durations.reduce((sum, duration) => sum + duration, 0),
            durations.length,
          )
        : null,
      bands,
    };
  });
}



function average(total: number, count: number) {
  return count ? total / count : 0;
}

function percentage(value: number, total: number) {
  return total ? (value / total) * 100 : 0;
}

function formatPercent(value: number) {
  return `${Math.round(value)}%`;
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Schedule pending";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatDuration(seconds: number | null) {
  if (seconds === null || !Number.isFinite(seconds)) {
    return "-";
  }
  const rounded = Math.round(seconds);
  const minutes = Math.floor(rounded / 60);
  const remainingSeconds = rounded % 60;
  if (minutes < 1) {
    return `${remainingSeconds}s`;
  }
  return `${minutes}m ${remainingSeconds}s`;
}

function bandWidth(count: number, total: number) {
  return total ? (count / total) * 100 : 0;
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
