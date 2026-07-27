import {
  CheckCircle2,
  ChevronDown,
  LoaderCircle,
  Play,
  TriangleAlert,
  XCircle,
} from "lucide-react";

import type { RunResultCase, RunResultState } from "./types";

function outputOrPlaceholder(value: string | undefined) {
  return value && value.length ? value : "(empty)";
}

function caseHeadline(testCase: RunResultCase) {
  if (testCase.passed) {
    return "Passed";
  }
  return testCase.errorType || testCase.status || "Did not pass";
}

function CaseCard({
  testCase,
  showOutputs,
}: {
  testCase: RunResultCase;
  showOutputs: boolean;
}) {
  const memory =
    typeof testCase.memoryKb === "number" && testCase.memoryKb > 0
      ? `${Math.round(testCase.memoryKb)} KB`
      : "";

  return (
    <article className={`cap-case ${testCase.passed ? "is-passed" : "is-failed"}`}>
      <div className="cap-case-head">
        {testCase.passed ? (
          <CheckCircle2 size={16} aria-hidden="true" />
        ) : (
          <XCircle size={16} aria-hidden="true" />
        )}
        <p className="cap-case-title">
          Test case {testCase.index}
          <span className="cap-case-verdict">{caseHeadline(testCase)}</span>
        </p>
        <p className="cap-case-metrics">
          {testCase.executionTime ? <span>{testCase.executionTime}s</span> : null}
          {memory ? <span>{memory}</span> : null}
        </p>
      </div>

      {testCase.checkerMessage ? (
        <p className="cap-case-message">{testCase.checkerMessage}</p>
      ) : null}

      {showOutputs ? (
        <>
          {testCase.input !== undefined ? (
            <div className="cap-case-block">
              <p className="cap-case-label">Input</p>
              <pre tabIndex={0}>{outputOrPlaceholder(testCase.input)}</pre>
            </div>
          ) : null}
          <div className="cap-case-grid">
            <div className="cap-case-block">
              <p className="cap-case-label">Expected output</p>
              <pre tabIndex={0}>{outputOrPlaceholder(testCase.expectedOutput)}</pre>
            </div>
            <div className="cap-case-block">
              <p className="cap-case-label">Your output</p>
              <pre tabIndex={0}>{outputOrPlaceholder(testCase.actualOutput)}</pre>
            </div>
          </div>
          {testCase.compileOutput ? (
            <div className="cap-case-block">
              <p className="cap-case-label">Compiler output</p>
              <pre tabIndex={0}>{testCase.compileOutput}</pre>
            </div>
          ) : null}
          {testCase.stderr ? (
            <div className="cap-case-block">
              <p className="cap-case-label">Error output</p>
              <pre tabIndex={0}>{testCase.stderr}</pre>
            </div>
          ) : null}
        </>
      ) : null}
    </article>
  );
}

interface CandidateResultsPanelProps {
  expanded: boolean;
  onToggle: () => void;
  result: RunResultState | null;
  isRunning: boolean;
  runLabel: string;
  errors: string[];
}

export function CandidateResultsPanel({
  expanded,
  onToggle,
  result,
  isRunning,
  runLabel,
  errors,
}: CandidateResultsPanelProps) {
  const isHidden = result?.kind === "hidden";
  const kindLabel = isHidden ? "Hidden tests" : "Sample tests";
  const tone = isRunning
    ? "is-running"
    : result?.cases.length
      ? result.cases.every((testCase) => testCase.passed)
        ? "is-passed"
        : "is-failed"
      : "is-idle";

  return (
    <section className={`cap-results ${expanded ? "is-expanded" : ""} ${tone}`}>
      <h2 className="sr-only">Test results</h2>
      <button
        type="button"
        className="cap-results-toggle"
        aria-expanded={expanded}
        aria-controls="cap-results-body"
        onClick={onToggle}
      >
        <span className="cap-results-toggle-label">
          <span className="cap-results-dot" aria-hidden="true" />
          Results
          {result ? <span className="cap-results-kind">{kindLabel}</span> : null}
        </span>
        <span className="cap-results-summary">
          {isRunning ? runLabel : result ? result.summary : "Not run yet"}
        </span>
        <ChevronDown size={16} aria-hidden="true" className="cap-results-chevron" />
      </button>

      <div id="cap-results-body" className="cap-results-body" hidden={!expanded}>
        {errors.length ? (
          <div className="cap-alert is-danger" role="alert">
            <TriangleAlert size={16} aria-hidden="true" />
            <div>
              <strong>We could not complete that action</strong>
              {errors.map((message) => (
                <p key={message}>{message}</p>
              ))}
            </div>
          </div>
        ) : null}

        {isRunning ? (
          <p className="cap-results-state">
            <LoaderCircle size={16} className="cap-spin" aria-hidden="true" />
            {runLabel}
          </p>
        ) : null}

        {!isRunning && !result && !errors.length ? (
          <div className="cap-results-empty">
            <Play size={18} aria-hidden="true" />
            <div>
              <strong>Nothing has run yet</strong>
              <p>
                Run the sample tests to check your solution against the visible
                examples, or submit the question to run the hidden tests.
              </p>
            </div>
          </div>
        ) : null}

        {result ? (
          <>
            <p className="cap-results-headline">
              <strong>{result.summary}</strong>
              {isHidden ? (
                <span>
                  Hidden test inputs and outputs are not shown. You can see whether
                  each case passed, how long it took, and the type of error.
                </span>
              ) : null}
            </p>
            {result.cases.length ? (
              <div className="cap-case-list">
                {result.cases.map((testCase) => (
                  <CaseCard
                    key={`${result.kind}-${testCase.index}`}
                    testCase={testCase}
                    showOutputs={result.kind === "sample"}
                  />
                ))}
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </section>
  );
}
