import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  Award,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Download,
  FileText,
  Layers3,
  RefreshCcw,
  ShieldCheck,
  TriangleAlert,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { PageHeader } from "../../components/common/PageHeader";
import { EmptyState } from "../../components/common/EmptyState";
import { LoadingState } from "../../components/common/LoadingState";
import { StatusBadge } from "../../components/common/StatusBadge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import {
  useAssessmentSlots,
  useAssessments,
  useSlotCandidates,
} from "../assessments/hooks/useAssessments";
import { useAuth } from "../auth";
import { EvaluationResultList } from "./components/EvaluationResultList";
import {
  averageHiddenPassRate,
  averageRuntime,
  averageScore,
  buildAssessmentOptions,
  buildCandidatesForTest,
  buildPipelineItems,
  buildQuestionAnalytics,
  buildTests,
  makeEmptyDashboard,
  type EvaluationAssessmentOption,
  type EvaluationTest,
} from "./evaluationViewModel";
import {
  backfillAssessmentEvaluations,
  downloadAssessmentEvaluationReport,
  fetchAssessmentEvaluationDashboard,
  retryEvaluationJob,
} from "./services/codeEvaluationService";
import type {
  AssessmentEvaluationDashboard,
  CandidateEvaluationSummary,
  EvaluationBackfillResponse,
} from "./types/EvaluationResult";

type EvaluationView = "assessments" | "assessment" | "test";
type RetryFailedResult = {
  requestedCount: number;
  retriedCount: number;
};

export function CodeEvaluationPage() {
  const { currentUser } = useAuth();
  const queryClient = useQueryClient();
  const [view, setView] = useState<EvaluationView>("assessments");
  const [selectedAssessmentId, setSelectedAssessmentId] = useState("");
  const [selectedTestId, setSelectedTestId] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(
    null,
  );

  const assessmentsQuery = useAssessments(currentUser);
  const assessmentOptions = useMemo(
    () => buildAssessmentOptions(assessmentsQuery.data?.items ?? []),
    [assessmentsQuery.data?.items],
  );
  const selectedAssessment =
    assessmentOptions.find((assessment) => assessment.id === selectedAssessmentId) ??
    assessmentOptions[0] ??
    null;
  const assessmentId = selectedAssessment?.id ?? null;

  useEffect(() => {
    if (!assessmentOptions.length) {
      if (selectedAssessmentId) {
        setSelectedAssessmentId("");
      }
      return;
    }
    if (!assessmentOptions.some((assessment) => assessment.id === selectedAssessmentId)) {
      setSelectedAssessmentId(assessmentOptions[0].id);
      setSelectedTestId(null);
      setSelectedCandidateId(null);
      setView("assessments");
    }
  }, [assessmentOptions, selectedAssessmentId]);

  const slotsQuery = useAssessmentSlots(currentUser, assessmentId);
  const dashboardQuery = useQuery({
    queryKey: ["code-evaluation-dashboard", assessmentId],
    queryFn: async () => {
      if (!currentUser || !assessmentId) {
        throw new Error("Recruiter session is required.");
      }
      return fetchAssessmentEvaluationDashboard(
        await currentUser.getIdToken(),
        assessmentId,
      );
    },
    retry: 1,
    enabled: Boolean(currentUser && assessmentId),
  });

  const dashboard = useMemo(
    () =>
      selectedAssessment
        ? dashboardQuery.data ?? makeEmptyDashboard(selectedAssessment)
        : null,
    [dashboardQuery.data, selectedAssessment],
  );

  const slots = useMemo(
    () => slotsQuery.data?.items ?? selectedAssessment?.slots ?? [],
    [selectedAssessment?.slots, slotsQuery.data?.items],
  );
  const tests = useMemo(
    () =>
      selectedAssessment && dashboard
        ? buildTests(selectedAssessment, slots, dashboard)
        : [],
    [dashboard, selectedAssessment, slots],
  );
  const selectedTest = tests.find((test) => test.id === selectedTestId) ?? tests[0];
  const slotCandidatesQuery = useSlotCandidates(
    currentUser,
    selectedTest?.type === "slot" ? selectedTest.id : null,
  );
  const selectedTestCandidates = useMemo(
    () =>
      buildCandidatesForTest(
        selectedTest,
        dashboard?.leaderboard ?? [],
        selectedTest?.type === "slot" ? slotCandidatesQuery.data?.items : undefined,
      ),
    [dashboard?.leaderboard, selectedTest, slotCandidatesQuery.data?.items],
  );

  useEffect(() => {
    if (!selectedTestId && tests[0]) {
      setSelectedTestId(tests[0].id);
    }
    if (selectedTestId && !tests.some((test) => test.id === selectedTestId)) {
      setSelectedTestId(tests[0]?.id ?? null);
      setSelectedCandidateId(null);
    }
  }, [selectedTestId, tests]);

  const selectedCandidate =
    selectedTestCandidates.find(
      (candidate) => candidate.candidate_assessment_id === selectedCandidateId,
    ) ?? selectedTestCandidates[0] ?? null;
  const selectedAssessmentCandidate =
    dashboard?.leaderboard.find(
      (candidate) => candidate.candidate_assessment_id === selectedCandidateId,
    ) ?? null;
  const pipelineItems = useMemo(
    () => buildPipelineItems(dashboard?.jobs ?? []),
    [dashboard?.jobs],
  );
  const serviceUnavailable =
    dashboardQuery.isError || assessmentsQuery.isError || slotsQuery.isError;
  const backfillMutation = useMutation({
    mutationFn: async () => {
      if (!currentUser) {
        throw new Error("Recruiter session is required.");
      }
      if (!assessmentId) {
        throw new Error("Select an assessment before starting evaluation.");
      }
      return backfillAssessmentEvaluations(await currentUser.getIdToken(), assessmentId);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["assessments"] }),
        queryClient.invalidateQueries({
          queryKey: ["code-evaluation-dashboard", assessmentId],
        }),
      ]);
    },
  });
  const retryFailedMutation = useMutation({
    mutationFn: async (): Promise<RetryFailedResult> => {
      if (!currentUser) {
        throw new Error("Recruiter session is required.");
      }
      const idToken = await currentUser.getIdToken();
      if (!assessmentId) {
        throw new Error("Select an assessment before retrying evaluation.");
      }
      const failedJobs = (dashboard?.jobs ?? []).filter(
        (job) => job.status === "failed",
      );
      const retried = await Promise.all(
        failedJobs.map((job) =>
          retryEvaluationJob(idToken, assessmentId, job.job_id),
        ),
      );
      return {
        requestedCount: failedJobs.length,
        retriedCount: retried.length,
      };
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["code-evaluation-dashboard", assessmentId],
      });
    },
  });
  const downloadReportMutation = useMutation({
    mutationFn: async () => {
      if (!currentUser) {
        throw new Error("Recruiter session is required.");
      }
      if (!assessmentId) {
        throw new Error("Select an assessment before downloading a report.");
      }
      await downloadAssessmentEvaluationReport(await currentUser.getIdToken(), assessmentId);
    },
  });

  return (
    <div className="code-evaluation-page">
      <PageHeader
        title="Code Evaluation"
        description="Review assessments, drill into tests, and inspect individual candidate scorecards."
      />

      {serviceUnavailable ? (
        <div className="evaluation-sync-banner" role="status">
          <TriangleAlert size={18} aria-hidden="true" />
          <span>
            Some live evaluation data is unavailable, so the page is showing the
            best available assessment data.
          </span>
        </div>
      ) : null}

      {assessmentsQuery.isPending ? (
        <LoadingState label="Loading assessments..." />
      ) : null}

      {!assessmentsQuery.isPending && !selectedAssessment ? (
        <EmptyState
          title="No assessments to evaluate"
          description="Create an assessment and invite candidates before opening the evaluation workspace."
        />
      ) : null}

      {selectedAssessment && dashboard ? (
        <><EvaluationBreadcrumbs
        view={view}
        assessmentTitle={selectedAssessment.title}
        testTitle={selectedTest?.title}
        onAssessments={() => {
          setView("assessments");
          setSelectedTestId(null);
          setSelectedCandidateId(null);
        }}
        onAssessment={() => {
          setView("assessment");
          setSelectedCandidateId(null);
        }}
        />

      {view === "assessments" ? (
        <AssessmentsIndex
          assessments={assessmentOptions}
          selectedAssessmentId={selectedAssessment.id}
          onOpen={(assessmentId) => {
            setSelectedAssessmentId(assessmentId);
            setSelectedTestId(null);
            setSelectedCandidateId(null);
            setView("assessment");
          }}
        />
      ) : null}

      {view === "assessment" ? (
        <AssessmentDetail
          dashboard={dashboard}
          assessment={selectedAssessment}
          tests={tests}
          pipelineItems={pipelineItems}
          reportDownloadPending={downloadReportMutation.isPending}
          reportDownloadError={
            downloadReportMutation.error instanceof Error
              ? downloadReportMutation.error.message
              : ""
          }
          backfillResult={backfillMutation.data ?? null}
          backfillError={
            backfillMutation.error instanceof Error
              ? backfillMutation.error.message
              : ""
          }
          backfillPending={backfillMutation.isPending}
          retryFailedResult={retryFailedMutation.data ?? null}
          retryFailedError={
            retryFailedMutation.error instanceof Error
              ? retryFailedMutation.error.message
              : ""
          }
          retryFailedPending={retryFailedMutation.isPending}
          failedJobCount={dashboard.overview.failed_jobs}
          selectedCandidate={selectedAssessmentCandidate}
          onBack={() => setView("assessments")}
          onBackfill={() => backfillMutation.mutate()}
          onRetryFailed={() => retryFailedMutation.mutate()}
          onDownloadReport={() => downloadReportMutation.mutate()}
          onSelectCandidate={setSelectedCandidateId}
          onOpenTest={(testId) => {
            setSelectedTestId(testId);
            setSelectedCandidateId(null);
            setView("test");
          }}
        />
      ) : null}

      {view === "test" && selectedTest ? (
        <TestDetail
          dashboard={dashboard}
          test={selectedTest}
          candidates={selectedTestCandidates}
          selectedCandidate={selectedCandidate}
          onBack={() => {
            setView("assessment");
            setSelectedCandidateId(null);
          }}
          onSelectCandidate={setSelectedCandidateId}
        />
      ) : null}</>
      ) : null}
    </div>
  );
}

function EvaluationBreadcrumbs({
  view,
  assessmentTitle,
  testTitle,
  onAssessments,
  onAssessment,
}: {
  view: EvaluationView;
  assessmentTitle: string;
  testTitle?: string;
  onAssessments: () => void;
  onAssessment: () => void;
}) {
  return (
    <nav className="evaluation-breadcrumbs" aria-label="Evaluation navigation">
      <button type="button" onClick={onAssessments} disabled={view === "assessments"}>
        Assessments
      </button>
      {view !== "assessments" ? (
        <>
          <ChevronRight size={15} aria-hidden="true" />
          <button type="button" onClick={onAssessment} disabled={view === "assessment"}>
            {assessmentTitle}
          </button>
        </>
      ) : null}
      {view === "test" && testTitle ? (
        <>
          <ChevronRight size={15} aria-hidden="true" />
          <span>{testTitle}</span>
        </>
      ) : null}
    </nav>
  );
}

function AssessmentsIndex({
  assessments,
  selectedAssessmentId,
  onOpen,
}: {
  assessments: EvaluationAssessmentOption[];
  selectedAssessmentId: string;
  onOpen: (assessmentId: string) => void;
}) {
  return (
    <>
      <section className="evaluation-hero">
        <div>
          <span className="panel-eyebrow">Evaluation workspace</span>
          <h2>Assessments</h2>
          <p>
            Open an assessment to review its tests, score pipeline, candidate
            ranking, and downloadable reports.
          </p>
        </div>
      </section>

      <section className="evaluation-assessment-grid" aria-label="Assessments">
        {assessments.map((assessment) => (
          <button
            type="button"
            key={assessment.id}
            className={`evaluation-assessment-card ${
              selectedAssessmentId === assessment.id ? "is-selected" : ""
            }`}
            onClick={() => onOpen(assessment.id)}
          >
            <span>
              <Layers3 size={18} aria-hidden="true" />
            </span>
            <div>
              <strong>{assessment.title}</strong>
              <p>{assessment.description || "Coding evaluation assessment"}</p>
              <dl>
                <div>
                  <dt>Tests</dt>
                  <dd>{assessment.testCount}</dd>
                </div>
                <div>
                  <dt>Candidates</dt>
                  <dd>{assessment.candidateCount}</dd>
                </div>
                <div>
                  <dt>Submitted</dt>
                  <dd>{assessment.submittedCount}</dd>
                </div>
              </dl>
            </div>
            <ChevronRight size={18} aria-hidden="true" />
          </button>
        ))}
      </section>
    </>
  );
}

function AssessmentDetail({
  dashboard,
  assessment,
  tests,
  pipelineItems,
  reportDownloadPending,
  reportDownloadError,
  backfillResult,
  backfillError,
  backfillPending,
  retryFailedResult,
  retryFailedError,
  retryFailedPending,
  failedJobCount,
  selectedCandidate,
  onBack,
  onBackfill,
  onRetryFailed,
  onDownloadReport,
  onSelectCandidate,
  onOpenTest,
}: {
  dashboard: AssessmentEvaluationDashboard;
  assessment: EvaluationAssessmentOption;
  tests: EvaluationTest[];
  pipelineItems: ReturnType<typeof buildPipelineItems>;
  reportDownloadPending: boolean;
  reportDownloadError: string;
  backfillResult: EvaluationBackfillResponse | null;
  backfillError: string;
  backfillPending: boolean;
  retryFailedResult: RetryFailedResult | null;
  retryFailedError: string;
  retryFailedPending: boolean;
  failedJobCount: number;
  selectedCandidate: CandidateEvaluationSummary | null;
  onBack: () => void;
  onBackfill: () => void;
  onRetryFailed: () => void;
  onDownloadReport: () => void;
  onSelectCandidate: (candidateAssessmentId: string) => void;
  onOpenTest: (testId: string) => void;
}) {
  const questionAnalytics = buildQuestionAnalytics(dashboard.leaderboard);

  return (
    <>
      <section className="evaluation-hero">
        <div>
          <button type="button" className="evaluation-back-link" onClick={onBack}>
            <ArrowLeft size={15} aria-hidden="true" />
            Assessments
          </button>
          <span className="panel-eyebrow">Assessment</span>
          <h2>{assessment.title}</h2>
          <p>{assessment.description || "Evaluation summary and test drill-down."}</p>
        </div>
        <div className="evaluation-hero-actions">
          <Button
            variant="secondary"
            type="button"
            disabled={retryFailedPending || failedJobCount === 0}
            onClick={onRetryFailed}
          >
            <RefreshCcw size={16} aria-hidden="true" />
            {retryFailedPending ? "Re-running..." : "Re-run failed"}
          </Button>
          <Button
            variant="secondary"
            type="button"
            disabled={backfillPending}
            onClick={onBackfill}
          >
            <CheckCircle2 size={16} aria-hidden="true" />
            {backfillPending ? "Evaluating..." : "Evaluate previous"}
          </Button>
          <Button
            type="button"
            disabled={reportDownloadPending}
            onClick={onDownloadReport}
          >
            <Download size={16} aria-hidden="true" />
            {reportDownloadPending ? "Preparing..." : "Export reports"}
          </Button>
        </div>
      </section>

      {reportDownloadError ? (
        <div className="evaluation-backfill-banner is-error" role="alert">
          {reportDownloadError}
        </div>
      ) : null}

      {backfillResult || backfillError ? (
        <div
          className={`evaluation-backfill-banner ${
            backfillError ? "is-error" : "is-success"
          }`}
          role="status"
        >
          {backfillError ? (
            <>
              <TriangleAlert size={18} aria-hidden="true" />
              <span>{backfillError}</span>
            </>
          ) : (
            <>
              <CheckCircle2 size={18} aria-hidden="true" />
              <span>
                Evaluated {backfillResult?.evaluated_count ?? 0} previous
                submissions, skipped {backfillResult?.skipped_count ?? 0}, failed{" "}
                {backfillResult?.failed_count ?? 0}.
              </span>
            </>
          )}
        </div>
      ) : null}

      {retryFailedResult || retryFailedError ? (
        <div
          className={`evaluation-backfill-banner ${
            retryFailedError ? "is-error" : "is-success"
          }`}
          role="status"
        >
          {retryFailedError ? (
            <>
              <TriangleAlert size={18} aria-hidden="true" />
              <span>{retryFailedError}</span>
            </>
          ) : (
            <>
              <CheckCircle2 size={18} aria-hidden="true" />
              <span>
                Re-ran {retryFailedResult?.retriedCount ?? 0} of{" "}
                {retryFailedResult?.requestedCount ?? 0} failed evaluation jobs.
              </span>
            </>
          )}
        </div>
      ) : null}

      <EvaluationMetrics dashboard={dashboard} />

      <section
        className={`evaluation-workspace ${
          selectedCandidate ? "" : "evaluation-workspace-single"
        }`}
      >
        <div className="evaluation-left">
          <Card className="evaluation-panel">
            <div className="card-head">
              <div>
                <span>Tests</span>
                <h2>Assessment tests</h2>
                <p>
                  Each test opens into the candidate list with score, hidden
                  checks, runtime, and AI quality details.
                </p>
              </div>
              <StatusBadge value={dashboard.overview.report_status} />
            </div>
            <div className="evaluation-test-grid">
              {tests.map((test) => (
                <button
                  type="button"
                  className="evaluation-test-card"
                  key={test.id}
                  onClick={() => onOpenTest(test.id)}
                >
                  <span>
                    <FileText size={17} aria-hidden="true" />
                  </span>
                  <div>
                    <strong>{test.title}</strong>
                    <small>{test.type === "slot" ? "Scheduled test" : "Question test"}</small>
                    <dl>
                      <div>
                        <dt>Candidates</dt>
                        <dd>{test.candidateCount}</dd>
                      </div>
                      <div>
                        <dt>Submitted</dt>
                        <dd>{test.submittedCount}</dd>
                      </div>
                      <div>
                        <dt>Status</dt>
                        <dd>{test.status}</dd>
                      </div>
                    </dl>
                  </div>
                  <ChevronRight size={18} aria-hidden="true" />
                </button>
              ))}
            </div>
          </Card>

          <Card className="evaluation-panel">
            <div className="card-head">
              <div>
                <span>Analytics</span>
                <h2>Overall test analytics</h2>
                <p>
                  Question-wise average score, hidden pass rate, and attempted
                  candidate count for the generated assessment report.
                </p>
              </div>
            </div>
            {questionAnalytics.length ? (
              <div className="evaluation-analytics-grid">
                {questionAnalytics.map((question) => (
                  <article key={question.questionId} className="evaluation-analytics-card">
                    <div>
                      <strong>{question.title}</strong>
                      <span>{question.candidateCount} candidates</span>
                    </div>
                    <dl>
                      <div>
                        <dt>Avg score</dt>
                        <dd>{Math.round(question.averageScore)}%</dd>
                      </div>
                      <div>
                        <dt>Pass rate</dt>
                        <dd>{Math.round(question.passRate)}%</dd>
                      </div>
                      <div>
                        <dt>Cases</dt>
                        <dd>
                          {question.passedCases}/{question.totalCases}
                        </dd>
                      </div>
                    </dl>
                  </article>
                ))}
              </div>
            ) : (
              <div className="evaluation-empty-state">
                <Activity size={22} aria-hidden="true" />
                <strong>No analytics yet</strong>
                <p>Analytics will appear after at least one candidate is evaluated.</p>
              </div>
            )}
          </Card>

          <Card className="evaluation-panel">
            <div className="card-head">
              <div>
                <span>Leaderboard</span>
                <h2>Candidate ranking</h2>
                <p>
                  Select a candidate to open the full scorecard with submitted
                  code and hidden test evidence.
                </p>
              </div>
            </div>
            {dashboard.leaderboard.length ? (
              <EvaluationResultList
                results={dashboard.leaderboard}
                selectedId={selectedCandidate?.candidate_assessment_id ?? ""}
                onSelect={onSelectCandidate}
              />
            ) : (
              <div className="evaluation-empty-state">
                <Users size={22} aria-hidden="true" />
                <strong>No ranked candidates yet</strong>
                <p>Run evaluation or backfill previous submissions to populate ranking.</p>
              </div>
            )}
          </Card>

          <Card className="evaluation-panel">
            <div className="card-head">
              <div>
                <span>Job pipeline</span>
                <h2>Evaluation status</h2>
                <p>
                  Tracks final hidden execution, score calculation, AI review,
                  ranking, and report generation.
                </p>
              </div>
            </div>
            <div className="evaluation-pipeline">
              {pipelineItems.map((item) => (
                <div key={item.label} className={`pipeline-step ${item.state}`}>
                  <span>
                    <CheckCircle2 size={16} aria-hidden="true" />
                  </span>
                  <div>
                    <strong>{item.label}</strong>
                    <small>{item.detail}</small>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
        {selectedCandidate ? (
          <CandidateScorecard candidate={selectedCandidate} />
        ) : null}
      </section>
    </>
  );
}

function TestDetail({
  dashboard,
  test,
  candidates,
  selectedCandidate,
  onBack,
  onSelectCandidate,
}: {
  dashboard: AssessmentEvaluationDashboard;
  test: EvaluationTest;
  candidates: CandidateEvaluationSummary[];
  selectedCandidate: CandidateEvaluationSummary | null;
  onBack: () => void;
  onSelectCandidate: (candidateAssessmentId: string) => void;
}) {
  return (
    <>
      <section className="evaluation-hero">
        <div>
          <button type="button" className="evaluation-back-link" onClick={onBack}>
            <ArrowLeft size={15} aria-hidden="true" />
            Assessment
          </button>
          <span className="panel-eyebrow">
            {test.type === "slot" ? "Scheduled test" : "Question test"}
          </span>
          <h2>{test.title}</h2>
          <p>
            Review every evaluated candidate in this test and open their
            scorecard without leaving the evaluation flow.
          </p>
        </div>
      </section>

      <section className="evaluation-metrics" aria-label="Test metrics">
        <MetricCard
          icon={<Users size={18} />}
          label="Candidates"
          value={String(test.candidateCount || candidates.length)}
          detail={`${test.submittedCount || candidates.length} submitted`}
        />
        <MetricCard
          icon={<Award size={18} />}
          label="Average score"
          value={`${Math.round(averageScore(candidates))}%`}
          detail={`Top score ${Math.round(dashboard.overview.highest_score)}%`}
        />
        <MetricCard
          icon={<ShieldCheck size={18} />}
          label="Hidden tests"
          value={`${Math.round(averageHiddenPassRate(candidates))}%`}
          detail="Average pass rate"
        />
        <MetricCard
          icon={<Clock3 size={18} />}
          label="Runtime"
          value={`${Math.round(averageRuntime(candidates))} ms`}
          detail="Average execution time"
        />
      </section>

      <section className="evaluation-workspace">
        <div className="evaluation-left">
          <Card className="evaluation-panel">
            <div className="card-head">
              <div>
                <span>Candidates</span>
                <h2>Individual candidates</h2>
                <p>
                  Select a row to inspect final score, hidden case performance,
                  runtime, memory, and AI review.
                </p>
              </div>
            </div>
            {candidates.length ? (
              <EvaluationResultList
                results={candidates}
                selectedId={selectedCandidate?.candidate_assessment_id ?? ""}
                onSelect={onSelectCandidate}
              />
            ) : (
              <div className="evaluation-empty-state">
                <Users size={22} aria-hidden="true" />
                <strong>No evaluated candidates yet</strong>
                <p>Submitted candidates will appear here once scoring is complete.</p>
              </div>
            )}
          </Card>
        </div>

        {selectedCandidate ? (
          <CandidateScorecard candidate={selectedCandidate} test={test} />
        ) : null}
      </section>
    </>
  );
}

function EvaluationMetrics({
  dashboard,
}: {
  dashboard: AssessmentEvaluationDashboard;
}) {
  return (
    <section className="evaluation-metrics" aria-label="Evaluation metrics">
      <MetricCard
        icon={<Award size={18} />}
        label="Average score"
        value={`${Math.round(dashboard.overview.average_score)}%`}
        detail={`${dashboard.overview.completed_candidates}/${dashboard.overview.total_candidates} completed`}
      />
      <MetricCard
        icon={<ShieldCheck size={18} />}
        label="Pass rate"
        value={`${Math.round(dashboard.overview.pass_rate)}%`}
        detail="Passing score 40%"
      />
      <MetricCard
        icon={<Activity size={18} />}
        label="Test accuracy"
        value={`${Math.round(dashboard.overview.average_test_case_score)}%`}
        detail="Hidden cases only"
      />
      <MetricCard
        icon={<Clock3 size={18} />}
        label="Pending jobs"
        value={String(dashboard.overview.pending_jobs)}
        detail={`${dashboard.overview.failed_jobs} failed`}
      />
    </section>
  );
}

function MetricCard({
  icon,
  label,
  value,
  detail,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <Card className="evaluation-metric-card">
      <span>{icon}</span>
      <div>
        <strong>{value}</strong>
        <small>{label}</small>
        <p>{detail}</p>
      </div>
    </Card>
  );
}

function CandidateScorecard({
  candidate,
  test,
}: {
  candidate: CandidateEvaluationSummary;
  test?: EvaluationTest;
}) {
  const questionBreakdown =
    test?.type === "question"
      ? candidate.question_breakdown.filter((question) => question.question_id === test.id)
      : candidate.question_breakdown;

  return (
    <aside className="evaluation-scorecard" aria-label="Candidate scorecard">
      <div className="scorecard-head">
        <div>
          <span>Scorecard</span>
          <h2>{candidate.candidate_name}</h2>
          <p>{candidate.candidate_email}</p>
        </div>
        <strong>#{candidate.rank || "-"}</strong>
      </div>

      <div className="score-ring" aria-label="Final score">
        <strong>{Math.round(candidate.scores.final_score)}%</strong>
        <span>Final score</span>
      </div>

      <div className="score-split">
        <ScorePart label="Hidden tests" value={candidate.scores.test_case_score} />
        <ScorePart label="Coding metrics" value={candidate.scores.coding_score} />
        <ScorePart label="AI quality" value={candidate.scores.ai_score} />
      </div>

      <div className="scorecard-facts">
        <div>
          <span>Hidden pass</span>
          <strong>
            {candidate.hidden_passed}/{candidate.hidden_total}
          </strong>
        </div>
        <div>
          <span>Runtime</span>
          <strong>{Math.round(candidate.total_execution_time_ms)} ms</strong>
        </div>
        <div>
          <span>Peak memory</span>
          <strong>{formatMemory(candidate.peak_memory_kb)}</strong>
        </div>
        <div>
          <span>Language</span>
          <strong>{candidate.language}</strong>
        </div>
      </div>

      <section className="ai-feedback-panel">
        <div className="mini-section-head">
          <FileText size={17} aria-hidden="true" />
          <h3>AI code quality</h3>
        </div>
        <p>{candidate.ai_quality.approach}</p>
        <dl>
          <div>
            <dt>Time</dt>
            <dd>{candidate.ai_quality.time_complexity}</dd>
          </div>
          <div>
            <dt>Space</dt>
            <dd>{candidate.ai_quality.space_complexity}</dd>
          </div>
        </dl>
      </section>

      <section className="question-breakdown">
        <div className="mini-section-head">
          <Activity size={17} aria-hidden="true" />
          <h3>{test?.type === "question" ? "Test breakdown" : "Question breakdown"}</h3>
        </div>
        {questionBreakdown.map((question) => (
          <article key={question.question_id} className="scorecard-question-detail">
            <header>
              <div>
                <strong>{question.question_title}</strong>
                <span>
                  {question.passed_count}/{question.total_count} hidden cases
                </span>
              </div>
              <small>{Math.round(question.score)}%</small>
            </header>
            <meter min="0" max="100" value={question.score} />
            <div className="scorecard-code-block">
              <span>{question.language || candidate.language}</span>
              <pre>{question.submitted_code || "No submitted code available."}</pre>
            </div>
            <div className="scorecard-case-list">
              {question.test_cases.length ? (
                question.test_cases.map((testCase) => (
                  <div key={testCase.test_case_id}>
                    <strong>{testCase.passed ? "Passed" : "Failed"}</strong>
                    <span>{testCase.verdict.replace(/_/g, " ")}</span>
                    <span>{Math.round(testCase.execution_time_ms ?? 0)} ms</span>
                    <span>{formatMemory(testCase.memory_kb ?? 0)}</span>
                  </div>
                ))
              ) : (
                <p>No hidden case rows were stored for this evaluation.</p>
              )}
            </div>
          </article>
        ))}
      </section>
    </aside>
  );
}

function ScorePart({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{Math.round(value)}%</strong>
    </div>
  );
}

function formatMemory(memoryKb: number) {
  if (memoryKb >= 1024) {
    return `${Math.round(memoryKb / 1024)} MB`;
  }
  return `${memoryKb} KB`;
}
