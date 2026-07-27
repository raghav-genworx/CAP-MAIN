import { Eye, Maximize, PauseCircle, ShieldCheck, TriangleAlert } from "lucide-react";

import { Button } from "../../../../components/ui/Button";

/**
 * Standing explanation of what this assessment actually monitors. Content is
 * driven entirely by `proctoring_mode`; nothing here implies camera,
 * microphone, face tracking, or screen recording, because none are implemented.
 */
export function CandidateProctoringNotice({
  mode,
  warningCount,
  warningLimit,
}: {
  mode: "none" | "basic" | "strict";
  warningCount: number;
  warningLimit: number;
}) {
  if (mode === "none") {
    return null;
  }

  const remaining = Math.max(0, warningLimit - warningCount);

  return (
    <section className="cap-proctor-notice" aria-label="Monitoring for this assessment">
      <p className="cap-proctor-line">
        {mode === "strict" ? (
          <ShieldCheck size={14} aria-hidden="true" />
        ) : (
          <Eye size={14} aria-hidden="true" />
        )}
        <span>
          {mode === "strict"
            ? "This assessment is strictly monitored. Fullscreen is required, copy and paste are disabled, and leaving the assessment is recorded."
            : "Browser activity such as switching tabs, losing focus, or using the clipboard is recorded for this assessment."}
        </span>
      </p>
      {warningCount > 0 ? (
        <p className="cap-proctor-line is-warning">
          <TriangleAlert size={14} aria-hidden="true" />
          <span>
            {warningCount} of {warningLimit} tab-switch warnings recorded.{" "}
            {remaining > 0
              ? `Your assessment is submitted automatically after ${warningLimit}.`
              : "Your assessment is being submitted."}
          </span>
        </p>
      ) : null}
    </section>
  );
}

/** Blocking gate shown when strict fullscreen has not been entered. */
export function CandidateFullscreenGate({ onEnterFullscreen }: { onEnterFullscreen: () => void }) {
  return (
    <div className="cap-gate" role="dialog" aria-modal="true" aria-labelledby="cap-gate-title">
      <div className="cap-gate-body">
        <span className="cap-state-icon" aria-hidden="true">
          <Maximize size={22} />
        </span>
        <h2 id="cap-gate-title">Fullscreen is required</h2>
        <p>
          This assessment runs in fullscreen. Your work is saved — enter fullscreen
          to continue. Leaving fullscreen again ends the assessment and submits
          your work.
        </p>
        <Button type="button" className="cap-btn" onClick={onEnterFullscreen} autoFocus>
          <Maximize size={16} aria-hidden="true" />
          Enter fullscreen
        </Button>
      </div>
    </div>
  );
}

/** Non-blocking banner shown while the recruiter has paused the session. */
export function CandidatePausedNotice() {
  return (
    <div className="cap-gate" role="status" aria-labelledby="cap-paused-title">
      <div className="cap-gate-body">
        <span className="cap-state-icon" aria-hidden="true">
          <PauseCircle size={22} />
        </span>
        <h2 id="cap-paused-title">Your assessment is paused</h2>
        <p>
          Your timer is frozen and your work is saved. This page continues to
          check for updates and reopens automatically when the session resumes.
        </p>
      </div>
    </div>
  );
}
