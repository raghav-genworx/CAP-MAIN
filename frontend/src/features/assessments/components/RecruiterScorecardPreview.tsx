import { ArrowLeft, CheckCircle2, Download, XCircle } from "lucide-react";

import { Button } from "../../../components/ui/Button";
import type {
  CandidateBenchmarkContext,
  CandidateEvaluationSummary,
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

function durationLabel(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "Not recorded";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return hours
    ? `${hours}h ${minutes}m ${remainder}s`
    : `${minutes}m ${remainder}s`;
}

function dateTimeLabel(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "Not recorded";
}

function recommendation(candidate: CandidateEvaluationSummary) {
  const hiddenRate = candidate.hidden_total
    ? (candidate.hidden_passed / candidate.hidden_total) * 100
    : 0;
  const suspicious = candidate.integrity?.suspicious_activity?.length ?? 0;
  const similarity = candidate.integrity?.plagiarism_similarity_score;
  if (!candidate.hidden_total || suspicious || (similarity ?? 0) >= 70) {
    return {
      label: "Manual Review Required",
      tone: "warning",
      detail: "Integrity signals or incomplete hidden-test evidence need recruiter review before a decision.",
    };
  }
  if (candidate.scores.final_score >= 85 && hiddenRate >= 85 && candidate.scores.ai_score >= 75) {
    return { label: "Strong Hire", tone: "positive", detail: "Strong correctness, execution, and code-quality evidence are aligned." };
  }
  if (candidate.scores.final_score >= 70 && hiddenRate >= 70 && candidate.scores.ai_score >= 60) {
    return { label: "Hire", tone: "positive", detail: "The candidate solved most requirements with acceptable implementation quality." };
  }
  if (candidate.scores.final_score < 40 || hiddenRate < 40) {
    return { label: "Reject", tone: "negative", detail: "Hidden-test correctness is below the expected reliability threshold." };
  }
  return { label: "Further Review", tone: "warning", detail: "The score profile is mixed; review question evidence before deciding." };
}

function EvidenceList({ title, values }: { title: string; values: string[] }) {
  return (
    <div className="scorecard-evidence-list">
      <strong>{title}</strong>
      {values.length ? <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul> : <p>None recorded.</p>}
    </div>
  );
}

function coverageSummary(testCases: CandidateEvaluationSummary["question_breakdown"][number]["test_cases"]) {
  const grouped = new Map<string, { total: number; passed: number }>();
  testCases.forEach((testCase) => {
    const category = testCase.case_category || "Confidential hidden validation case";
    const current = grouped.get(category) ?? { total: 0, passed: 0 };
    current.total += 1;
    current.passed += testCase.passed ? 1 : 0;
    grouped.set(category, current);
  });
  return [...grouped.entries()];
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
    return <div className="recruiter-scorecard-preview">{onBack ? <Button type="button" variant="secondary" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" />Back to results</Button> : null}<strong>Loading scorecard...</strong></div>;
  }
  if (error || !candidate) {
    return <div className="recruiter-scorecard-preview is-error" role="alert">{onBack ? <Button type="button" variant="secondary" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" />Back to results</Button> : null}<strong>{error || "Scorecard unavailable."}</strong></div>;
  }

  const decision = recommendation(candidate);
  const weights = candidate.weights ?? { test_case_weight: 60, coding_weight: 20, ai_weight: 20 };
  const activity = candidate.activity;
  const integrity = candidate.integrity;
  const questionTitles = new Map(candidate.question_breakdown.map((question) => [question.question_id, question.question_title]));
  const questionTimes = Object.entries(activity?.question_time_seconds ?? {});

  if (!fullPage) {
    return (
      <div className="recruiter-scorecard-preview">
        <div className="scorecard-head">
          <div><span>Candidate scorecard</span><h2>{candidate.candidate_name}</h2><p>{candidate.candidate_email}</p></div>
          <Button type="button" variant="secondary" disabled={downloadPending} onClick={onDownload}><Download size={16} aria-hidden="true" />{downloadPending ? "Preparing..." : "Download PDF"}</Button>
        </div>
        <div className="assessment-result-summary">
          <div><span>Rank</span><strong>#{candidate.rank || "-"}</strong></div>
          <div><span>Final</span><strong>{candidate.scores.final_score.toFixed(1)}%</strong></div>
          <div><span>Hidden cases</span><strong>{candidate.hidden_passed}/{candidate.hidden_total}</strong></div>
        </div>
        <div className="recruiter-scorecard-questions">
          {candidate.question_breakdown.map((question) => <article key={question.question_id}><header><div><strong>{question.question_title}</strong><span>{question.passed_count}/{question.total_count} cases passed</span></div><strong>{(question.earned_marks ?? 0).toFixed(1)}/{(question.assigned_marks ?? question.total_points).toFixed(1)}</strong></header></article>)}
        </div>
      </div>
    );
  }

  return (
    <div className={`recruiter-scorecard-preview ${fullPage ? "is-full-page" : ""}`}>
      <div className="scorecard-page-actions">
        {onBack ? <Button type="button" variant="secondary" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" />Back to results</Button> : <span />}
        <Button type="button" variant="secondary" disabled={downloadPending} onClick={onDownload}>
          <Download size={16} aria-hidden="true" />{downloadPending ? "Preparing..." : "Download PDF"}
        </Button>
      </div>

      <div className="scorecard-head">
        <div><span>Candidate technical scorecard</span><h2>{candidate.candidate_name}</h2><p>{candidate.candidate_email}</p></div>
        <strong>{candidate.scores.final_score.toFixed(1)}%</strong>
      </div>

      <section className={`scorecard-recommendation is-${decision.tone}`}>
        <div><span>Recruiter recommendation</span><strong>{decision.label}</strong></div>
        <p>{decision.detail}</p>
      </section>

      <section className="scorecard-section">
        <div className="scorecard-section-heading"><span>01</span><h3>Score composition</h3></div>
        <div className="assessment-result-summary scorecard-metrics">
          <div><span>Final score</span><strong>{candidate.scores.final_score.toFixed(1)}%</strong></div>
          <div><span>Hidden tests</span><strong>{candidate.scores.test_case_score.toFixed(1)}%</strong></div>
          <div><span>Coding metrics</span><strong>{candidate.scores.coding_score.toFixed(1)}%</strong></div>
          <div><span>AI quality</span><strong>{candidate.scores.ai_score.toFixed(1)}%</strong></div>
        </div>
        <div className="scorecard-table-shell"><table className="scorecard-detail-table"><thead><tr><th>Component</th><th>Weight</th><th>Raw score</th><th>Weighted score</th></tr></thead><tbody>
          {[
            ["Hidden test correctness", weights.test_case_weight, candidate.scores.test_case_score],
            ["Coding/runtime metrics", weights.coding_weight, candidate.scores.coding_score],
            ["AI code quality", weights.ai_weight, candidate.scores.ai_score],
          ].map(([label, weight, score]) => <tr key={String(label)}><td>{label}</td><td>{Number(weight).toFixed(0)}%</td><td>{Number(score).toFixed(1)}%</td><td>{(Number(weight) * Number(score) / 100).toFixed(1)}</td></tr>)}
        </tbody></table></div>
      </section>

      <section className="scorecard-section">
        <div className="scorecard-section-heading"><span>02</span><h3>Assessment summary</h3></div>
        <dl className="scorecard-facts">
          <div><dt>Assessment rank</dt><dd>{candidate.rank ? `#${candidate.rank}` : "Not ranked"}</dd></div>
          <div><dt>Language</dt><dd>{candidate.language || "Not recorded"}</dd></div>
          <div><dt>Hidden cases</dt><dd>{candidate.hidden_passed}/{candidate.hidden_total}</dd></div>
          <div><dt>Runtime total</dt><dd>{candidate.total_execution_time_ms.toFixed(0)} ms</dd></div>
          <div><dt>Peak memory</dt><dd>{candidate.peak_memory_kb >= 1024 ? `${(candidate.peak_memory_kb / 1024).toFixed(1)} MB` : `${candidate.peak_memory_kb} KB`}</dd></div>
          <div><dt>Time taken</dt><dd>{durationLabel(activity?.total_time_seconds ?? candidate.time_taken_seconds)}</dd></div>
          <div><dt>Started</dt><dd>{dateTimeLabel(activity?.started_at)}</dd></div>
          <div><dt>Submitted</dt><dd>{dateTimeLabel(activity?.submitted_at ?? candidate.submitted_at)}</dd></div>
        </dl>
        <div className="scorecard-subsection"><h4>Time by question</h4>{questionTimes.length ? <dl className="scorecard-question-times">{questionTimes.map(([id, seconds]) => <div key={id}><dt>{questionTitles.get(id) || id}</dt><dd>{durationLabel(seconds)}</dd></div>)}</dl> : <p>Question-level timing was not recorded.</p>}</div>
        <div className="scorecard-subsection"><h4>Integrity signals</h4><dl className="scorecard-facts">
          <div><dt>Proctoring</dt><dd>{integrity?.proctoring_mode || "Not configured"}</dd></div>
          <div><dt>Tab switches</dt><dd>{integrity?.tab_switches ?? "Not recorded"}</dd></div>
          <div><dt>Copy / paste</dt><dd>{integrity?.copy_paste_count ?? "Not recorded"}</dd></div>
          <div><dt>Fullscreen exits</dt><dd>{integrity?.fullscreen_exits ?? "Not recorded"}</dd></div>
          <div><dt>Similarity</dt><dd>{integrity?.plagiarism_similarity_score == null ? "Not available" : `${integrity.plagiarism_similarity_score.toFixed(1)}%`}</dd></div>
        </dl><EvidenceList title="Integrity notes" values={integrity?.suspicious_activity ?? []} /></div>
        <div className="scorecard-subsection"><h4>Benchmark</h4><dl className="scorecard-facts">
          <div><dt>Candidate rank</dt><dd>{benchmark?.candidate_rank ? `#${benchmark.candidate_rank}/${benchmark.total_candidates}` : "Not ranked"}</dd></div>
          <div><dt>Average score</dt><dd>{benchmark?.average_score == null ? "Not available" : `${benchmark.average_score.toFixed(1)}%`}</dd></div>
          <div><dt>Average time</dt><dd>{durationLabel(benchmark?.average_completion_time_seconds)}</dd></div>
          <div><dt>Percentile</dt><dd>{benchmark?.percentile == null ? "Not available" : benchmark.percentile.toFixed(1)}</dd></div>
        </dl></div>
      </section>

      <section className="scorecard-section">
        <div className="scorecard-section-heading"><span>03</span><h3>Code quality review</h3></div>
        <dl className="scorecard-review-grid">
          <div><dt>Approach</dt><dd>{candidate.ai_quality.approach}</dd></div>
          <div><dt>Readability</dt><dd>{candidate.ai_quality.readability}</dd></div>
          <div><dt>Maintainability</dt><dd>{candidate.ai_quality.maintainability}</dd></div>
          <div><dt>Complexity</dt><dd>Time: {candidate.ai_quality.time_complexity} · Space: {candidate.ai_quality.space_complexity}</dd></div>
          <div><dt>Quality score</dt><dd>{candidate.ai_quality.score.toFixed(1)}%</dd></div>
          <div><dt>Score breakdown</dt><dd>{Object.entries(candidate.ai_quality.score_breakdown ?? {}).map(([label, score]) => `${label.replace(/_/g, " ")}: ${score.toFixed(0)}%`).join(" · ") || "Not available"}</dd></div>
        </dl>
        <div className="scorecard-evidence-columns"><EvidenceList title="Strengths" values={candidate.ai_quality.strengths} /><EvidenceList title="Weaknesses" values={candidate.ai_quality.weaknesses} /><EvidenceList title="Improvements" values={candidate.ai_quality.improvements} /></div>
      </section>

      <section className="scorecard-section">
        <div className="scorecard-section-heading"><span>04</span><h3>Question-wise performance</h3></div>
        <div className="recruiter-scorecard-questions">
          {candidate.question_breakdown.map((question, index) => (
            <article key={question.question_id}>
              <header><div><span>Question {index + 1} · {question.difficulty || "Difficulty not set"}</span><strong>{question.question_title}</strong><small>{question.evaluation_status === "not_attempted" ? "Not attempted · evaluation skipped" : `${question.passed_count}/${question.total_count} hidden cases passed`}</small></div><strong>{(question.earned_marks ?? 0).toFixed(1)}/{(question.assigned_marks ?? question.total_points).toFixed(1)}</strong></header>
              <div className="question-evaluation-score-parts"><span>Hidden {Math.round(question.test_case_score ?? 0)}%</span><span>Metrics {Math.round(question.coding_score ?? 0)}%</span><span>AI quality {Math.round(question.ai_score ?? 0)}%</span></div>
              {question.tags?.length ? <div className="scorecard-tags">{question.tags.map((tag) => <span key={tag}>{tag}</span>)}</div> : null}
              <div className="scorecard-question-context"><h4>Problem statement</h4><p>{question.problem_statement || "Not available"}</p><h4>Input format</h4><p>{question.input_format || "Not available"}</p><h4>Output format</h4><p>{question.output_format || "Not available"}</p><h4>Constraints</h4><p>{question.constraints || "Not available"}</p></div>
              {question.ai_quality ? <div className="scorecard-question-review"><h4>Question code review</h4><p>{question.ai_quality.approach}</p><p><strong>Complexity:</strong> {question.ai_quality.time_complexity} time, {question.ai_quality.space_complexity} space</p><p><strong>Quality concerns:</strong> {question.ai_quality.weaknesses.join("; ") || "None recorded."}</p><p>AI quality includes readability, maintainability, complexity, and input/error handling, so it can differ from hidden-test correctness.</p></div> : null}
              {question.test_cases.length ? <div className="scorecard-test-table-wrap"><h4>Test coverage summary</h4><table className="scorecard-detail-table"><thead><tr><th>Coverage category</th><th>Cases</th><th>Passed</th></tr></thead><tbody>{coverageSummary(question.test_cases).map(([category, totals]) => <tr key={category}><td>{category}</td><td>{totals.total}</td><td>{totals.passed}/{totals.total}</td></tr>)}</tbody></table></div> : null}
              <div className="scorecard-test-table-wrap"><h4>Hidden test-case results</h4><table className="scorecard-detail-table"><thead><tr><th>Case</th><th>Result</th><th>Input</th><th>Expected</th><th>Actual</th><th>Runtime</th><th>Memory</th><th>Points</th></tr></thead><tbody>{question.test_cases.map((testCase, caseIndex) => <tr key={testCase.test_case_id}><td>{testCase.case_category || `Case ${caseIndex + 1}`}</td><td><span className={`scorecard-verdict ${testCase.passed ? "is-passed" : "is-failed"}`}>{testCase.passed ? <CheckCircle2 size={14} aria-hidden="true" /> : <XCircle size={14} aria-hidden="true" />}{testCase.verdict.replace(/_/g, " ")}</span></td><td><pre>{testCase.input || "-"}</pre></td><td><pre>{testCase.expected_output || "-"}</pre></td><td><pre>{testCase.actual_output || "-"}</pre></td><td>{testCase.execution_time_ms == null ? "-" : `${testCase.execution_time_ms.toFixed(1)} ms`}</td><td>{testCase.memory_kb == null ? "-" : `${testCase.memory_kb} KB`}</td><td>{testCase.points}{testCase.mandatory ? " · mandatory" : ""}</td></tr>)}</tbody></table></div>
              {question.test_cases.some((testCase) => !testCase.passed) ? <div className="scorecard-failures"><h4>Failure diagnostics</h4>{question.test_cases.filter((testCase) => !testCase.passed).map((testCase) => <p key={testCase.test_case_id}><strong>{testCase.verdict.replace(/_/g, " ")}:</strong> {testCase.message || "Output did not match the expected result."}</p>)}</div> : null}
              {(question.suggested_solution || question.suggested_improvement_notes?.length) ? <div className="scorecard-suggestions"><h4>Suggested improvements</h4>{question.suggested_improvement_notes?.map((note) => <p key={note}>{note}</p>)}{question.suggested_solution ? <pre>{question.suggested_solution}</pre> : null}</div> : null}
              <div><h4>Submitted source</h4><pre>{question.submitted_code || "No submitted code available."}</pre></div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
