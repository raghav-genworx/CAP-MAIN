import {
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  Users,
} from "lucide-react";

import { MetricStrip } from "../../../components/common/MetricStrip";
import type {
  CandidateAssessmentStatus,
  SlotStatus,
} from "../../assessments";

type CandidateStatusCounts = Record<CandidateAssessmentStatus, number>;

export interface DashboardAnalyticsSession {
  assessmentId: string;
  candidateCount: number;
  effectiveStatus: SlotStatus;
  needsAttention: boolean;
  slotId: string;
  slotTitle: string;
  statusCounts: CandidateStatusCounts;
  submittedCount: number;
}

interface RecruiterDashboardAnalyticsProps {
  assessmentCount: number;
  sessions: DashboardAnalyticsSession[];
}

function percentage(value: number, total: number) {
  return total > 0
    ? Math.min(100, Math.max(0, Math.round((value / total) * 100)))
    : 0;
}

export function RecruiterDashboardAnalytics({
  assessmentCount,
  sessions,
}: RecruiterDashboardAnalyticsProps) {
  const candidateCount = sessions.reduce(
    (total, session) => total + session.candidateCount,
    0,
  );
  const submittedCount = Math.min(
    candidateCount,
    sessions.reduce(
      (total, session) => total + session.submittedCount,
      0,
    ),
  );
  const completionRate = percentage(submittedCount, candidateCount);
  return (
    <section className="dashboard-analytics" aria-label="Dashboard analytics">
      <MetricStrip
        items={[
          {
            icon: <ClipboardList size={18} aria-hidden="true" />,
            label: "Assessments",
            value: assessmentCount,
          },
          {
            icon: <CalendarClock size={18} aria-hidden="true" />,
            label: "Test slots",
            value: sessions.length,
          },
          {
            icon: <Users size={18} aria-hidden="true" />,
            label: "Candidates",
            value: candidateCount,
          },
          {
            icon: <CheckCircle2 size={18} aria-hidden="true" />,
            label: "Completion",
            value: `${completionRate}%`,
          },
        ]}
      />
    </section>
  );
}

export function DashboardCompletionByTest({
  isLoading,
  sessions,
}: {
  isLoading: boolean;
  sessions: DashboardAnalyticsSession[];
}) {
  const completionSessions = [...sessions]
    .sort((left, right) => right.candidateCount - left.candidateCount)
    .slice(0, 6);

  return (
    <section className="dashboard-analytics-grid dashboard-completion-section">
      <section className="dashboard-analytics-panel">
        <div className="dashboard-analytics-heading">
          <div>
            <p className="dashboard-eyebrow">Completion by test</p>
            <h2>Candidate submissions</h2>
          </div>
        </div>

        {isLoading ? (
          <p className="empty-state">Loading test completion...</p>
        ) : completionSessions.length ? (
          <div className="dashboard-completion-chart">
            {completionSessions.map((session) => {
              const rate = percentage(
                session.submittedCount,
                session.candidateCount,
              );
              return (
                <div className="dashboard-completion-row" key={session.slotId}>
                  <div>
                    <strong title={session.slotTitle}>{session.slotTitle}</strong>
                    <span>{session.submittedCount}/{session.candidateCount}</span>
                  </div>
                  <div className="dashboard-completion-track" aria-label={`${rate}% complete`}>
                    <i style={{ width: `${rate}%` }} />
                  </div>
                  <b>{rate}%</b>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="empty-state">No test slots are available in this view.</p>
        )}
      </section>
    </section>
  );
}
