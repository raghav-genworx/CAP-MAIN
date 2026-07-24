import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { DataTable } from "../../../components/common/DataTable";
import { EmptyState } from "../../../components/common/EmptyState";
import { StatusBadge } from "../../../components/common/StatusBadge";
import { useAuth } from "../../auth";
import {
  useAssessments,
  assessmentPath,
  assessmentTestPath,
  fetchAssessmentSlots,
  fetchSlotMonitoring,
} from "../../assessments";
import type {
  Assessment,
  AssessmentStatus,
  AssessmentSlot,
  CandidateAssessmentStatus,
  MonitoringCandidate,
  SlotStatus,
} from "../../assessments";

type CandidateStatusCounts = Record<CandidateAssessmentStatus, number>;

interface AssessmentActivityBundle {
  assessmentId: string;
  sessions: Array<{
    slot: AssessmentSlot;
    monitoring: MonitoringCandidate[];
  }>;
}

interface SessionRow {
  assessmentId: string;
  assessmentTitle: string;
  assessmentStatus: AssessmentStatus;
  questionCount: number;
  slotId: string;
  slotTitle: string;
  slotStatus: SlotStatus;
  effectiveStatus: SlotStatus;
  startAt: string;
  endAt: string;
  candidateCount: number;
  statusCounts: CandidateStatusCounts;
  submittedCount: number;
  isLive: boolean;
  needsAttention: boolean;
  startsSoon: boolean;
}

function createStatusCounts(): CandidateStatusCounts {
  return {
    not_started: 0,
    in_progress: 0,
    submitted: 0,
    auto_submitted: 0,
    revoked: 0,
  };
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "Not set";
  }

  return new Date(value).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatStatusLabel(value: string) {
  return value.replaceAll("_", " ");
}

function pluralize(count: number, label: string) {
  return `${count} ${label}${count === 1 ? "" : "s"}`;
}

function buildSessionRow(
  assessment: Assessment,
  slot: AssessmentSlot,
  monitoring: MonitoringCandidate[],
): SessionRow {
  const now = Date.now();
  const statusCounts = monitoring.reduce((counts, candidate) => {
    counts[candidate.status] += 1;
    return counts;
  }, createStatusCounts());

  const candidateCount = Math.max(slot.candidate_count, monitoring.length);
  const submittedCount = Math.min(
    candidateCount,
    Math.max(
      slot.submitted_count,
      statusCounts.submitted + statusCounts.auto_submitted,
    ),
  );
  const isLive =
    slot.effective_status === "active" || statusCounts.in_progress > 0;
  const startsAt = new Date(slot.start_at).getTime();
  const startsSoon =
    !isLive &&
    slot.effective_status === "scheduled" &&
    startsAt >= now &&
    startsAt - now <= 1000 * 60 * 60 * 48;
  const needsAttention =
    statusCounts.revoked > 0 ||
    (isLive && candidateCount === 0) ||
    (slot.effective_status === "active" &&
      candidateCount > 0 &&
      statusCounts.in_progress === 0 &&
      submittedCount === 0);

  return {
    assessmentId: assessment.id,
    assessmentTitle: assessment.title,
    assessmentStatus: assessment.status,
    questionCount: assessment.question_count,
    slotId: slot.id,
    slotTitle: slot.title,
    slotStatus: slot.status,
    effectiveStatus: slot.effective_status,
    startAt: slot.start_at,
    endAt: slot.end_at,
    candidateCount,
    statusCounts,
    submittedCount,
    isLive,
    needsAttention,
    startsSoon,
  };
}

function sessionRank(session: SessionRow) {
  if (session.needsAttention) {
    return 0;
  }

  if (session.isLive) {
    return 1;
  }

  if (session.startsSoon) {
    return 2;
  }

  return 3;
}

function buildSessionNote(session: SessionRow) {
  if (session.statusCounts.revoked > 0) {
    return "A revoked attempt needs a quick recruiter review.";
  }

  if (session.isLive && session.candidateCount === 0) {
    return "This test is live, but candidates have not been added yet.";
  }

  if (session.isLive && session.statusCounts.in_progress > 0) {
    return `${pluralize(session.statusCounts.in_progress, "candidate")} working right now.`;
  }

  if (session.isLive && session.submittedCount > 0) {
    return `${pluralize(session.submittedCount, "submission")} already received.`;
  }

  if (session.isLive) {
    return "This test is live and waiting for candidate activity.";
  }

  if (session.effectiveStatus === "paused") {
    return "Candidate activity is paused until the test is continued.";
  }

  if (session.effectiveStatus === "closed") {
    return session.submittedCount
      ? `${pluralize(session.submittedCount, "submission")} ready for review.`
      : "This test is closed with no submissions.";
  }

  if (session.effectiveStatus === "draft") {
    return "Finish the schedule and candidate setup before publishing.";
  }

  if (session.slotStatus === "scheduled" && session.candidateCount > 0) {
    return `${pluralize(session.candidateCount, "candidate")} assigned for this upcoming test.`;
  }

  return "Scheduled and ready for the next candidate batch.";
}

function buildTimingLabel(session: SessionRow) {
  if (session.effectiveStatus === "active") {
    return "Live now";
  }
  if (session.effectiveStatus === "paused") {
    return "Paused";
  }
  if (session.effectiveStatus === "closed") {
    return "Closed";
  }
  if (session.effectiveStatus === "draft") {
    return "Draft schedule";
  }

  const minutesUntilStart = Math.max(
    0,
    Math.ceil((new Date(session.startAt).getTime() - Date.now()) / 60_000),
  );
  if (minutesUntilStart < 60) {
    return `Starts in ${minutesUntilStart} min`;
  }
  if (minutesUntilStart < 1_440) {
    return `Starts in ${Math.ceil(minutesUntilStart / 60)} hr`;
  }
  return `Starts in ${Math.ceil(minutesUntilStart / 1_440)} days`;
}

function completionPercentage(session: SessionRow) {
  return session.candidateCount
    ? Math.round((session.submittedCount / session.candidateCount) * 100)
    : 0;
}

export function RecruitersPage() {
  const { currentUser } = useAuth();

  const assessmentsQuery = useAssessments(currentUser);
  const assessments = useMemo(
    () => assessmentsQuery.data?.items ?? [],
    [assessmentsQuery.data?.items],
  );
  const assessmentQueryKey = useMemo(
    () =>
      assessments
        .map((assessment) => `${assessment.id}:${assessment.updated_at}`)
        .join("|"),
    [assessments],
  );

  const activityQuery = useQuery<AssessmentActivityBundle[]>({
    queryKey: [
      "recruiter-dashboard-activity",
      currentUser?.uid,
      assessmentQueryKey,
    ],
    enabled: Boolean(currentUser && assessmentsQuery.data),
    queryFn: async () => {
      if (!currentUser) {
        return [];
      }

      const idToken = await currentUser.getIdToken();

      return Promise.all(
        assessments.map(async (assessment) => {
          const slotResponse = await fetchAssessmentSlots(idToken, assessment.id);

          const sessions = await Promise.all(
            slotResponse.items.map(async (slot) => {
              if (slot.candidate_count === 0) {
                return { slot, monitoring: [] };
              }

              const monitoring = await fetchSlotMonitoring(idToken, slot.id);
              return {
                slot,
                monitoring: monitoring.items,
              };
            }),
          );

          return {
            assessmentId: assessment.id,
            sessions,
          };
        }),
      );
    },
    staleTime: 30_000,
  });

  const sessionRows = useMemo(() => {
    const activityMap = new Map(
      (activityQuery.data ?? []).map((entry) => [entry.assessmentId, entry]),
    );

    return assessments
      .flatMap((assessment) => {
        const bundle = activityMap.get(assessment.id);
        return (bundle?.sessions ?? []).map(({ slot, monitoring }) =>
          buildSessionRow(assessment, slot, monitoring),
        );
      })
      .sort((left, right) => {
        const rankGap = sessionRank(left) - sessionRank(right);
        if (rankGap !== 0) {
          return rankGap;
        }

        if (sessionRank(left) < 3) {
          return new Date(left.startAt).getTime() - new Date(right.startAt).getTime();
        }
        return new Date(right.startAt).getTime() - new Date(left.startAt).getTime();
      });
  }, [activityQuery.data, assessments]);

  const recentSessions = sessionRows.slice(0, 5);
  const liveSessionCount = sessionRows.filter((session) => session.isLive).length;
  const upcomingSessionCount = sessionRows.filter(
    (session) => session.effectiveStatus === "scheduled",
  ).length;
  const attentionSessionCount = sessionRows.filter(
    (session) => session.needsAttention,
  ).length;

  return (
    <main className="recruiter-dashboard dashboard-classic">
      <div className="dashboard-shell">
        <section
          className="recruiter-welcome-banner workspace-page-header"
          aria-label="Recruiter dashboard header"
        >
          <div className="dashboard-welcome-copy">
            <p className="dashboard-eyebrow workspace-page-eyebrow">Recruiter Dashboard</p>
            <h1 className="workspace-page-title">
              Welcome back, {currentUser?.displayName || currentUser?.email?.split("@")[0] || "Recruiter"}!
            </h1>
          </div>
          <div className="dashboard-welcome-side">
            <div className="dashboard-welcome-stats" aria-label="Test slot summary">
              <span className="is-live"><strong>{liveSessionCount}</strong> Live</span>
              <span className="is-upcoming"><strong>{upcomingSessionCount}</strong> Upcoming</span>
              <span className="is-attention"><strong>{attentionSessionCount}</strong> Attention</span>
            </div>
          </div>
        </section>

        <section className="dashboard-classic-layout">
          <section className="dashboard-panel dashboard-test-slots-panel">
            <div className="dashboard-section-heading dashboard-classic-heading">
              <div>
                <p className="dashboard-eyebrow">Recent</p>
                <h2>Recent test slots</h2>
              </div>
              <div className="dashboard-classic-metrics" aria-label="Recent test slot totals">
                <span>
                  <strong>{sessionRows.length}</strong>
                  Total test slots
                </span>
                <span className="is-live">
                  <strong>{liveSessionCount}</strong>
                  Live now
                </span>
                <span className="is-attention">
                  <strong>{attentionSessionCount}</strong>
                  Need review
                </span>
              </div>
            </div>

            {activityQuery.isError ? (
              <p className="empty-state">Unable to load candidate attempts.</p>
            ) : null}

            <DataTable
              rows={recentSessions}
              isLoading={activityQuery.isPending}
              getRowKey={(session) => session.slotId}
              emptyState={
                <EmptyState
                  title="No recent test slots"
                  description="Create an assessment and schedule a test slot to see recent activity here."
                />
              }
              columns={[
                {
                  header: "Test",
                  key: "assessment",
                  render: (session) => (
                    <div className="table-primary-cell">
                      <Link
                        className="entity-link"
                        to={assessmentTestPath(
                          session.assessmentId,
                          session.slotId,
                          session.assessmentTitle,
                          session.slotTitle,
                        )}
                      >
                        {session.slotTitle}
                      </Link>
                      <Link
                        className="entity-secondary-link"
                        to={assessmentPath(session.assessmentId, session.assessmentTitle)}
                      >
                        {session.assessmentTitle} -{" "}
                        {formatStatusLabel(session.assessmentStatus)}
                      </Link>
                    </div>
                  ),
                },
                {
                  header: "Schedule",
                  key: "window",
                  render: (session) => (
                    <div className="table-primary-cell">
                      <strong>{buildTimingLabel(session)}</strong>
                      <span>{formatDateTime(session.startAt)}</span>
                      <span>Closes {formatDateTime(session.endAt)}</span>
                    </div>
                  ),
                },
                {
                  header: "Completion",
                  key: "candidates",
                  render: (session) => {
                    const completion = completionPercentage(session);
                    return (
                      <div className="dashboard-slot-completion">
                        <div>
                          <strong>{session.submittedCount}/{session.candidateCount}</strong>
                          <span>{completion}% submitted</span>
                        </div>
                        <span className="dashboard-slot-progress" aria-hidden="true">
                          <i style={{ width: `${completion}%` }} />
                        </span>
                      </div>
                    );
                  },
                },
                {
                  header: "Status",
                  key: "status",
                  render: (session) => (
                    <div className="dashboard-tag-stack">
                      {session.isLive ? <span className="pulse-indicator" title="Live Now" /> : null}
                      <StatusBadge
                        value={session.effectiveStatus}
                      />
                      {session.needsAttention ? (
                        <span className="dashboard-attention-label">
                          <AlertTriangle size={13} aria-hidden="true" />
                          Needs attention
                        </span>
                      ) : null}
                    </div>
                  ),
                },
                {
                  header: "Recruiter note",
                  key: "note",
                  render: (session) => (
                    <p className="dashboard-table-note">{buildSessionNote(session)}</p>
                  ),
                },
              ]}
            />
          </section>
        </section>
      </div>
    </main>
  );
}
