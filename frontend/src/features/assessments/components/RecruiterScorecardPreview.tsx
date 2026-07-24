import { ArrowLeft, CheckCircle2, Download, XCircle } from "lucide-react";

import { Button } from "../../../components/ui/Button";
import type {
  AICodeQualitySignal,
  CandidateBenchmarkContext,
  CandidateEvaluationSummary,
  QuestionEvaluationBreakdown,
  QuestionTestCaseResult,
} from "../../codeEvaluation/types/EvaluationResult";

interface RecruiterScorecardPreviewProps {
  candidate: CandidateEvaluationSummary | null;
  benchmark?: CandidateBenchmarkContext | null;
  loading: boolean;
  error: string;
  downloadPending: boolean;
  onDownload: () => void;
  onBack?: () => void;
  fullPage?: boolean;
}

function hasText(value: string | null | undefined) {
  return Boolean(value && value.trim() && value.trim() !== "Not available");
}

function displayText(value: string | null | undefined, fallback = "Not recorded") {
  return hasText(value) ? value!.trim() : fallback;
}

function durationLabel(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "Not recorded";
  }
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  return hours
    ? `${hours}h ${minutes}m ${remainder}s`
    : `${minutes}m ${remainder}s`;
}

function dateTimeLabel(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "Not recorded";
}

function memoryLabel(kb: number | null | undefined) {
  if (kb === null || kb === undefined || !Number.isFinite(kb)) {
    return "Not recorded";
  }
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb} KB`;
}

function percentLabel(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "Not available"
    : `${value.toFixed(1)}%`;
}

function passRate(passed: number, total: number) {
  return total ? (passed / total) * 100 : 0;
}

const STYLE_ONLY_REVIEW_PATTERNS = [
  /\bcomments?\b/i,
  /\bdocstrings?\b/i,
  /\bvariable\s+nam(?:e|ing)s?\b/i,
  /\bnaming\b/i,
  /\brename\b/i,
  /\bcamelcase\b/i,
  /\bsnake[_\s-]?case\b/i,
  /\bhelper\s+functions?\b/i,
  /\bsplit\s+into\s+functions?\b/i,
  /\bextract\s+(?:a\s+)?functions?\b/i,
  /\bwrap\s+.*\bfunctions?\b/i,
  /\bclasses?\b/i,
  /\bclass-based\b/i,
  /\bobject[-\s]?oriented\b/i,
  /\bmodulari[sz]e\b/i,
  /\bformatting\b/i,
  /\bindentation\b/i,
  /\bcode\s+style\b/i,
];

const HIDDEN_BREAKDOWN_KEYS = new Set([
  "readability",
  "maintainability",
  "naming",
  "comments",
  "style",
  "formatting",
]);

function isStyleOnlyReview(value: string) {
  return STYLE_ONLY_REVIEW_PATTERNS.some((pattern) => pattern.test(value));
}

function filterReviewItems(values: string[] | undefined) {
  return (values ?? []).filter((value) => value.trim() && !isStyleOnlyReview(value));
}

function scoreBreakdownText(quality: AICodeQualitySignal) {
  return (
    Object.entries(quality.score_breakdown ?? {})
      .filter(([label]) => !HIDDEN_BREAKDOWN_KEYS.has(label.toLowerCase()))
      .map(
        ([label, score]) =>
          `${label.replace(/_/g, " ")}: ${score.toFixed(0)}%`,
      )
      .join(", ") || "Not available"
  );
}

function recommendation(candidate: CandidateEvaluationSummary) {
  const hiddenRate = passRate(candidate.hidden_passed, candidate.hidden_total);
  const suspicious = candidate.integrity?.suspicious_activity?.length ?? 0;
  const similarity = candidate.integrity?.plagiarism_similarity_score;
  if (!candidate.hidden_total || suspicious || (similarity ?? 0) >= 70) {
    return {
      label: "Manual Review Required",
      tone: "warning",
      detail:
        "Integrity signals or incomplete hidden-test evidence need recruiter review before a decision.",
    };
  }
  if (
    candidate.scores.final_score >= 85 &&
    hiddenRate >= 85 &&
    candidate.scores.ai_score >= 75
  ) {
    return {
      label: "Strong Hire",
      tone: "positive",
      detail:
        "Correctness, execution, and code-quality evidence are strongly aligned.",
    };
  }
  if (
    candidate.scores.final_score >= 70 &&
    hiddenRate >= 70 &&
    candidate.scores.ai_score >= 60
  ) {
    return {
      label: "Hire",
      tone: "positive",
      detail:
        "The candidate solved most requirements with acceptable implementation quality.",
    };
  }
  if (candidate.scores.final_score < 40 || hiddenRate < 40) {
    return {
      label: "Reject",
      tone: "negative",
      detail: "Hidden-test correctness is below the expected reliability threshold.",
    };
  }
  return {
    label: "Further Review",
    tone: "warning",
    detail: "The score profile is mixed; review question evidence before deciding.",
  };
}

function coverageSummary(
  testCases: CandidateEvaluationSummary["question_breakdown"][number]["test_cases"],
) {
  const grouped = new Map<string, { total: number; passed: number }>();
  testCases.forEach((testCase) => {
    const category =
      testCase.case_category || "Confidential hidden validation case";
    const current = grouped.get(category) ?? { total: 0, passed: 0 };
    current.total += 1;
    current.passed += testCase.passed ? 1 : 0;
    grouped.set(category, current);
  });
  return [...grouped.entries()];
}

function verdictText(testCase: QuestionTestCaseResult) {
  return testCase.verdict.replace(/_/g, " ");
}

function qualityFallback(
  question: QuestionEvaluationBreakdown,
  candidate: CandidateEvaluationSummary,
) {
  return question.ai_quality ?? candidate.ai_quality;
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function EvidenceList({ title, values }: { title: string; values: string[] }) {
  return (
    <div className="scorecard-evidence-list">
      <strong>{title}</strong>
      {values.length ? (
        <ul>
          {values.map((value) => (
            <li key={value}>{value}</li>
          ))}
        </ul>
      ) : (
        <p>None recorded.</p>
      )}
    </div>
  );
}

function ScoreLane({
  label,
  value,
  weight,
}: {
  label: string;
  value: number;
  weight: number;
}) {
  const width = `${Math.max(0, Math.min(100, value))}%`;
  return (
    <div className="scorecard-score-lane">
      <div>
        <span>{label}</span>
        <strong>{percentLabel(value)}</strong>
      </div>
      <div className="scorecard-score-track" aria-hidden="true">
        <span style={{ width }} />
      </div>
      <em>{weight.toFixed(0)}% weight</em>
    </div>
  );
}

function ApproachPanel({
  quality,
  compact = false,
}: {
  quality: AICodeQualitySignal;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "scorecard-approach-panel is-compact" : "scorecard-approach-panel"}>
      <span>Candidate approach</span>
      <p>{displayText(quality.approach, "Approach was not recorded.")}</p>
      <dl>
        <div>
          <dt>Time</dt>
          <dd>{displayText(quality.time_complexity, "Not recorded")}</dd>
        </div>
        <div>
          <dt>Space</dt>
          <dd>{displayText(quality.space_complexity, "Not recorded")}</dd>
        </div>
      </dl>
    </div>
  );
}

function HiddenCaseTable({
  testCases,
}: {
  testCases: QuestionEvaluationBreakdown["test_cases"];
}) {
  if (!testCases.length) {
    return (
      <div className="scorecard-empty-panel">
        Hidden test-case details are not available for this question.
      </div>
    );
  }

  return (
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
            <th>Runtime</th>
            <th>Memory</th>
            <th>Points</th>
          </tr>
        </thead>
        <tbody>
          {testCases.map((testCase, caseIndex) => (
            <tr key={testCase.test_case_id}>
              <td>{testCase.case_category || `Case ${caseIndex + 1}`}</td>
              <td>
                <span
                  className={`scorecard-verdict ${
                    testCase.passed ? "is-passed" : "is-failed"
                  }`}
                >
                  {testCase.passed ? (
                    <CheckCircle2 size={14} aria-hidden="true" />
                  ) : (
                    <XCircle size={14} aria-hidden="true" />
                  )}
                  {verdictText(testCase)}
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
              <td>
                {testCase.execution_time_ms == null
                  ? "-"
                  : `${testCase.execution_time_ms.toFixed(1)} ms`}
              </td>
              <td>{memoryLabel(testCase.memory_kb)}</td>
              <td>
                {testCase.points}
                {testCase.mandatory ? " mandatory" : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RecruiterScorecardPreview({
  candidate,
  benchmark = null,
  loading,
  error,
  downloadPending,
  onDownload,
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

  const decision = recommendation(candidate);
  const weights = candidate.weights ?? {
    test_case_weight: 60,
    coding_weight: 20,
    ai_weight: 20,
  };
  const activity = candidate.activity;
  const integrity = candidate.integrity;
  const hiddenRate = passRate(candidate.hidden_passed, candidate.hidden_total);
  const questionTitles = new Map(
    candidate.question_breakdown.map((question) => [
      question.question_id,
      question.question_title,
    ]),
  );
  const questionTimes = Object.entries(activity?.question_time_seconds ?? {});
  const scoreLanes = [
    {
      label: "Hidden test correctness",
      value: candidate.scores.test_case_score,
      weight: weights.test_case_weight,
    },
    {
      label: "Coding and runtime metrics",
      value: candidate.scores.coding_score,
      weight: weights.coding_weight,
    },
    {
      label: "AI solution review",
      value: candidate.scores.ai_score,
      weight: weights.ai_weight,
    },
  ];

  if (!fullPage) {
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
            <strong>{candidate.scores.final_score.toFixed(1)}%</strong>
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
                    {question.passed_count}/{question.total_count} cases passed
                  </span>
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

  return (
    <div className="recruiter-scorecard-preview is-full-page">
      <div className="scorecard-page-actions">
        {onBack ? (
          <Button type="button" variant="secondary" onClick={onBack}>
            <ArrowLeft size={16} aria-hidden="true" />
            Back to results
          </Button>
        ) : (
          <span />
        )}
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

      <section className="scorecard-hero">
        <div>
          <span>Candidate technical scorecard</span>
          <h2>{candidate.candidate_name}</h2>
          <p>{candidate.candidate_email}</p>
        </div>
        <div className="scorecard-final-score">
          <span>Final score</span>
          <strong>{candidate.scores.final_score.toFixed(1)}%</strong>
          <em>{candidate.rank ? `Rank #${candidate.rank}` : "Rank not set"}</em>
        </div>
      </section>

      <section className={`scorecard-recommendation is-${decision.tone}`}>
        <div>
          <span>Recruiter recommendation</span>
          <strong>{decision.label}</strong>
        </div>
        <p>{decision.detail}</p>
      </section>

      <section className="scorecard-section">
        <div className="scorecard-section-heading">
          <span>01</span>
          <h3>Decision summary</h3>
        </div>
        <div className="scorecard-decision-grid">
          <div className="scorecard-decision-card is-primary">
            <span>Final score</span>
            <strong>{candidate.scores.final_score.toFixed(1)}%</strong>
            <p>Combined score from configured assessment weights.</p>
          </div>
          <div className="scorecard-decision-card">
            <span>Hidden tests</span>
            <strong>
              {candidate.hidden_passed}/{candidate.hidden_total}
            </strong>
            <p>{percentLabel(hiddenRate)} hidden pass rate.</p>
          </div>
          <div className="scorecard-decision-card">
            <span>AI solution review</span>
            <strong>{candidate.scores.ai_score.toFixed(1)}%</strong>
            <p>Algorithm, complexity, input handling, and correctness risk.</p>
          </div>
          <div className="scorecard-decision-card">
            <span>Time taken</span>
            <strong>
              {durationLabel(
                activity?.total_time_seconds ?? candidate.time_taken_seconds,
              )}
            </strong>
            <p>
              Submitted {dateTimeLabel(activity?.submitted_at ?? candidate.submitted_at)}
            </p>
          </div>
        </div>
      </section>

      <section className="scorecard-section">
        <div className="scorecard-section-heading">
          <span>02</span>
          <h3>Score composition</h3>
        </div>
        <div className="scorecard-score-lanes">
          {scoreLanes.map((lane) => (
            <ScoreLane key={lane.label} {...lane} />
          ))}
        </div>
        <div className="scorecard-table-shell">
          <table className="scorecard-detail-table scorecard-breakdown-table">
            <thead>
              <tr>
                <th>Component</th>
                <th>Weight</th>
                <th>Raw score</th>
                <th>Weighted score</th>
              </tr>
            </thead>
            <tbody>
              {scoreLanes.map((lane) => (
                <tr key={lane.label}>
                  <td>{lane.label}</td>
                  <td>{lane.weight.toFixed(0)}%</td>
                  <td>{lane.value.toFixed(1)}%</td>
                  <td>{((lane.weight * lane.value) / 100).toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="scorecard-section">
        <div className="scorecard-section-heading">
          <span>03</span>
          <h3>Session context</h3>
        </div>
        <dl className="scorecard-facts">
          <Fact
            label="Assessment rank"
            value={candidate.rank ? `#${candidate.rank}` : "Not ranked"}
          />
          <Fact label="Language" value={displayText(candidate.language)} />
          <Fact
            label="Runtime total"
            value={`${candidate.total_execution_time_ms.toFixed(0)} ms`}
          />
          <Fact label="Peak memory" value={memoryLabel(candidate.peak_memory_kb)} />
          <Fact label="Started" value={dateTimeLabel(activity?.started_at)} />
          <Fact
            label="Submitted"
            value={dateTimeLabel(activity?.submitted_at ?? candidate.submitted_at)}
          />
          <Fact
            label="Average score"
            value={
              benchmark?.average_score == null
                ? "Not available"
                : percentLabel(benchmark.average_score)
            }
          />
          <Fact
            label="Percentile"
            value={
              benchmark?.percentile == null
                ? "Not available"
                : benchmark.percentile.toFixed(1)
            }
          />
        </dl>
        <div className="scorecard-context-grid">
          <div className="scorecard-subsection">
            <h4>Time by question</h4>
            {questionTimes.length ? (
              <dl className="scorecard-question-times">
                {questionTimes.map(([id, seconds]) => (
                  <div key={id}>
                    <dt>{questionTitles.get(id) || id}</dt>
                    <dd>{durationLabel(seconds)}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p>Question-level timing was not recorded.</p>
            )}
          </div>
          <div className="scorecard-subsection">
            <h4>Integrity signals</h4>
            <dl className="scorecard-facts scorecard-facts-compact">
              <Fact
                label="Proctoring"
                value={displayText(integrity?.proctoring_mode, "Not configured")}
              />
              <Fact
                label="Tab switches"
                value={
                  integrity?.tab_switches == null
                    ? "Not recorded"
                    : String(integrity.tab_switches)
                }
              />
              <Fact
                label="Copy / paste"
                value={
                  integrity?.copy_paste_count == null
                    ? "Not recorded"
                    : String(integrity.copy_paste_count)
                }
              />
              <Fact
                label="Similarity"
                value={
                  integrity?.plagiarism_similarity_score == null
                    ? "Not available"
                    : percentLabel(integrity.plagiarism_similarity_score)
                }
              />
            </dl>
            <EvidenceList
              title="Integrity notes"
              values={integrity?.suspicious_activity ?? []}
            />
          </div>
        </div>
      </section>

      <section className="scorecard-section">
        <div className="scorecard-section-heading">
          <span>04</span>
          <h3>AI solution review</h3>
        </div>
        <div className="scorecard-review-summary">
          <ApproachPanel quality={candidate.ai_quality} />
          <dl className="scorecard-review-grid">
            <div>
              <dt>Quality score</dt>
              <dd>{candidate.ai_quality.score.toFixed(1)}%</dd>
            </div>
            <div>
              <dt>Score breakdown</dt>
              <dd>{scoreBreakdownText(candidate.ai_quality)}</dd>
            </div>
          </dl>
        </div>
        <div className="scorecard-evidence-columns">
          <EvidenceList
            title="Strengths"
            values={filterReviewItems(candidate.ai_quality.strengths)}
          />
          <EvidenceList
            title="Weaknesses"
            values={filterReviewItems(candidate.ai_quality.weaknesses)}
          />
          <EvidenceList
            title="Improvements"
            values={filterReviewItems(candidate.ai_quality.improvements)}
          />
        </div>
      </section>

      <section className="scorecard-section">
        <div className="scorecard-section-heading">
          <span>05</span>
          <h3>Question-wise performance</h3>
        </div>
        <div className="recruiter-scorecard-questions">
          {candidate.question_breakdown.map((question, index) => {
            const quality = qualityFallback(question, candidate);
            const filteredWeaknesses = filterReviewItems(quality.weaknesses);
            const suggestedNotes = filterReviewItems(
              question.suggested_improvement_notes,
            );
            const showSuggestions = Boolean(
              question.suggested_solution || suggestedNotes.length,
            );
            const failedCases = question.test_cases.filter(
              (testCase) => !testCase.passed,
            );
            return (
              <article key={question.question_id} className="scorecard-question-card">
                <header>
                  <div>
                    <span>
                      Question {index + 1}
                      {question.difficulty ? ` - ${question.difficulty}` : ""}
                    </span>
                    <strong>{question.question_title}</strong>
                    <small>
                      {question.evaluation_status === "not_attempted"
                        ? "Not attempted - evaluation skipped"
                        : `${question.passed_count}/${question.total_count} hidden cases passed`}
                    </small>
                  </div>
                  <strong>
                    {(question.earned_marks ?? 0).toFixed(1)}/
                    {(question.assigned_marks ?? question.total_points).toFixed(1)}
                  </strong>
                </header>

                <div className="question-evaluation-score-parts">
                  <span>Hidden {Math.round(question.test_case_score ?? 0)}%</span>
                  <span>Metrics {Math.round(question.coding_score ?? 0)}%</span>
                  <span>AI review {Math.round(question.ai_score ?? 0)}%</span>
                </div>

                {question.tags?.length ? (
                  <div className="scorecard-tags">
                    {question.tags.map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </div>
                ) : null}

                <div className="scorecard-question-layout">
                  <div className="scorecard-question-context">
                    <h4>Problem brief</h4>
                    <p>{displayText(question.problem_statement, "Not available")}</p>
                    <div className="scorecard-io-grid">
                      <div>
                        <h4>Input</h4>
                        <p>{displayText(question.input_format, "Not available")}</p>
                      </div>
                      <div>
                        <h4>Output</h4>
                        <p>{displayText(question.output_format, "Not available")}</p>
                      </div>
                    </div>
                    <h4>Constraints</h4>
                    <p>{displayText(question.constraints, "Not available")}</p>
                  </div>

                  <div className="scorecard-question-review">
                    <h4>Reviewer notes</h4>
                    <ApproachPanel quality={quality} compact />
                    <p>
                      <strong>Quality concerns:</strong>{" "}
                      {filteredWeaknesses.length
                        ? filteredWeaknesses.join("; ")
                        : "None recorded."}
                    </p>
                  </div>
                </div>

                {question.test_cases.length ? (
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

                <HiddenCaseTable testCases={question.test_cases} />

                {failedCases.length ? (
                  <div className="scorecard-failures">
                    <h4>Failure diagnostics</h4>
                    {failedCases.map((testCase) => (
                      <p key={testCase.test_case_id}>
                        <strong>{verdictText(testCase)}:</strong>{" "}
                        {testCase.message ||
                          "Output did not match the expected result."}
                      </p>
                    ))}
                  </div>
                ) : null}

                <div className="scorecard-source-review">
                  <ApproachPanel quality={quality} compact />
                  <div className="scorecard-source-block">
                    <h4>Submitted source</h4>
                    <pre>{question.submitted_code || "No submitted code available."}</pre>
                  </div>
                </div>

                {showSuggestions ? (
                  <div className="scorecard-suggestions">
                    <h4>Suggested improvements</h4>
                    {suggestedNotes.map((note) => (
                      <p key={note}>{note}</p>
                    ))}
                    {question.suggested_solution ? (
                      <pre>{question.suggested_solution}</pre>
                    ) : null}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
