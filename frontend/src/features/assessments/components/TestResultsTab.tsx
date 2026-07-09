import { useEffect, useState } from "react";

import { StatusBadge } from "../../../components/common/StatusBadge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { useAuth } from "../../auth";
import {
  downloadTestEvaluationReport,
  fetchCandidateScorecardReport,
  type CandidateEvaluationReport,
} from "../../codeEvaluation";
import type {
  Assessment,
  AssessmentSlot,
  EvaluationBackfillResponse,
  SlotCandidate,
} from "../types/Assessment";
import {
  buildScorecardSettings,
  RecruiterScorecardPreview,
} from "./RecruiterScorecardPreview";

interface TestResultsTabProps {
  assessment: Assessment;
  slot: AssessmentSlot;
  candidates: SlotCandidate[];
  backfillPending: boolean;
  backfillError: string;
  backfillResult: EvaluationBackfillResponse | null;
  onBackfillEvaluations: (
    candidateAssessmentIds: string[],
  ) => Promise<unknown> | void;
}

export function TestResultsTab({
  assessment,
  slot,
  candidates,
  backfillPending,
  backfillError,
  backfillResult,
  onBackfillEvaluations,
}: TestResultsTabProps) {
  const { currentUser } = useAuth();
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(
    null,
  );
  const [selectedScorecard, setSelectedScorecard] =
    useState<CandidateEvaluationReport | null>(null);
  const [scorecardError, setScorecardError] = useState("");
  const [downloadError, setDownloadError] = useState("");
  const [downloadingReport, setDownloadingReport] = useState<string | null>(
    null,
  );
  const rankedCandidates = [...candidates].sort((first, second) => {
    const firstRank = first.rank ?? Number.POSITIVE_INFINITY;
    const secondRank = second.rank ?? Number.POSITIVE_INFINITY;
    if (firstRank !== secondRank) {
      return firstRank - secondRank;
    }
    const firstScore = first.percentage ?? -1;
    const secondScore = second.percentage ?? -1;
    if (firstScore !== secondScore) {
      return secondScore - firstScore;
    }
    return first.name.localeCompare(second.name);
  });
  const evaluatedCount = candidates.filter(
    (candidate) => candidate.percentage !== null,
  ).length;
  const submittedCount = candidates.filter((candidate) =>
    ["submitted", "auto_submitted"].includes(candidate.assessment_status),
  ).length;
  const submittedCandidateIds = candidates
    .filter((candidate) =>
      ["submitted", "auto_submitted"].includes(candidate.assessment_status),
    )
    .map((candidate) => candidate.candidate_assessment_id);
  const averageScore = evaluatedCount
    ? candidates.reduce(
        (total, candidate) => total + (candidate.percentage ?? 0),
        0,
      ) / evaluatedCount
    : 0;

  useEffect(() => {
    if (!selectedCandidateId) {
      setSelectedScorecard(null);
      setScorecardError("");
      return;
    }

    const controller = new AbortController();
    setSelectedScorecard(null);
    setScorecardError("");
    void (async () => {
      try {
        if (!currentUser) {
          throw new Error("Recruiter session is required.");
        }
        const report = await fetchCandidateScorecardReport(
          await currentUser.getIdToken(),
          assessment.id,
          selectedCandidateId,
          controller.signal,
        );
        setSelectedScorecard(report);
      } catch (error: unknown) {
        if (controller.signal.aborted) {
          return;
        }
        setSelectedScorecard(null);
        setScorecardError(
          error instanceof Error ? error.message : "Unable to load scorecard.",
        );
      }
    })();

    return () => controller.abort();
  }, [assessment.id, currentUser, selectedCandidateId]);

  async function downloadTestReport() {
    setDownloadError("");
    setDownloadingReport("assessment");
    try {
      if (!currentUser) {
        throw new Error("Recruiter session is required.");
      }
      await downloadTestEvaluationReport(
        await currentUser.getIdToken(),
        assessment.id,
        slot.id,
      );
    } catch (error: unknown) {
      setDownloadError(
        error instanceof Error ? error.message : "Unable to download report.",
      );
    } finally {
      setDownloadingReport(null);
    }
  }

  if (selectedCandidateId) {
    return (
      <Card className="assessment-panel assessment-panel-wide scorecard-page-card">
        <RecruiterScorecardPreview
          candidate={selectedScorecard?.candidate ?? null}
          benchmark={selectedScorecard?.benchmark}
          settings={buildScorecardSettings(assessment, slot)}
          loading={!selectedScorecard && !scorecardError}
          error={scorecardError}
          onBack={() => setSelectedCandidateId(null)}
          fullPage
        />
      </Card>
    );
  }

  return (
    <Card className="assessment-panel assessment-panel-wide">
      <div className="panel-heading">
        <div>
          <span>Results</span>
          <h2>Leaderboard and scorecards</h2>
          <p>
            Open a candidate scorecard to review results. Use Print / Save as PDF
            on the scorecard for the same report layout.
          </p>
        </div>
        <div className="assessment-row-actions">
          <StatusBadge value={evaluatedCount ? "ready" : "pending"} />
          <Button
            type="button"
            variant="secondary"
            disabled={backfillPending || submittedCandidateIds.length === 0}
            onClick={() => onBackfillEvaluations(submittedCandidateIds)}
          >
            {backfillPending ? "Evaluating..." : "Evaluate Previous"}
          </Button>
          <Button
            type="button"
            disabled={!evaluatedCount || downloadingReport !== null}
            onClick={() => void downloadTestReport()}
          >
            {downloadingReport === "assessment"
              ? "Preparing..."
              : "Download Test Slot PDF"}
          </Button>
        </div>
      </div>
      {backfillResult || backfillError ? (
        <p
          className={`test-feedback-message ${
            backfillError ? "is-error" : "is-success"
          }`}
          role={backfillError ? "alert" : "status"}
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
      <div className="assessment-result-summary">
        <div>
          <span>Evaluated</span>
          <strong>
            {evaluatedCount}/{candidates.length}
          </strong>
        </div>
        <div>
          <span>Submitted</span>
          <strong>
            {submittedCount}/{candidates.length}
          </strong>
        </div>
        <div>
          <span>Average</span>
          <strong>{Math.round(averageScore)}%</strong>
        </div>
      </div>
      <div className="assessment-table-shell">
        <table
          aria-label="Candidate evaluation leaderboard"
          className="assessment-table compact-table"
        >
          <thead>
            <tr>
              <th>Rank</th>
              <th>Candidate</th>
              <th>Score</th>
              <th>Submission</th>
              <th>Scorecard</th>
              <th>Evaluation Status</th>
            </tr>
          </thead>
          <tbody>
            {rankedCandidates.length ? (
              rankedCandidates.map((candidate) => {
                const resultStatus = candidate.percentage === null
                  ? "pending"
                  : candidate.percentage >= assessment.passing_score
                    ? "passed"
                    : "failed";
                return (
                  <tr key={candidate.candidate_assessment_id}>
                    <td>{candidate.rank ? `#${candidate.rank}` : "-"}</td>
                    <td>
                      <div className="assessment-name-cell">
                        <strong>{candidate.name}</strong>
                        <span>{candidate.email}</span>
                      </div>
                    </td>
                    <td>
                      {candidate.percentage !== null
                        ? `${Math.round(candidate.percentage)}%`
                        : "Pending"}
                    </td>
                    <td>
                      {candidate.submitted_at
                        ? new Date(candidate.submitted_at).toLocaleString()
                        : "Not submitted"}
                    </td>
                    <td>
                      {candidate.percentage !== null ? (
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() =>
                            setSelectedCandidateId(
                              candidate.candidate_assessment_id,
                            )
                          }
                        >
                          View Scorecard
                        </Button>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td>
                      <StatusBadge value={resultStatus} />
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={6}>Candidates will appear here after import.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
