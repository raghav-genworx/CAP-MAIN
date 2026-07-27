import { Info } from "lucide-react";

import type { CandidateQuestion } from "../../types/CandidatePortal";

const ANSWER_VALIDATION_LABELS = {
  exact: "Exact output match",
  unordered: "Order of results is flexible",
  floating: "Numeric tolerance allowed",
  multiple_valid: "Multiple answers accepted",
  constructive: "Any valid construction accepted",
} as const;

const DIFFICULTY_LABELS = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
} as const;

/** Split a free-text specification into readable lines, tolerating bullets. */
function specLines(value: string, fallback: string) {
  const lines = (value.trim() || fallback)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.replace(/^[-*•]\s*/, ""));
  return lines.length ? lines : [fallback];
}

function SpecSection({
  title,
  value,
  fallback,
  forceList = false,
}: {
  title: string;
  value: string;
  fallback: string;
  forceList?: boolean;
}) {
  const lines = specLines(value, fallback);
  return (
    <section className="cap-problem-section">
      <h2>{title}</h2>
      {forceList || lines.length > 1 ? (
        <ul className="cap-spec-list">
          {lines.map((line, index) => (
            <li key={`${title}-${index}`}>{line}</li>
          ))}
        </ul>
      ) : (
        <p className="cap-prose">{lines[0]}</p>
      )}
    </section>
  );
}

export function CandidateProblemPanel({ question }: { question: CandidateQuestion }) {
  const statementParagraphs = question.problem_statement
    .split(/\r?\n\s*\r?\n/)
    .map((block) => block.trim())
    .filter(Boolean);
  const validationLabel = ANSWER_VALIDATION_LABELS[question.answer_validation_mode];
  const showCheckerNote =
    question.answer_validation_mode !== "exact" ||
    Boolean(question.output_checker_explanation.trim());

  return (
    <section className="cap-problem" aria-label="Problem statement">
      <div className="cap-problem-scroll" tabIndex={0}>
        <div className="cap-problem-head">
          <p className="cap-eyebrow">Question {question.question_order}</p>
          <h1>{question.title}</h1>
          <ul className="cap-tag-row">
            <li className={`cap-tag is-${question.difficulty}`}>
              {DIFFICULTY_LABELS[question.difficulty]}
            </li>
            <li className="cap-tag">
              {question.marks} mark{question.marks === 1 ? "" : "s"}
            </li>
            <li className={`cap-tag ${question.is_mandatory ? "is-required" : ""}`}>
              {question.is_mandatory ? "Required" : "Optional"}
            </li>
          </ul>
        </div>

        <section className="cap-problem-section">
          <h2>Problem</h2>
          {statementParagraphs.length ? (
            statementParagraphs.map((block, index) => (
              <p className="cap-prose" key={`statement-${index}`}>
                {block}
              </p>
            ))
          ) : (
            <p className="cap-prose">
              The problem statement was not provided for this question.
            </p>
          )}
        </section>

        <SpecSection
          title="Input format"
          value={question.input_format}
          fallback="The input format is described in the problem statement."
        />
        <SpecSection
          title="Output format"
          value={question.output_format}
          fallback="Print the required answer only."
        />
        <SpecSection
          title="Constraints"
          value={question.constraints}
          fallback="Use an approach that is efficient for the stated limits."
          forceList
        />

        {showCheckerNote ? (
          <section className="cap-problem-section">
            <h2>How your output is checked</h2>
            <p className="cap-callout">
              <Info size={15} aria-hidden="true" />
              <span>
                <strong>{validationLabel}.</strong>{" "}
                {question.output_checker_explanation.trim()}
              </span>
            </p>
          </section>
        ) : null}

        {question.sample_test_cases.length ? (
          <section className="cap-problem-section">
            <h2>Sample test cases</h2>
            <div className="cap-samples">
              {question.sample_test_cases.map((testCase, index) => (
                <article className="cap-sample" key={`${question.id}-sample-${index}`}>
                  <h3>Sample {index + 1}</h3>
                  <div className="cap-sample-block">
                    <p className="cap-sample-label" id={`${question.id}-in-${index}`}>
                      Input
                    </p>
                    <pre aria-labelledby={`${question.id}-in-${index}`} tabIndex={0}>
                      {testCase.input}
                    </pre>
                  </div>
                  <div className="cap-sample-block">
                    <p className="cap-sample-label" id={`${question.id}-out-${index}`}>
                      Expected output
                    </p>
                    <pre aria-labelledby={`${question.id}-out-${index}`} tabIndex={0}>
                      {testCase.expected_output}
                    </pre>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </section>
  );
}
