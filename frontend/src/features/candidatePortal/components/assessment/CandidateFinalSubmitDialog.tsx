import { TriangleAlert } from "lucide-react";
import { useEffect, useRef } from "react";

import { Button } from "../../../../components/ui/Button";
import {
  QUESTION_STATUS_LABEL,
  type QuestionProgress,
} from "./types";
import { formatClock, formatDurationWords } from "../../utils/format";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface CandidateFinalSubmitDialogProps {
  items: QuestionProgress[];
  attemptedCount: number;
  submittedCount: number;
  unansweredCount: number;
  mandatoryUnansweredCount: number;
  remainingSeconds: number;
  requiresEndConfirmation: boolean;
  confirmationValue: string;
  onConfirmationChange: (value: string) => void;
  isSubmitting: boolean;
  errorMessage: string;
  onClose: () => void;
  onSubmit: () => void;
  onReview: (questionId: string) => void;
}

export function CandidateFinalSubmitDialog({
  items,
  attemptedCount,
  submittedCount,
  unansweredCount,
  mandatoryUnansweredCount,
  remainingSeconds,
  requiresEndConfirmation,
  confirmationValue,
  onConfirmationChange,
  isSubmitting,
  errorMessage,
  onClose,
  onSubmit,
  onReview,
}: CandidateFinalSubmitDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  const confirmationBlocked =
    requiresEndConfirmation && confirmationValue.trim().toLowerCase() !== "end";

  useEffect(() => {
    previouslyFocusedRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const first = dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE);
    (first || dialogRef.current)?.focus();
    const restoreTo = previouslyFocusedRef.current;
    return () => restoreTo?.focus();
  }, []);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) {
        return;
      }
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE),
      );
      if (!focusable.length) {
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [onClose]);

  return (
    <div className="cap-modal-backdrop">
      <div
        className="cap-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cap-final-title"
        aria-describedby="cap-final-description"
        ref={dialogRef}
        tabIndex={-1}
      >
        <div className="cap-modal-head">
          <h2 id="cap-final-title">Finish and submit your assessment?</h2>
          <p id="cap-final-description">
            Submitting ends your assessment. You will not be able to return, edit
            your code, or submit again.
          </p>
        </div>

        <dl className="cap-modal-stats">
          <div>
            <dt>Attempted</dt>
            <dd>
              {attemptedCount} of {items.length}
            </dd>
          </div>
          <div>
            <dt>Questions submitted</dt>
            <dd>
              {submittedCount} of {items.length}
            </dd>
          </div>
          <div>
            <dt>Unanswered</dt>
            <dd>{unansweredCount}</dd>
          </div>
          <div>
            <dt>Required unanswered</dt>
            <dd>{mandatoryUnansweredCount}</dd>
          </div>
          <div>
            <dt>Time remaining</dt>
            <dd className="cap-numeric" aria-hidden="true">
              {formatClock(remainingSeconds)}
            </dd>
            <dd className="sr-only">{formatDurationWords(remainingSeconds)}</dd>
          </div>
        </dl>

        {unansweredCount > 0 ? (
          <div
            className={`cap-alert ${mandatoryUnansweredCount > 0 ? "is-danger" : "is-warning"}`}
            role="alert"
          >
            <TriangleAlert size={16} aria-hidden="true" />
            <div>
              <strong>
                {unansweredCount} question{unansweredCount === 1 ? "" : "s"} not
                answered
              </strong>
              {mandatoryUnansweredCount > 0 ? (
                <p>
                  {mandatoryUnansweredCount} of them{" "}
                  {mandatoryUnansweredCount === 1 ? "is" : "are"} required for this
                  assessment.
                </p>
              ) : null}
            </div>
          </div>
        ) : null}

        <div className="cap-modal-list">
          <h3>Question status</h3>
          <ul>
            {items.map((item) => (
              <li key={item.question.id} className={`is-${item.status}`}>
                <span className="cap-modal-list-index" aria-hidden="true">
                  {item.question.question_order}
                </span>
                <span className="cap-modal-list-title">
                  {item.question.title}
                  {item.question.is_mandatory ? (
                    <span className="cap-modal-list-required"> · Required</span>
                  ) : null}
                </span>
                <span className="cap-modal-list-status">
                  {QUESTION_STATUS_LABEL[item.status]}
                </span>
                <button
                  type="button"
                  className="cap-link-button"
                  onClick={() => onReview(item.question.id)}
                >
                  Review
                  <span className="sr-only">
                    {` question ${item.question.question_order}, ${item.question.title}`}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        {requiresEndConfirmation ? (
          <div className="cap-field">
            <label htmlFor="cap-final-confirm">
              More than half of your time is still left. Type <strong>END</strong>{" "}
              to confirm you want to submit now.
            </label>
            <input
              id="cap-final-confirm"
              className="cap-input"
              value={confirmationValue}
              autoComplete="off"
              placeholder="END"
              onChange={(event) => onConfirmationChange(event.target.value)}
            />
          </div>
        ) : null}

        {errorMessage ? (
          <div className="cap-alert is-danger" role="alert">
            <TriangleAlert size={16} aria-hidden="true" />
            <div>
              <strong>Your assessment was not submitted</strong>
              <p>{errorMessage}</p>
            </div>
          </div>
        ) : null}

        <div className="cap-modal-actions">
          <Button
            type="button"
            variant="secondary"
            className="cap-btn"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Return to assessment
          </Button>
          <Button
            type="button"
            className="cap-btn cap-btn-final"
            onClick={onSubmit}
            disabled={isSubmitting || confirmationBlocked}
          >
            {isSubmitting ? "Submitting…" : "Submit assessment"}
          </Button>
        </div>
      </div>
    </div>
  );
}
