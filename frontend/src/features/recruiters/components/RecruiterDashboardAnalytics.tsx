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
