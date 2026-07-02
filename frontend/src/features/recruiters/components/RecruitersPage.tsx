import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  FilePlus2,
  PlayCircle,
  Plus,
  Users,
} from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { DataTable } from "../../../components/common/DataTable";
import { EmptyState } from "../../../components/common/EmptyState";
import { MetricStrip } from "../../../components/common/MetricStrip";
import { StatusBadge } from "../../../components/common/StatusBadge";
import { Button } from "../../../components/ui/Button";
import { useAuth } from "../../auth";
import {
  useAssessments,
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

type SessionFilter = "all" | "active" | "upcoming";
type CandidateStatusCounts = Record<CandidateAssessmentStatus, number>;

interface AssessmentActivityBundle {
  assessmentId: string;
  sessions: Array<{
    slot: AssessmentSlot;
    monitoring: MonitoringCandidate[];
  }>;
}

interface SessionRow {
  assessmentTitle: string;
  assessmentStatus: AssessmentStatus;
  questionCount: number;
  slotId: string;
  slotTitle: string;
  slotStatus: SlotStatus;
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

  const submittedCount =
    statusCounts.submitted + statusCounts.auto_submitted;
  const candidateCount = Math.max(slot.candidate_count, monitoring.length);
  const isLive = slot.status === "active" || statusCounts.in_progress > 0;
  const startsAt = new Date(slot.start_at).getTime();
  const startsSoon =
    !isLive &&
    slot.status === "scheduled" &&
    startsAt >= now &&
    startsAt - now <= 1000 * 60 * 60 * 48;
  const needsAttention =
    statusCounts.revoked > 0 ||
    (isLive && candidateCount === 0) ||
    (slot.status === "active" &&
      candidateCount > 0 &&
      statusCounts.in_progress === 0 &&
      submittedCount === 0);

  return {
    assessmentTitle: assessment.title,
    assessmentStatus: assessment.status,
    questionCount: assessment.question_count,
    slotId: slot.id,
    slotTitle: slot.title,
    slotStatus: slot.status,
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

  if (session.slotStatus === "scheduled" && session.candidateCount > 0) {
    return `${pluralize(session.candidateCount, "candidate")} assigned for this upcoming test.`;
  }

  return "Scheduled and ready for the next candidate batch.";
}

function matchesSearch(session: SessionRow, search: string) {
  if (!search) {
    return true;
  }

  const haystack = [
    session.assessmentTitle,
    session.slotTitle,
    session.assessmentStatus,
    session.slotStatus,
  ]
    .join(" ")
    .toLowerCase();

  return haystack.includes(search);
}

export function RecruitersPage() {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const [search, setSearch] = useState("");
  const [sessionFilter, setSessionFilter] = useState<SessionFilter>("all");
  const deferredSearch = useDeferredValue(search);

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
      .filter((session) => session.isLive || session.slotStatus === "scheduled")
      .sort((left, right) => {
        const rankGap = sessionRank(left) - sessionRank(right);
        if (rankGap !== 0) {
          return rankGap;
        }

        return new Date(left.startAt).getTime() - new Date(right.startAt).getTime();
      });
  }, [activityQuery.data, assessments]);

  const normalizedSearch = deferredSearch.trim().toLowerCase();

  const visibleSessions = useMemo(
    () =>
      sessionRows.filter((session) => {
        if (sessionFilter === "active" && !session.isLive) {
          return false;
        }

        if (sessionFilter === "upcoming" && session.isLive) {
          return false;
        }

        return matchesSearch(session, normalizedSearch);
      }),
    [normalizedSearch, sessionFilter, sessionRows],
  );

  const liveCount = sessionRows.filter((session) => session.isLive).length;
  const upcomingCount = sessionRows.filter((session) => !session.isLive).length;
  const attentionCount = sessionRows.filter(
    (session) => session.needsAttention,
  ).length;
  const availableAssessments = assessments.filter(
    (assessment) => assessment.status === "available",
  ).length;
  const recentAssessments = assessments.slice(0, 6);

  return (
    <main className="recruiter-dashboard">
      <div className="dashboard-shell">
        <section className="dashboard-intro" aria-label="Recruiter dashboard header">
          <div className="dashboard-intro-copy">
            <p className="dashboard-eyebrow">Recruiter dashboard</p>
            <h1>Command center</h1>
          </div>

          <div className="dashboard-status-strip" aria-label="Important test status">
            <span className="dashboard-status-chip is-live">
              <strong>{liveCount}</strong> Active
            </span>
            <span className="dashboard-status-chip is-upcoming">
              <strong>{upcomingCount}</strong> Upcoming
            </span>
            <span className="dashboard-status-chip is-alert">
              <strong>{attentionCount}</strong> Attention
            </span>
          </div>
        </section>

        <MetricStrip
          items={[
            {
              icon: <ClipboardList size={18} aria-hidden="true" />,
              label: "Assessments",
              value: assessments.length,
            },
            {
              icon: <CheckCircle2 size={18} aria-hidden="true" />,
              label: "Available",
              value: availableAssessments,
            },
            {
              icon: <PlayCircle size={18} aria-hidden="true" />,
              label: "Active tests",
              value: liveCount,
            },
            {
              icon: <AlertTriangle size={18} aria-hidden="true" />,
              label: "Pending review",
              value: attentionCount,
            },
          ]}
        />

        <section className="dashboard-action-bar" aria-label="Quick actions">
          <Button type="button" onClick={() => navigate("/recruiter/assessments")}>
            <Plus size={16} aria-hidden="true" />
            Create assessment
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => navigate("/recruiter/question-management/new")}
          >
            <FilePlus2 size={16} aria-hidden="true" />
            Add question
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => navigate("/recruiter/assessments")}
          >
            <Users size={16} aria-hidden="true" />
            Candidate batches
          </Button>
        </section>

        <section className="dashboard-table-grid">
          <section className="dashboard-panel">
            <div className="dashboard-section-heading">
              <div>
                <p className="dashboard-eyebrow">Recent</p>
                <h2>Assessments</h2>
              </div>
            </div>
            <DataTable
              rows={recentAssessments}
              isLoading={assessmentsQuery.isPending}
              getRowKey={(assessment) => assessment.id}
              emptyState={
                <EmptyState
                  title="No assessments yet"
                  description="Create an assessment to start scheduling candidate tests."
                />
              }
              columns={[
                {
                  header: "Name",
                  key: "name",
                  render: (assessment) => <strong>{assessment.title}</strong>,
                },
                {
                  header: "Questions",
                  key: "questions",
                  render: (assessment) => assessment.question_count,
                },
                {
                  header: "Status",
                  key: "status",
                  render: (assessment) => <StatusBadge value={assessment.status} />,
                },
              ]}
            />
          </section>

          <section className="dashboard-panel">
            <div className="dashboard-section-heading">
              <div>
                <p className="dashboard-eyebrow">Attempts</p>
                <h2>Active and upcoming</h2>
              </div>
            </div>

            <div className="dashboard-filter-bar dashboard-filter-bar-compact">
              <label className="dashboard-filter-control">
                <span>Search</span>
                <input
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Assessment or test name"
                />
              </label>

              <label className="dashboard-filter-control">
                <span>Show</span>
                <select
                  value={sessionFilter}
                  onChange={(event) =>
                    setSessionFilter(event.target.value as SessionFilter)
                  }
                >
                  <option value="all">Active and upcoming</option>
                  <option value="active">Active only</option>
                  <option value="upcoming">Upcoming only</option>
                </select>
              </label>
            </div>

            {activityQuery.isError ? (
              <p className="empty-state">Unable to load candidate attempts.</p>
            ) : null}

            <DataTable
              rows={visibleSessions}
              isLoading={activityQuery.isPending}
              getRowKey={(session) => session.slotId}
              emptyState={
                <EmptyState
                  title="No tests in view"
                  description="Active and scheduled tests will appear here."
                />
              }
              columns={[
                {
                  header: "Assessment",
                  key: "assessment",
                  render: (session) => (
                    <div className="table-primary-cell">
                      <strong>{session.assessmentTitle}</strong>
                      <span>{formatStatusLabel(session.assessmentStatus)}</span>
                    </div>
                  ),
                },
                {
                  header: "Window",
                  key: "window",
                  render: (session) => (
                    <div className="table-primary-cell">
                      <strong>{formatDateTime(session.startAt)}</strong>
                      <span>Ends {formatDateTime(session.endAt)}</span>
                    </div>
                  ),
                },
                {
                  header: "Candidates",
                  key: "candidates",
                  render: (session) => session.candidateCount,
                },
                {
                  header: "Status",
                  key: "status",
                  render: (session) => (
                    <div className="dashboard-tag-stack">
                      <StatusBadge
                        value={session.isLive ? "active" : "scheduled"}
                      />
                      {session.needsAttention ? (
                        <StatusBadge value="evaluating" />
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
