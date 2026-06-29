import type { CandidateEvaluationSummary } from "../types/EvaluationResult";

interface EvaluationResultListProps {
  results: CandidateEvaluationSummary[];
  selectedId: string;
  onSelect: (candidateAssessmentId: string) => void;
}

export function EvaluationResultList({
  results,
  selectedId,
  onSelect,
}: EvaluationResultListProps) {
  return (
    <div className="data-table-wrap evaluation-table-wrap">
      <table className="data-table evaluation-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Candidate</th>
            <th>Final</th>
            <th>Tests</th>
            <th>Coding</th>
            <th>AI</th>
            <th>Runtime</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result) => (
            <tr
              key={result.candidate_assessment_id}
              className={
                selectedId === result.candidate_assessment_id ? "is-selected" : ""
              }
              onClick={() => onSelect(result.candidate_assessment_id)}
            >
              <td>
                <strong>#{result.rank || "-"}</strong>
              </td>
              <td>
                <span className="table-primary-cell">
                  <strong>{result.candidate_name}</strong>
                  <span>{result.candidate_email}</span>
                </span>
              </td>
              <td>
                <strong>{Math.round(result.scores.final_score)}%</strong>
              </td>
              <td>{Math.round(result.scores.test_case_score)}%</td>
              <td>{Math.round(result.scores.coding_score)}%</td>
              <td>{Math.round(result.scores.ai_score)}%</td>
              <td>{Math.round(result.total_execution_time_ms)} ms</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
