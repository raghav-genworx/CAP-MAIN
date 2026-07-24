import { useMutation, useQuery } from "@tanstack/react-query";
import { PlayCircle, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import {
  startCandidateAssessment,
  verifyInvite,
} from "../services/candidatePortalService";
import {
  clearSubmissionResult,
  saveCandidateSessionToken,
  saveCandidateInviteToken,
} from "../utils/sessionStorage";

function formatDateTime(value: string) {
  return new Date(value).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatCountdown(seconds: number) {
  const safeSeconds = Math.max(0, seconds);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const remainder = safeSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${String(minutes).padStart(2, "0")}m ${String(remainder).padStart(2, "0")}s`;
  }
  return `${minutes}m ${String(remainder).padStart(2, "0")}s`;
}

function inviteError(error: unknown) {
  return error instanceof Error ? error.message : "Unable to verify this invite link.";
}

export function CandidateInvitePage() {
  const navigate = useNavigate();
  const { token = "" } = useParams();
  const [nowMs, setNowMs] = useState(() => Date.now());
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

  const inviteWindow = useMemo(() => {
    if (!invite) {
      return {
        status: "loading",
        label: "Checking assessment window...",
        secondsUntilStart: 0,
        secondsUntilClose: 0,
      };
    }
    if (invite.slot_status === "paused") {
      return {
        status: "paused",
        label: "This assessment is temporarily paused by the recruiter.",
        secondsUntilStart: 0,
        secondsUntilClose: 0,
      };
    }
    if (invite.slot_status === "closed") {
      return {
        status: "closed",
        label: "This assessment window is closed.",
        secondsUntilStart: 0,
        secondsUntilClose: 0,
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
        label: `To be started in ${formatCountdown(secondsUntilStart)}`,
        secondsUntilStart,
        secondsUntilClose,
      };
    }
    if (secondsUntilClose > 0) {
      return {
        status: "active",
        label: `Active now. Accepting responses closes in ${formatCountdown(secondsUntilClose)}`,
        secondsUntilStart,
        secondsUntilClose,
      };
    }
    return {
      status: "closed",
      label: "This assessment window is closed.",
      secondsUntilStart,
      secondsUntilClose,
    };
  }, [invite, nowMs]);

  return (
    <main className="candidate-shell candidate-shell-branded">
      <Card className="candidate-card invite-card">
        <div className="candidate-access-heading">
          <span className="candidate-access-icon" aria-hidden="true">
            <ShieldCheck size={22} />
          </span>
          <div>
            <span className="candidate-kicker">Coding Assessment Platform</span>
            <h1>{invite ? `Welcome, ${invite.candidate_name}` : "Assessment Invite"}</h1>
            <p className="candidate-muted">
              Review the assessment details before entering your workspace.
            </p>
          </div>
        </div>

        {inviteQuery.isLoading ? (
          <p className="candidate-muted">Validating your secure assessment link...</p>
        ) : null}

        {invite ? (
          <>
            <div className="invite-hero">
              <div>
                <span>Assessment</span>
                <strong>{invite.assessment_title}</strong>
                <p>{invite.slot_title}</p>
              </div>
              <div>
                <span>Duration</span>
                <strong>{invite.duration_minutes} min</strong>
                <p>{invite.allow_resume ? "Resume is allowed before expiry" : "Single active attempt"}</p>
              </div>
            </div>

            <div className="invite-window">
              <div>
                <span>Opens</span>
                <strong>{formatDateTime(invite.start_at)}</strong>
              </div>
              <div>
                <span>Closes</span>
                <strong>{formatDateTime(invite.end_at)}</strong>
              </div>
            </div>

            <div className={`candidate-window-status is-${inviteWindow.status}`}>
              <span>{inviteWindow.status === "active" ? "Active status" : "Window status"}</span>
              <strong>{inviteWindow.label}</strong>
            </div>

            <section className="candidate-instructions">
              <h2>Before you start</h2>
              <p>{invite.instructions || "Read each question carefully, save your progress, and submit before the timer ends."}</p>
              <ul>
                <li>Use only the supported languages shown inside the test portal.</li>
                <li>Your work autosaves during the test, but use Save Progress before switching questions if your network is unstable.</li>
                <li>The final submission runs hidden checks first; detailed evaluation runs only if the pass mark is met.</li>
              </ul>
            </section>

            {!invite.can_start ? (
              <p className="form-error">
                This assessment is not open right now or has already been submitted.
              </p>
            ) : null}

            <Button
              type="button"
              onClick={() => void startMutation.mutateAsync()}
              disabled={!invite.can_start || startMutation.isPending}
            >
              <PlayCircle size={17} aria-hidden="true" />
              {startMutation.isPending ? "Starting..." : "Start Assessment"}
            </Button>
          </>
        ) : null}

        {inviteQuery.error ? <p className="form-error">{inviteError(inviteQuery.error)}</p> : null}
        {startMutation.error ? <p className="form-error">{inviteError(startMutation.error)}</p> : null}
      </Card>
    </main>
  );
}
