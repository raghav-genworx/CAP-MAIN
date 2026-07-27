import { AlertTriangle, Send, Timer } from "lucide-react";

import { Button } from "../../../../components/ui/Button";
import { CandidateBrandMark } from "../CandidatePageShell";
import { CandidateStatusIndicator } from "./CandidateStatusIndicator";
import type { SaveState } from "./types";
import { formatClock, formatDurationWords } from "../../utils/format";

interface CandidateAssessmentHeaderProps {
  assessmentTitle: string;
  candidateName: string;
  questionPosition: number;
  questionCount: number;
  remainingSeconds: number;
  saveState: SaveState;
  showWarnings: boolean;
  warningCount: number;
  warningLimit: number;
  onFinish: () => void;
  finishDisabled: boolean;
}

export function CandidateAssessmentHeader({
  assessmentTitle,
  candidateName,
  questionPosition,
  questionCount,
  remainingSeconds,
  saveState,
  showWarnings,
  warningCount,
  warningLimit,
  onFinish,
  finishDisabled,
}: CandidateAssessmentHeaderProps) {
  const timerTone =
    remainingSeconds <= 60 ? "is-critical" : remainingSeconds <= 300 ? "is-low" : "";
  const timerNote =
    remainingSeconds <= 60
      ? "Under a minute left"
      : remainingSeconds <= 300
        ? "Low time"
        : "Time remaining";

  return (
    <header className="cap-ws-header">
      <div className="cap-ws-header-identity">
        <CandidateBrandMark compact />
        <span className="cap-ws-divider" aria-hidden="true" />
        <div className="cap-ws-titles">
          <p className="cap-ws-assessment" title={assessmentTitle}>
            {assessmentTitle}
          </p>
          <p className="cap-ws-position">
            Question {questionPosition} of {questionCount}
          </p>
        </div>
      </div>

      <div className="cap-ws-header-meta">
        <p className="cap-ws-candidate">
          <span>Candidate</span>
          <strong title={candidateName}>{candidateName}</strong>
        </p>

        <CandidateStatusIndicator state={saveState} className="cap-ws-save" />

        <div className={`cap-timer ${timerTone}`} role="timer">
          <Timer size={16} aria-hidden="true" />
          <span className="cap-timer-body">
            <span className="cap-timer-note">{timerNote}</span>
            <span className="cap-timer-value cap-numeric" aria-hidden="true">
              {formatClock(remainingSeconds)}
            </span>
          </span>
          <span className="sr-only">
            {`Time remaining: ${formatDurationWords(remainingSeconds)}`}
          </span>
        </div>

        {showWarnings ? (
          <p
            className={`cap-warning-count ${warningCount ? "has-warnings" : ""}`}
            aria-label={`Proctoring warnings: ${warningCount} of ${warningLimit}`}
          >
            <AlertTriangle size={15} aria-hidden="true" />
            <span aria-hidden="true">
              {warningCount}/{warningLimit}
            </span>
          </p>
        ) : null}

        <Button
          type="button"
          className="cap-btn cap-btn-sm"
          onClick={onFinish}
          disabled={finishDisabled}
        >
          <Send size={15} aria-hidden="true" />
          Finish Assessment
        </Button>
      </div>
    </header>
  );
}
