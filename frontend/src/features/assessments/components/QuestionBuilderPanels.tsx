import { Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import type { QuestionAIDraftProgressEvent } from "../types/QuestionBank";
import { languageDisplayName } from "../utils/questionLanguage";

type AgentRunScope =
  | "full"
  | "basics"
  | "problem"
  | "problem_field"
  | "constraints"
  | "constraints_formats"
  | "examples"
  | "tests"
  | "tests_solution"
  | "solution"
  | "other_languages"
  | "recruiter_validation"
  | "difficulty"
  | "metadata"
  | "validation";

interface QuestionBuilderStep {
  id: number;
  title: string;
  actionLabel: string;
}

export function AgentRunOverlay({
  scope,
  commentary,
  lines,
  progressEvents,
  latestEvent,
  onStop,
}: {
  scope: AgentRunScope;
  commentary: string;
  lines: string[];
  progressEvents: QuestionAIDraftProgressEvent[];
  latestEvent: QuestionAIDraftProgressEvent | null;
  onStop?: () => void;
}) {
  const title =
    scope === "full"
      ? "Generating full question draft"
      : scope === "validation"
        ? "Running execution validation"
        : "Generating section";
  const showLiveProgress = Boolean(latestEvent);
  const liveUpdates = progressEvents
    .filter(
      (event) =>
        event.type !== "validation_case_start" && event.type !== "validation_case_result",
    )
    .slice(-5);
  const liveCommentary = latestEvent?.message || commentary;
  const progressValue = latestEvent?.progress ?? null;
  const latestModelEvent = [...progressEvents]
    .reverse()
    .find((event) => Boolean(event.ai_model));
  const modelLabel = latestModelEvent?.ai_model || "Connecting...";
  const providerLabel = latestModelEvent?.ai_provider || "AI";
  const latestValidationPass = progressEvents.reduce(
    (latest, event) => Math.max(latest, event.validation_pass || 0),
    0,
  );
  const validationCaseMap = new Map<string, QuestionAIDraftProgressEvent>();
  progressEvents.forEach((event) => {
    if (
      event.validation_pass !== latestValidationPass ||
      !event.test_bucket ||
      !event.test_index ||
      !event.test_outcome
    ) {
      return;
    }
    validationCaseMap.set(`${event.test_bucket}-${event.test_index}`, event);
  });
  const validationCases = Array.from(validationCaseMap.values()).sort((left, right) => {
    const leftBucket = left.test_bucket === "sample" ? 0 : 1;
    const rightBucket = right.test_bucket === "sample" ? 0 : 1;
    return leftBucket - rightBucket || (left.test_index || 0) - (right.test_index || 0);
  });
  const completedValidationCases = validationCases.filter(
    (event) => event.test_outcome !== "running",
  ).length;

  return (
    <div className="agent-run-backdrop" role="status" aria-live="polite">
      <Card className="agent-run-modal">
        <div className="agent-run-head">
          <div className="agent-orb" aria-hidden="true" />
          <div>
            <span>{scope === "validation" ? "Validation" : "Generation"}</span>
            <h2>{title}</h2>
            <p>{liveCommentary}</p>
            <div className="agent-model-chip" aria-label={`Current AI model: ${modelLabel}`}>
              <b>{providerLabel}</b>
              <code>{modelLabel}</code>
            </div>
          </div>
        </div>
        {showLiveProgress && progressValue !== null ? (
          <div className="agent-run-progress" aria-live="polite">
            <div className="agent-run-progress-head">
              <div>
                <span>Live progress</span>
                <strong>{latestEvent?.next_node || latestEvent?.current_node || "working"}</strong>
              </div>
              <em>{progressValue}%</em>
            </div>
            <div
              className="agent-run-progress-track"
              role="progressbar"
              aria-label="AI generation progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progressValue}
            >
              <span style={{ width: `${progressValue}%` }} />
            </div>
          </div>
        ) : null}
        {validationCases.length > 0 ? (
          <section className="agent-test-progress" aria-label="Live test case validation">
            <div className="agent-test-progress-head">
              <div>
                <span>Test execution</span>
                <strong>
                  {completedValidationCases} of {latestEvent?.overall_total || validationCases.length} checked
                </strong>
              </div>
              <em>Pass {latestValidationPass}</em>
            </div>
            <div className="agent-test-case-list">
              {validationCases.map((event) => {
                const outcome = event.test_outcome || "running";
                const statusLabel =
                  outcome === "passed"
                    ? "Passed"
                    : outcome === "wrong"
                      ? "Wrong answer"
                      : outcome === "error"
                        ? "Error"
                        : "Running";
                const compactValue = (value: string | undefined, fallback: string) => {
                  const compacted = (value || fallback).replace(/\s+/g, " ").trim();
                  return compacted.length > 120
                    ? `${compacted.slice(0, 117)}...`
                    : compacted;
                };
                const inputPreview = compactValue(event.test_input, "No standard input");
                const expectedPreview = compactValue(event.expected_output, "(empty)");
                const actualPreview =
                  outcome === "running"
                    ? "Waiting for program output"
                    : compactValue(event.actual_output, "(empty)");
                return (
                  <article
                    key={`${latestValidationPass}-${event.test_bucket}-${event.test_index}`}
                    className={`agent-test-case is-${outcome}`}
                  >
                    <div className="agent-test-case-title">
                      <span aria-hidden="true" />
                      <strong>
                        {event.test_bucket === "sample" ? "Sample" : "Hidden"} {event.test_index}
                      </strong>
                      {event.test_language ? <b>{languageDisplayName(event.test_language)}</b> : null}
                      <em>{statusLabel}</em>
                    </div>
                    <div className="agent-test-io-grid">
                      <div>
                        <span>Input</span>
                        <code title={event.test_input || ""}>{inputPreview}</code>
                      </div>
                      <div>
                        <span>Expected</span>
                        <code title={event.expected_output || ""}>{expectedPreview}</code>
                      </div>
                      <div>
                        <span>Actual</span>
                        <code title={event.actual_output || ""}>{actualPreview}</code>
                      </div>
                    </div>
                    {outcome === "error" && event.error_message ? (
                      <p>{event.error_message}</p>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </section>
        ) : null}
        {showLiveProgress ? (
          <div className="agent-thinking-list">
            {liveUpdates.map((event, index) => (
              <div
                key={`${event.type}-${event.current_node || "start"}-${index}`}
                className={[
                  "agent-thinking-line",
                  index === liveUpdates.length - 1 ? "is-active" : "is-complete",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <span aria-hidden="true" />
                <p>{event.message}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="agent-thinking-list">
            {lines.map((line, index) => (
              <div
                key={line}
                className={index === 0 ? "agent-thinking-line is-active" : "agent-thinking-line"}
              >
                <span aria-hidden="true" />
                <p>
                  {line}
                  <b className="thinking-dots" aria-hidden="true" />
                </p>
              </div>
            ))}
          </div>
        )}
        <p className="agent-run-foot">
          You can open another menu while this continues. Return to this question from
          Question Management to view the live updates or review the completed result.
        </p>
        {onStop ? (
          <div style={{ marginTop: "16px", display: "flex", justifyContent: "center" }}>
            <Button
              type="button"
              variant="secondary"
              onClick={onStop}
              style={{
                backgroundColor: "#ef4444",
                color: "#ffffff",
                border: "none",
                fontWeight: 600,
                padding: "8px 24px",
                borderRadius: "8px"
              }}
            >
              Stop Generation
            </Button>
          </div>
        ) : null}
      </Card>
    </div>
  );
}

export function StepCard({
  step,
  busy = false,
  onGenerate,
  children,
}: {
  step: QuestionBuilderStep;
  busy?: boolean;
  onGenerate?: () => void;
  children: ReactNode;
}) {
  return (
    <Card
      className={`step-card${busy ? " is-loading" : ""}`}
    >
      {onGenerate ? (
        <div className="step-card-tools">
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={(event) => {
              event.stopPropagation();
              onGenerate();
            }}
          >
            <Sparkles size={16} />
            {busy ? "Working..." : step.actionLabel}
          </Button>
        </div>
      ) : null}
      <div className="step-card-body">
        {children}
      </div>
    </Card>
  );
}
