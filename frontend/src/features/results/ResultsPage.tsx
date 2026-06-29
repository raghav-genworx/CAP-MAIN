import { DataTable } from "../../components/common/DataTable";
import { EmptyState } from "../../components/common/EmptyState";
import { PageHeader } from "../../components/common/PageHeader";
import { StatusBadge } from "../../components/common/StatusBadge";

const MOCK_RESULTS = [
  {
    assessment: "Frontend Engineer Coding Round",
    candidate: "Anika Rao",
    score: "84%",
    status: "passed",
    submitted: "Today, 10:20 AM",
  },
  {
    assessment: "Backend Problem Solving",
    candidate: "Rahul Mehta",
    score: "Pending",
    status: "evaluating",
    submitted: "Yesterday, 6:45 PM",
  },
  {
    assessment: "Data Structures Screen",
    candidate: "Maya Chen",
    score: "52%",
    status: "failed",
    submitted: "Jun 18, 2:10 PM",
  },
];

export function ResultsPage() {
  return (
    <section className="ops-page">
      <PageHeader
        title="Results"
        description="Evaluation outcomes, scoring status, and recruiter review queue."
      />
      <DataTable
        rows={MOCK_RESULTS}
        getRowKey={(row) => `${row.assessment}-${row.candidate}`}
        emptyState={
          <EmptyState
            title="No results yet"
            description="Submitted assessments will appear here after evaluation begins."
          />
        }
        columns={[
          {
            header: "Assessment",
            key: "assessment",
            render: (row) => <strong>{row.assessment}</strong>,
          },
          {
            header: "Candidate",
            key: "candidate",
            render: (row) => row.candidate,
          },
          {
            header: "Score",
            key: "score",
            render: (row) => row.score,
          },
          {
            header: "Status",
            key: "status",
            render: (row) => <StatusBadge value={row.status} />,
          },
          {
            header: "Submitted",
            key: "submitted",
            render: (row) => row.submitted,
          },
        ]}
      />
    </section>
  );
}
