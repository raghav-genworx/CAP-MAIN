import {
  ArrowLeft,
  CheckCircle2,
  Clock3,
  Printer,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import { Button } from "../../../components/ui/Button";
import type {
  CandidateBenchmarkContext,
  CandidateEvaluationSummary,
} from "../../codeEvaluation/types/EvaluationResult";
import type { Assessment, AssessmentSlot } from "../types/Assessment";

export interface ScorecardSettings {
  test_case_score_weight: number;
  coding_score_weight: number;
  ai_score_weight: number;
  passing_score: number;
  proctoring_mode: string;
  allow_resume: boolean;
  supported_languages: string[];
  duration_minutes: number;
  slot_title?: string;
  slot_duration_minutes?: number;
}

interface RecruiterScorecardPreviewProps {
  candidate: CandidateEvaluationSummary | null;
  benchmark?: CandidateBenchmarkContext | null;
  settings?: ScorecardSettings | null;
  loading: boolean;
  error: string;
  onBack?: () => void;
  fullPage?: boolean;
}

function hasText(value: string | null | undefined) {
  return Boolean(value && value.trim() && value.trim() !== "Not available");
}

function hasNumber(value: number | null | undefined) {
  return value !== null && value !== undefined && Number.isFinite(value);
}

function durationLabel(seconds: number | null | undefined) {
  if (!hasNumber(seconds)) {
    return null;
  }
  const total = Math.max(0, Math.floor(seconds as number));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  return hours
    ? `${hours}h ${minutes}m ${remainder}s`
    : `${minutes}m ${remainder}s`;
}

function dateTimeLabel(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : null;
}

function memoryLabel(kb: number | null | undefined) {
  if (!hasNumber(kb) || (kb as number) <= 0) {
    return null;
  }
  return (kb as number) >= 1024
    ? `${((kb as number) / 1024).toFixed(1)} MB`
    : `${kb} KB`;
}

function proctoringLabel(mode: string) {
  if (mode === "strict") {
    return "Strict monitoring";
  }
  if (mode === "basic") {
    return "Basic monitoring";
  }
  if (mode === "none") {
    return "No proctoring";
  }
  return mode;
}

function recommendation(
  candidate: CandidateEvaluationSummary,
  settings: ScorecardSettings,
  options: {
    includeAi: boolean;
    includeIntegrity: boolean;
  },
) {
  const hiddenRate = candidate.hidden_total
    ? (candidate.hidden_passed / candidate.hidden_total) * 100
    : 0;
  const suspicious = options.includeIntegrity
    ? (candidate.integrity?.suspicious_activity?.length ?? 0)
    : 0;
  const similarity = options.includeIntegrity
    ? candidate.integrity?.plagiarism_similarity_score
    : null;
  const aiScore = options.includeAi ? candidate.scores.ai_score : 100;
  const passMark = settings.passing_score;

  if (
    options.includeIntegrity &&
    (suspicious > 0 || (similarity ?? 0) >= 70)
  ) {
    return {
      label: "Manual Review Required",
      tone: "warning",
      detail:
        "Integrity signals need recruiter review before a hiring decision.",
    };
  }
  if (!candidate.hidden_total && settings.test_case_score_weight > 0) {
    return {
      label: "Manual Review Required",
      tone: "warning",
      detail: "Hidden-test evidence is incomplete for this candidate.",
    };
  }
  if (
    candidate.scores.final_score >= Math.max(85, passMark + 15) &&
    (settings.test_case_score_weight === 0 || hiddenRate >= 85) &&
    (!options.includeAi || aiScore >= 75)
  ) {
    return {
      label: "Strong Hire",
      tone: "positive",
      detail: "Strong results against the configured scoring policy.",
    };
  }
  if (
    candidate.scores.final_score >= passMark &&
    (settings.test_case_score_weight === 0 || hiddenRate >= passMark) &&
    (!options.includeAi || aiScore >= 60)
  ) {
    return {
      label: "Hire",
      tone: "positive",
      detail: `Meets the assessment pass mark of ${passMark}%.`,
    };
  }
  if (
    candidate.scores.final_score < Math.min(40, passMark) ||
    (settings.test_case_score_weight > 0 && hiddenRate < 40)
  ) {
    return {
      label: "Reject",
      tone: "negative",
      detail: "Results are below the reliability threshold for this assessment.",
    };
  }
  return {
    label: "Further Review",
    tone: "warning",
    detail: "The score profile is mixed; review question evidence before deciding.",
  };
}

function EvidenceList({ title, values }: { title: string; values: string[] }) {
  if (!values.length) {
    return null;
  }
  return (
    <div className="scorecard-evidence-list">
      <strong>{title}</strong>
      <ul>
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
}

function coverageSummary(
  testCases: CandidateEvaluationSummary["question_breakdown"][number]["test_cases"],
) {
  const grouped = new Map<string, { total: number; passed: number }>();
  testCases.forEach((testCase) => {
    const category = testCase.case_category || "Hidden validation";
    const current = grouped.get(category) ?? { total: 0, passed: 0 };
    current.total += 1;
    current.passed += testCase.passed ? 1 : 0;
    grouped.set(category, current);
  });
  return [...grouped.entries()];
}

function ScoreBar({
  label,
  value,
  weight,
}: {
  label: string;
  value: number;
  weight: number;
}) {
  return (
    <div className="scorecard-score-bar">
      <div className="scorecard-score-bar-head">
        <span>{label}</span>
        <strong>
          {value.toFixed(1)}%
          <em>· {weight.toFixed(0)}% weight</em>
        </strong>
      </div>
      <div className="scorecard-score-bar-track" aria-hidden="true">
        <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string | null }) {
  if (!value) {
    return null;
  }
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function printScorecard() {
  window.print();
}

export function buildScorecardSettings(
  assessment: Assessment,
  slot?: AssessmentSlot | null,
): ScorecardSettings {
  return {
    test_case_score_weight: assessment.test_case_score_weight,
    coding_score_weight: assessment.coding_score_weight,
    ai_score_weight: assessment.ai_score_weight,
    passing_score: assessment.passing_score,
    proctoring_mode: assessment.proctoring_mode,
    allow_resume: assessment.allow_resume,
    supported_languages: assessment.supported_languages,
    duration_minutes: assessment.duration_minutes,
    slot_title: slot?.title,
    slot_duration_minutes: slot?.duration_minutes,
  };
}

export function RecruiterScorecardPreview({
  candidate,
  benchmark = null,
  settings = null,
  loading,
  error,
  onBack,
  fullPage = false,
}: RecruiterScorecardPreviewProps) {
  if (loading) {
    return (
      <div className="recruiter-scorecard-preview">
        {onBack ? (
          <Button type="button" variant="secondary" onClick={onBack}>
            <ArrowLeft size={16} aria-hidden="true" />
            Back to results
          </Button>
        ) : null}
        <strong>Loading scorecard...</strong>
      </div>
    );
  }

  if (error || !candidate) {
    return (
      <div className="recruiter-scorecard-preview is-error" role="alert">
        {onBack ? (
          <Button type="button" variant="secondary" onClick={onBack}>
            <ArrowLeft size={16} aria-hidden="true" />
            Back to results
          </Button>
        ) : null}
        <strong>{error || "Scorecard unavailable."}</strong>
      </div>
    );
  }

  const resolvedSettings: ScorecardSettings = settings ?? {
    test_case_score_weight: candidate.weights?.test_case_weight ?? 60,
    coding_score_weight: candidate.weights?.coding_weight ?? 20,
    ai_score_weight: candidate.weights?.ai_weight ?? 20,
    passing_score: 60,
    proctoring_mode: candidate.integrity?.proctoring_mode || "none",
    allow_resume: false,
    supported_languages: [],
    duration_minutes: 0,
  };

  const showHiddenScore = resolvedSettings.test_case_score_weight > 0;
  const showCodingScore = resolvedSettings.coding_score_weight > 0;
  const showAiScore = resolvedSettings.ai_score_weight > 0;
  const showProctoring = resolvedSettings.proctoring_mode !== "none";
  const showFullscreen =
    resolvedSettings.proctoring_mode === "strict" &&
    hasNumber(candidate.integrity?.fullscreen_exits);
  const showClipboard =
    showProctoring && hasNumber(candidate.integrity?.copy_paste_count);
  const showTabSwitches =
    showProctoring && hasNumber(candidate.integrity?.tab_switches);
  const showSimilarity = hasNumber(
    candidate.integrity?.plagiarism_similarity_score,
  );
  const integrityNotes = candidate.integrity?.suspicious_activity ?? [];
  const showIntegritySection =
    showProctoring || showSimilarity || integrityNotes.length > 0;

  const activity = candidate.activity;
  const timeTaken = durationLabel(
    activity?.total_time_seconds ?? candidate.time_taken_seconds,
  );
  const startedAt = dateTimeLabel(activity?.started_at);
  const submittedAt = dateTimeLabel(
    activity?.submitted_at ?? candidate.submitted_at,
  );
  const runtimeLabel =
    hasNumber(candidate.total_execution_time_ms) &&
    candidate.total_execution_time_ms > 0
      ? `${candidate.total_execution_time_ms.toFixed(0)} ms`
      : null;
  const peakMemory = memoryLabel(candidate.peak_memory_kb);
  const questionTitles = new Map(
    candidate.question_breakdown.map((question) => [
      question.question_id,
      question.question_title,
    ]),
  );
  const questionTimes = Object.entries(activity?.question_time_seconds ?? {}).filter(
    ([, seconds]) => hasNumber(seconds) && (seconds as number) > 0,
  );
  const hiddenRate = candidate.hidden_total
    ? Math.round((candidate.hidden_passed / candidate.hidden_total) * 100)
    : null;
  const decision = recommendation(candidate, resolvedSettings, {
    includeAi: showAiScore,
    includeIntegrity: showIntegritySection,
  });

  const scoreComponents = [
    showHiddenScore
      ? {
          label: "Hidden test correctness",
          weight: resolvedSettings.test_case_score_weight,
          score: candidate.scores.test_case_score,
        }
      : null,
    showCodingScore
      ? {
          label: "Coding / runtime metrics",
          weight: resolvedSettings.coding_score_weight,
          score: candidate.scores.coding_score,
        }
      : null,
    showAiScore
      ? {
          label: "AI code quality",
          weight: resolvedSettings.ai_score_weight,
          score: candidate.scores.ai_score,
        }
      : null,
  ].filter(Boolean) as Array<{ label: string; weight: number; score: number }>;

  const sessionFacts = [
    {
      label: "Test slot",
      value: resolvedSettings.slot_title || null,
    },
    {
      label: "Language",
      value: hasText(candidate.language) ? candidate.language : null,
    },
    {
      label: "Allowed languages",
      value: resolvedSettings.supported_languages.length
        ? resolvedSettings.supported_languages.join(", ")
        : null,
    },
    {
      label: "Pass mark",
      value: `${resolvedSettings.passing_score}%`,
    },
    {
      label: "Duration",
      value: `${
        resolvedSettings.slot_duration_minutes ||
        resolvedSettings.duration_minutes
      } min`,
    },
    {
      label: "Resume policy",
      value: resolvedSettings.allow_resume
        ? "Resume allowed"
        : "Single attempt",
    },
    {
      label: "Hidden cases",
      value:
        showHiddenScore && candidate.hidden_total > 0
          ? `${candidate.hidden_passed}/${candidate.hidden_total}${
              hiddenRate != null ? ` (${hiddenRate}%)` : ""
            }`
          : null,
    },
    { label: "Time taken", value: timeTaken },
    { label: "Runtime total", value: showCodingScore ? runtimeLabel : null },
    { label: "Peak memory", value: showCodingScore ? peakMemory : null },
    { label: "Started", value: startedAt },
    { label: "Submitted", value: submittedAt },
    {
      label: "Benchmark",
      value:
        benchmark?.candidate_rank != null
          ? `#${benchmark.candidate_rank}/${benchmark.total_candidates}${
              hasNumber(benchmark.average_score)
                ? ` · avg ${benchmark.average_score!.toFixed(1)}%`
                : ""
            }`
          : null,
    },
  ].filter((fact) => Boolean(fact.value));

  const aiQuality = candidate.ai_quality;
  const showAiSection =
    showAiScore &&
    Boolean(
      hasText(aiQuality?.approach) ||
        hasText(aiQuality?.readability) ||
        hasText(aiQuality?.maintainability) ||
        hasText(aiQuality?.time_complexity) ||
        (aiQuality?.strengths?.length ?? 0) > 0 ||
        (aiQuality?.weaknesses?.length ?? 0) > 0 ||
        (aiQuality?.improvements?.length ?? 0) > 0 ||
        hasNumber(aiQuality?.score),
    );

  if (!fullPage) {
    return (
      <div className="recruiter-scorecard-preview">
        <div className="scorecard-head">
          <div>
            <span>Candidate scorecard</span>
            <h2>{candidate.candidate_name}</h2>
            <p>{candidate.candidate_email}</p>
          </div>
          <Button type="button" variant="secondary" onClick={printScorecard}>
            <Printer size={16} aria-hidden="true" />
            Print / Save PDF
          </Button>
        </div>
        <div className="assessment-result-summary">
          {candidate.rank ? (
            <div>
              <span>Rank</span>
              <strong>#{candidate.rank}</strong>
            </div>
          ) : null}
          <div>
            <span>Final</span>
            <strong>{candidate.scores.final_score.toFixed(1)}%</strong>
          </div>
          {showHiddenScore && candidate.hidden_total > 0 ? (
            <div>
              <span>Hidden cases</span>
              <strong>
                {candidate.hidden_passed}/{candidate.hidden_total}
              </strong>
            </div>
          ) : null}
        </div>
        <div className="recruiter-scorecard-questions">
          {candidate.question_breakdown.map((question) => (
            <article key={question.question_id}>
              <header>
                <div>
                  <strong>{question.question_title}</strong>
                  {question.total_count > 0 ? (
                    <span>
                      {question.passed_count}/{question.total_count} cases
                      passed
                    </span>
                  ) : null}
                </div>
                <strong>
                  {(question.earned_marks ?? 0).toFixed(1)}/
                  {(question.assigned_marks ?? question.total_points).toFixed(1)}
                </strong>
              </header>
            </article>
          ))}
        </div>
      </div>
    );
  }

  let sectionNumber = 1;

  return (
    <div className="recruiter-scorecard-preview is-full-page">
      <div className="scorecard-page-actions no-print">
        {onBack ? (
          <Button type="button" variant="secondary" onClick={onBack}>
            <ArrowLeft size={16} aria-hidden="true" />
            Back to results
          </Button>
        ) : (
          <span />
        )}
        <Button type="button" onClick={printScorecard}>
          <Printer size={16} aria-hidden="true" />
          Print / Save as PDF
        </Button>
      </div>

      <article className="scorecard-document" id="candidate-scorecard-print">
        <header className="scorecard-doc-header">
          <div className="scorecard-doc-brand">
            <span>Candidate evaluation report</span>
            <h1>{candidate.candidate_name}</h1>
            <p>{candidate.candidate_email}</p>
            {resolvedSettings.slot_title ? (
              <p className="scorecard-doc-slot">{resolvedSettings.slot_title}</p>
            ) : null}
          </div>
          <div className="scorecard-doc-score">
            <span>Final score</span>
            <strong>{candidate.scores.final_score.toFixed(1)}%</strong>
            <em>
              {[
                candidate.rank ? `Rank #${candidate.rank}` : null,
                `Pass mark ${resolvedSettings.passing_score}%`,
                showHiddenScore && hiddenRate != null
                  ? `Hidden pass ${hiddenRate}%`
                  : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </em>
          </div>
        </header>

        <section className={`scorecard-recommendation is-${decision.tone}`}>
          <div>
            <span>Recommendation</span>
            <strong>{decision.label}</strong>
          </div>
          <p>{decision.detail}</p>
        </section>

        {scoreComponents.length ? (
          <section className="scorecard-section">
            <div className="scorecard-section-heading">
              <span>{String(sectionNumber++).padStart(2, "0")}</span>
              <h2>Score breakdown</h2>
            </div>
            <p className="scorecard-section-note">
              Based on this assessment&apos;s scoring weights
              {showHiddenScore
                ? ` · tests ${resolvedSettings.test_case_score_weight}%`
                : ""}
              {showCodingScore
                ? ` · coding ${resolvedSettings.coding_score_weight}%`
                : ""}
              {showAiScore
                ? ` · AI ${resolvedSettings.ai_score_weight}%`
                : ""}
              .
            </p>
            <div className="scorecard-score-bars">
              {scoreComponents.map((component) => (
                <ScoreBar
                  key={component.label}
                  label={component.label}
                  value={component.score}
                  weight={component.weight}
                />
              ))}
            </div>
            {scoreComponents.length > 1 ? (
              <div className="scorecard-table-shell">
                <table className="scorecard-detail-table scorecard-breakdown-table">
                  <thead>
                    <tr>
                      <th>Component</th>
                      <th>Weight</th>
                      <th>Raw score</th>
                      <th>Weighted</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scoreComponents.map((component) => (
                      <tr key={component.label}>
                        <td>{component.label}</td>
                        <td>{component.weight.toFixed(0)}%</td>
                        <td>{component.score.toFixed(1)}%</td>
                        <td>
                          {(
                            (component.weight * component.score) /
                            100
                          ).toFixed(1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
        ) : null}

        {sessionFacts.length || questionTimes.length || showIntegritySection ? (
          <section className="scorecard-section">
            <div className="scorecard-section-heading">
              <span>{String(sectionNumber++).padStart(2, "0")}</span>
              <h2>Session snapshot</h2>
            </div>
            {sessionFacts.length ? (
              <dl className="scorecard-facts">
                {sessionFacts.map((fact) => (
                  <Fact key={fact.label} label={fact.label} value={fact.value} />
                ))}
              </dl>
            ) : null}

            {questionTimes.length || showIntegritySection ? (
              <div
                className={
                  questionTimes.length && showIntegritySection
                    ? "scorecard-two-col"
                    : "scorecard-one-col"
                }
              >
                {questionTimes.length ? (
                  <div className="scorecard-subsection">
                    <h3>
                      <Clock3 size={15} aria-hidden="true" />
                      Time by question
                    </h3>
                    <dl className="scorecard-question-times">
                      {questionTimes.map(([id, seconds]) => (
                        <div key={id}>
                          <dt>{questionTitles.get(id) || id}</dt>
                          <dd>{durationLabel(seconds)}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ) : null}

                {showIntegritySection ? (
                  <div className="scorecard-subsection">
                    <h3>
                      <ShieldAlert size={15} aria-hidden="true" />
                      Integrity signals
                    </h3>
                    <dl className="scorecard-facts scorecard-facts-compact">
                      <Fact
                        label="Proctoring"
                        value={proctoringLabel(resolvedSettings.proctoring_mode)}
                      />
                      {showTabSwitches ? (
                        <Fact
                          label="Tab switches"
                          value={String(candidate.integrity?.tab_switches)}
                        />
                      ) : null}
                      {showClipboard ? (
                        <Fact
                          label="Copy / paste"
                          value={String(candidate.integrity?.copy_paste_count)}
                        />
                      ) : null}
                      {showFullscreen ? (
                        <Fact
                          label="Fullscreen exits"
                          value={String(candidate.integrity?.fullscreen_exits)}
                        />
                      ) : null}
                      {showSimilarity ? (
                        <Fact
                          label="Similarity"
                          value={`${candidate.integrity!.plagiarism_similarity_score!.toFixed(1)}%`}
                        />
                      ) : null}
                    </dl>
                    <EvidenceList title="Integrity notes" values={integrityNotes} />
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        ) : null}

        {showAiSection ? (
          <section className="scorecard-section">
            <div className="scorecard-section-heading">
              <span>{String(sectionNumber++).padStart(2, "0")}</span>
              <h2>Code quality review</h2>
            </div>
            <dl className="scorecard-review-grid">
              {hasText(aiQuality.approach) ? (
                <div>
                  <dt>Approach</dt>
                  <dd>{aiQuality.approach}</dd>
                </div>
              ) : null}
              {hasText(aiQuality.readability) ? (
                <div>
                  <dt>Readability</dt>
                  <dd>{aiQuality.readability}</dd>
                </div>
              ) : null}
              {hasText(aiQuality.maintainability) ? (
                <div>
                  <dt>Maintainability</dt>
                  <dd>{aiQuality.maintainability}</dd>
                </div>
              ) : null}
              {hasText(aiQuality.time_complexity) ||
              hasText(aiQuality.space_complexity) ? (
                <div>
                  <dt>Complexity</dt>
                  <dd>
                    {[
                      hasText(aiQuality.time_complexity)
                        ? `Time: ${aiQuality.time_complexity}`
                        : null,
                      hasText(aiQuality.space_complexity)
                        ? `Space: ${aiQuality.space_complexity}`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </dd>
                </div>
              ) : null}
              {hasNumber(aiQuality.score) ? (
                <div>
                  <dt>Quality score</dt>
                  <dd>{aiQuality.score.toFixed(1)}%</dd>
                </div>
              ) : null}
              {Object.keys(aiQuality.score_breakdown ?? {}).length ? (
                <div>
                  <dt>Score breakdown</dt>
                  <dd>
                    {Object.entries(aiQuality.score_breakdown ?? {})
                      .map(
                        ([label, score]) =>
                          `${label.replace(/_/g, " ")}: ${score.toFixed(0)}%`,
                      )
                      .join(" · ")}
                  </dd>
                </div>
              ) : null}
            </dl>
            <div className="scorecard-evidence-columns">
              <EvidenceList title="Strengths" values={aiQuality.strengths} />
              <EvidenceList title="Weaknesses" values={aiQuality.weaknesses} />
              <EvidenceList
                title="Improvements"
                values={aiQuality.improvements}
              />
            </div>
          </section>
        ) : null}

        <section className="scorecard-section">
          <div className="scorecard-section-heading">
            <span>{String(sectionNumber++).padStart(2, "0")}</span>
            <h2>Question-wise performance</h2>
          </div>
          <div className="recruiter-scorecard-questions">
            {candidate.question_breakdown.map((question, index) => {
              const questionScoreParts = [
                showHiddenScore && hasNumber(question.test_case_score)
                  ? `Hidden ${Math.round(question.test_case_score ?? 0)}%`
                  : null,
                showCodingScore && hasNumber(question.coding_score)
                  ? `Metrics ${Math.round(question.coding_score ?? 0)}%`
                  : null,
                showAiScore && hasNumber(question.ai_score)
                  ? `AI quality ${Math.round(question.ai_score ?? 0)}%`
                  : null,
              ].filter(Boolean) as string[];
              const failedCases = question.test_cases.filter(
                (testCase) => !testCase.passed,
              );
              const showQuestionAi =
                showAiScore &&
                question.ai_quality &&
                (hasText(question.ai_quality.approach) ||
                  question.ai_quality.weaknesses.length > 0);
              const showRuntimeCol = question.test_cases.some((testCase) =>
                hasNumber(testCase.execution_time_ms),
              );
              const showMemoryCol = question.test_cases.some((testCase) =>
                hasNumber(testCase.memory_kb),
              );

              return (
                <article
                  key={question.question_id}
                  className="scorecard-question-card"
                >
                  <header>
                    <div>
                      <span>
                        Question {index + 1}
                        {question.difficulty
                          ? ` · ${question.difficulty}`
                          : ""}
                      </span>
                      <strong>{question.question_title}</strong>
                      <small>
                        {question.evaluation_status === "not_attempted"
                          ? "Not attempted · evaluation skipped"
                          : question.total_count > 0
                            ? `${question.passed_count}/${question.total_count} hidden cases passed`
                            : "Evaluated"}
                      </small>
                    </div>
                    <div className="scorecard-question-marks">
                      <strong>
                        {(question.earned_marks ?? 0).toFixed(1)}
                      </strong>
                      <span>
                        /{" "}
                        {(
                          question.assigned_marks ?? question.total_points
                        ).toFixed(1)}{" "}
                        marks
                      </span>
                    </div>
                  </header>

                  {questionScoreParts.length ? (
                    <div
                      className="question-evaluation-score-parts"
                      style={{
                        gridTemplateColumns: `repeat(${questionScoreParts.length}, minmax(0, 1fr))`,
                      }}
                    >
                      {questionScoreParts.map((part) => (
                        <span key={part}>{part}</span>
                      ))}
                    </div>
                  ) : null}

                  {question.tags?.length ? (
                    <div className="scorecard-tags">
                      {question.tags.map((tag) => (
                        <span key={tag}>{tag}</span>
                      ))}
                    </div>
                  ) : null}

                  {hasText(question.problem_statement) ||
                  hasText(question.input_format) ||
                  hasText(question.output_format) ||
                  hasText(question.constraints) ? (
                    <div className="scorecard-question-context">
                      {hasText(question.problem_statement) ? (
                        <>
                          <h4>Problem statement</h4>
                          <p>{question.problem_statement}</p>
                        </>
                      ) : null}
                      {hasText(question.input_format) ||
                      hasText(question.output_format) ? (
                        <div className="scorecard-io-grid">
                          {hasText(question.input_format) ? (
                            <div>
                              <h4>Input format</h4>
                              <p>{question.input_format}</p>
                            </div>
                          ) : null}
                          {hasText(question.output_format) ? (
                            <div>
                              <h4>Output format</h4>
                              <p>{question.output_format}</p>
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                      {hasText(question.constraints) ? (
                        <>
                          <h4>Constraints</h4>
                          <p>{question.constraints}</p>
                        </>
                      ) : null}
                    </div>
                  ) : null}

                  {showQuestionAi && question.ai_quality ? (
                    <div className="scorecard-question-review">
                      <h4>Question code review</h4>
                      {hasText(question.ai_quality.approach) ? (
                        <p>{question.ai_quality.approach}</p>
                      ) : null}
                      {hasText(question.ai_quality.time_complexity) ||
                      hasText(question.ai_quality.space_complexity) ? (
                        <p>
                          <strong>Complexity:</strong>{" "}
                          {[
                            hasText(question.ai_quality.time_complexity)
                              ? `${question.ai_quality.time_complexity} time`
                              : null,
                            hasText(question.ai_quality.space_complexity)
                              ? `${question.ai_quality.space_complexity} space`
                              : null,
                          ]
                            .filter(Boolean)
                            .join(", ")}
                        </p>
                      ) : null}
                      {question.ai_quality.weaknesses.length ? (
                        <p>
                          <strong>Quality concerns:</strong>{" "}
                          {question.ai_quality.weaknesses.join("; ")}
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  {showHiddenScore && question.test_cases.length ? (
                    <div className="scorecard-test-table-wrap">
                      <h4>Test coverage summary</h4>
                      <table className="scorecard-detail-table scorecard-coverage-table">
                        <thead>
                          <tr>
                            <th>Coverage category</th>
                            <th>Cases</th>
                            <th>Passed</th>
                          </tr>
                        </thead>
                        <tbody>
                          {coverageSummary(question.test_cases).map(
                            ([category, totals]) => (
                              <tr key={category}>
                                <td>{category}</td>
                                <td>{totals.total}</td>
                                <td>
                                  {totals.passed}/{totals.total}
                                </td>
                              </tr>
                            ),
                          )}
                        </tbody>
                      </table>
                    </div>
                  ) : null}

                  {showHiddenScore && question.test_cases.length ? (
                    <div className="scorecard-test-table-wrap">
                      <h4>Hidden test-case results</h4>
                      <table className="scorecard-detail-table scorecard-hidden-table">
                        <thead>
                          <tr>
                            <th>Case</th>
                            <th>Result</th>
                            <th>Input</th>
                            <th>Expected</th>
                            <th>Actual</th>
                            {showRuntimeCol ? <th>Runtime</th> : null}
                            {showMemoryCol ? <th>Memory</th> : null}
                            <th>Points</th>
                          </tr>
                        </thead>
                        <tbody>
                          {question.test_cases.map((testCase, caseIndex) => (
                            <tr key={testCase.test_case_id}>
                              <td>
                                {testCase.case_category ||
                                  `Case ${caseIndex + 1}`}
                              </td>
                              <td>
                                <span
                                  className={`scorecard-verdict ${
                                    testCase.passed ? "is-passed" : "is-failed"
                                  }`}
                                >
                                  {testCase.passed ? (
                                    <CheckCircle2
                                      size={14}
                                      aria-hidden="true"
                                    />
                                  ) : (
                                    <XCircle size={14} aria-hidden="true" />
                                  )}
                                  {testCase.verdict.replace(/_/g, " ")}
                                </span>
                              </td>
                              <td>
                                <pre>{testCase.input || "-"}</pre>
                              </td>
                              <td>
                                <pre>{testCase.expected_output || "-"}</pre>
                              </td>
                              <td>
                                <pre>{testCase.actual_output || "-"}</pre>
                              </td>
                              {showRuntimeCol ? (
                                <td>
                                  {hasNumber(testCase.execution_time_ms)
                                    ? `${testCase.execution_time_ms!.toFixed(1)} ms`
                                    : "-"}
                                </td>
                              ) : null}
                              {showMemoryCol ? (
                                <td>
                                  {hasNumber(testCase.memory_kb)
                                    ? `${testCase.memory_kb} KB`
                                    : "-"}
                                </td>
                              ) : null}
                              <td>
                                {testCase.points}
                                {testCase.mandatory ? " · mandatory" : ""}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}

                  {showHiddenScore && failedCases.length ? (
                    <div className="scorecard-failures">
                      <h4>Failure diagnostics</h4>
                      {failedCases.map((testCase) => (
                        <p key={testCase.test_case_id}>
                          <strong>
                            {testCase.verdict.replace(/_/g, " ")}:
                          </strong>{" "}
                          {testCase.message ||
                            "Output did not match the expected result."}
                        </p>
                      ))}
                    </div>
                  ) : null}

                  {question.suggested_solution ||
                  question.suggested_improvement_notes?.length ? (
                    <div className="scorecard-suggestions">
                      <h4>Suggested improvements</h4>
                      {question.suggested_improvement_notes?.map((note) => (
                        <p key={note}>{note}</p>
                      ))}
                      {question.suggested_solution ? (
                        <pre>{question.suggested_solution}</pre>
                      ) : null}
                    </div>
                  ) : null}

                  {hasText(question.submitted_code) ? (
                    <div className="scorecard-source-block">
                      <h4>Submitted source</h4>
                      <pre>{question.submitted_code}</pre>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        </section>

        <footer className="scorecard-doc-footer">
          <p>
            Based on assessment scoring and{" "}
            {proctoringLabel(resolvedSettings.proctoring_mode).toLowerCase()}{" "}
            settings
            {resolvedSettings.slot_title
              ? ` · ${resolvedSettings.slot_title}`
              : ""}{" "}
            · {new Date().toLocaleString()}
          </p>
        </footer>
      </article>
    </div>
  );
}
