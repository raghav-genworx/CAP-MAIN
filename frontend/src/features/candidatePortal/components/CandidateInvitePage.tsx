import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  CircleSlash,
  LoaderCircle,
  PauseCircle,
  PlayCircle,
  RotateCcw,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import {
  startCandidateAssessment,
  verifyInvite,
} from "../services/candidatePortalService";
import type { CandidateInviteVerificationResponse } from "../types/CandidatePortal";
import {
  clearSubmissionResult,
  saveCandidateInviteToken,
  saveCandidateSessionToken,
} from "../utils/sessionStorage";
import { formatCountdown, formatDateTime, formatMinutes } from "../utils/format";
import { CandidatePageShell } from "./CandidatePageShell";

const ACKNOWLEDGEMENT_ID = "candidate-start-acknowledgement";

type WindowStatus = "scheduled" | "active" | "paused" | "closed" | "submitted";

interface AssessmentWindow {
  status: WindowStatus;
  headline: string;
  detail: string;
  countdownSeconds: number;
  countdownLabel: string;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function resolveWindow(
  invite: CandidateInviteVerificationResponse,
  nowMs: number,
): AssessmentWindow {
  if (invite.status === "submitted" || invite.status === "auto_submitted") {
    return {
      status: "submitted",
      headline: "Already submitted",
      detail:
        "This assessment has been submitted. You do not need to do anything else.",
      countdownSeconds: 0,
      countdownLabel: "",
    };
  }
  if (invite.slot_status === "paused") {
    return {
      status: "paused",
      headline: "Temporarily paused",
      detail:
        "Your recruiter has paused this assessment session. This page updates when it resumes.",
      countdownSeconds: 0,
      countdownLabel: "",
    };
  }
  if (invite.slot_status === "closed") {
    return {
      status: "closed",
      headline: "Assessment window closed",
      detail:
        "This assessment is no longer accepting responses. Contact your recruiter if you believe this is a mistake.",
      countdownSeconds: 0,
      countdownLabel: "",
    };
  }

  const secondsUntilStart = Math.max(
    0,
    Math.floor((new Date(invite.start_at).getTime() - nowMs) / 1000),
  );
  const secondsUntilClose = Math.max(
    0,
    Math.floor((new Date(invite.end_at).getTime() - nowMs) / 1000),
  );

  if (secondsUntilStart > 0) {
    return {
      status: "scheduled",
      headline: "Not open yet",
      detail: `Your assessment window opens on ${formatDateTime(invite.start_at)}.`,
      countdownSeconds: secondsUntilStart,
      countdownLabel: "Opens in",
    };
  }
  if (secondsUntilClose > 0) {
    return {
      status: "active",
      headline: "Open now",
      detail:
        "You can begin whenever you are ready. Your own timer starts when you begin.",
      countdownSeconds: secondsUntilClose,
      countdownLabel: "Window closes in",
    };
  }
  return {
    status: "closed",
    headline: "Assessment window closed",
    detail:
      "This assessment is no longer accepting responses. Contact your recruiter if you believe this is a mistake.",
    countdownSeconds: 0,
    countdownLabel: "",
  };
}

const WINDOW_ICON = {
  scheduled: CalendarClock,
  active: CheckCircle2,
  paused: PauseCircle,
  closed: CircleSlash,
  submitted: CheckCircle2,
} as const;

export function CandidateInvitePage() {
  const navigate = useNavigate();
  const { token = "" } = useParams();
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [acknowledged, setAcknowledged] = useState(false);

  const inviteQuery = useQuery({
    queryKey: ["candidate-invite", token],
    queryFn: async () => verifyInvite(token),
    enabled: Boolean(token),
  });
  const startMutation = useMutation({
    mutationFn: async () => startCandidateAssessment(token),
    onSuccess: (data) => {
      clearSubmissionResult();
      saveCandidateInviteToken(token);
      saveCandidateSessionToken(data.session_token);
      navigate("/candidate/portal");
    },
  });

  const invite = inviteQuery.data;

  useEffect(() => {
    clearSubmissionResult();
  }, [token]);

  useEffect(() => {
    const interval = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  const assessmentWindow = useMemo(
    () => (invite ? resolveWindow(invite, nowMs) : null),
    [invite, nowMs],
  );

  if (!token || inviteQuery.isError) {
    return (
      <CandidatePageShell>
        <Card className="cap-panel cap-panel-narrow" aria-labelledby="cap-invite-error">
          <div className="cap-state-icon is-danger" aria-hidden="true">
            <AlertTriangle size={22} />
          </div>
          <div className="cap-panel-intro">
            <h1 id="cap-invite-error">We could not open this assessment</h1>
            <p role="alert">
              {token
                ? errorMessage(
                    inviteQuery.error,
                    "This assessment link could not be verified.",
                  )
                : "No assessment code was provided."}
            </p>
          </div>
          <p className="cap-muted">
            Check that you used the most recent link or code from your invitation
            email. If the problem continues, contact the recruiter who invited you.
          </p>
          <div className="cap-actions">
            <Button
              type="button"
              variant="secondary"
              className="cap-btn"
              onClick={() => void inviteQuery.refetch()}
              disabled={inviteQuery.isFetching}
            >
              <RotateCcw size={16} aria-hidden="true" />
              {inviteQuery.isFetching ? "Retrying…" : "Try again"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="cap-btn"
              onClick={() => navigate("/candidate/join")}
            >
              Enter a different code
            </Button>
          </div>
        </Card>
      </CandidatePageShell>
    );
  }

  if (!invite || !assessmentWindow) {
    return (
      <CandidatePageShell>
        <Card className="cap-panel cap-panel-narrow" aria-labelledby="cap-invite-loading">
          <div className="cap-panel-intro">
            <h1 id="cap-invite-loading">Checking your assessment link</h1>
            <p className="cap-inline-status" role="status">
              <LoaderCircle size={16} className="cap-spin" aria-hidden="true" />
              <span>Verifying your invitation. This usually takes a moment.</span>
            </p>
          </div>
          <div className="cap-skeleton-stack" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        </Card>
      </CandidatePageShell>
    );
  }

  const isResume = invite.status === "in_progress" && invite.allow_resume;
  const canStart = invite.can_start && assessmentWindow.status === "active";
  const startBlocked = !canStart;
  const WindowIcon = WINDOW_ICON[assessmentWindow.status];
  const startLabel = isResume ? "Resume Assessment" : "Start Assessment";
  const pendingLabel = isResume ? "Resuming…" : "Starting…";

  return (
    <CandidatePageShell>
      <Card className="cap-panel" aria-labelledby="cap-lobby-title">
        <div className="cap-panel-intro">
          <p className="cap-eyebrow">Assessment lobby</p>
          <h1 id="cap-lobby-title">Welcome, {invite.candidate_name}</h1>
          <p className="cap-lead">{invite.assessment_title}</p>
          <p className="cap-muted">{invite.slot_title}</p>
        </div>

        <div
          className={`cap-window-status is-${assessmentWindow.status}`}
          role="status"
        >
          <span className="cap-window-status-icon" aria-hidden="true">
            <WindowIcon size={18} />
          </span>
          <div className="cap-window-status-body">
            <strong>{assessmentWindow.headline}</strong>
            <p>{assessmentWindow.detail}</p>
          </div>
          {assessmentWindow.countdownSeconds > 0 ? (
            <div className="cap-window-countdown">
              <span>{assessmentWindow.countdownLabel}</span>
              <strong className="cap-numeric">
                {formatCountdown(assessmentWindow.countdownSeconds)}
              </strong>
            </div>
          ) : null}
        </div>

        <dl className="cap-facts">
          <div>
            <dt>Candidate</dt>
            <dd>{invite.candidate_name}</dd>
          </div>
          <div>
            <dt>Email</dt>
            <dd className="cap-facts-wrap">{invite.candidate_email}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>{formatMinutes(invite.duration_minutes)}</dd>
          </div>
          <div>
            <dt>Opens</dt>
            <dd>{formatDateTime(invite.start_at)}</dd>
          </div>
          <div>
            <dt>Closes</dt>
            <dd>{formatDateTime(invite.end_at)}</dd>
          </div>
          <div>
            <dt>If you get disconnected</dt>
            <dd>
              {invite.allow_resume
                ? "You can return and resume while the window is open."
                : "Only one attempt is available for this assessment."}
            </dd>
          </div>
        </dl>

        {invite.instructions ? (
          <section className="cap-subsection" aria-labelledby="cap-lobby-instructions">
            <h2 id="cap-lobby-instructions">Instructions from your recruiter</h2>
            <p className="cap-prose">{invite.instructions}</p>
          </section>
        ) : null}

        <section className="cap-subsection" aria-labelledby="cap-lobby-checklist">
          <h2 id="cap-lobby-checklist">Before you begin</h2>
          <ul className="cap-checklist">
            <li>
              Your work is saved automatically while you code, and you can also
              save at any time.
            </li>
            <li>
              The timer runs for the length of your assessment session once you
              begin.
            </li>
            <li>
              The languages you can use are shown inside the coding workspace, per
              question.
            </li>
            <li>
              Depending on how this assessment is configured, browser activity such
              as leaving the assessment, switching tabs, or copying may be recorded.
            </li>
            <li>
              Some assessments require fullscreen. If yours does, you will be
              prompted when the workspace opens.
            </li>
            <li>
              Use a desktop or laptop with a stable connection. Final submission
              cannot be undone.
            </li>
          </ul>
        </section>

        <div className="cap-start-block">
          <div className="cap-check">
            <input
              id={ACKNOWLEDGEMENT_ID}
              type="checkbox"
              checked={acknowledged}
              disabled={startBlocked || startMutation.isPending}
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
            <label htmlFor={ACKNOWLEDGEMENT_ID}>
              I have read the instructions and understand that the assessment timer
              starts when I begin.
            </label>
          </div>

          {startBlocked ? (
            <p className="cap-inline-note">
              {assessmentWindow.status === "submitted"
                ? "This assessment has already been submitted."
                : assessmentWindow.status === "scheduled"
                  ? "The Start button becomes available when your window opens."
                  : assessmentWindow.status === "paused"
                    ? "You can start once your recruiter resumes this session."
                    : "This assessment is not open right now."}
            </p>
          ) : null}

          <Button
            type="button"
            className="cap-btn cap-btn-lg"
            onClick={() => void startMutation.mutateAsync().catch(() => undefined)}
            disabled={startBlocked || !acknowledged || startMutation.isPending}
          >
            {startMutation.isPending ? (
              <>
                <LoaderCircle size={17} className="cap-spin" aria-hidden="true" />
                {pendingLabel}
              </>
            ) : (
              <>
                {isResume ? (
                  <RotateCcw size={17} aria-hidden="true" />
                ) : (
                  <PlayCircle size={17} aria-hidden="true" />
                )}
                {startLabel}
              </>
            )}
          </Button>

          <p className="cap-live-note" role="status">
            {startMutation.isPending
              ? "Opening your assessment workspace."
              : ""}
          </p>

          {startMutation.isError ? (
            <div className="cap-alert is-danger" role="alert">
              <AlertTriangle size={16} aria-hidden="true" />
              <div>
                <strong>We could not open your assessment</strong>
                <p>
                  {errorMessage(
                    startMutation.error,
                    "Something went wrong while starting your assessment.",
                  )}
                </p>
              </div>
              <Button
                type="button"
                variant="secondary"
                className="cap-btn cap-btn-sm"
                onClick={() => void startMutation.mutateAsync().catch(() => undefined)}
              >
                Retry
              </Button>
            </div>
          ) : null}
        </div>
      </Card>
    </CandidatePageShell>
  );
}
