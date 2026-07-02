import { DataTable } from "../../../components/common/DataTable";
import { EmptyState } from "../../../components/common/EmptyState";
import { PageHeader } from "../../../components/common/PageHeader";
import { StatusBadge } from "../../../components/common/StatusBadge";
import { useCandidates } from "../hooks/useCandidates";

const MOCK_CANDIDATES = [
  {
    assessment: "Frontend Engineer Coding Round",
    email: "anika.rao@example.com",
    id: "mock-1",
    name: "Anika Rao",
    status: "in_progress",
  },
  {
    assessment: "Backend Problem Solving",
    email: "rahul.mehta@example.com",
    id: "mock-2",
    name: "Rahul Mehta",
    status: "submitted",
  },
  {
    assessment: "Data Structures Screen",
    email: "maya.chen@example.com",
    id: "mock-3",
    name: "Maya Chen",
    status: "scheduled",
  },
];

export function CandidatesPage() {
  const candidatesQuery = useCandidates();
  const candidates = candidatesQuery.data?.length
    ? candidatesQuery.data.map((candidate) => ({
        ...candidate,
        assessment: "Assigned assessment",
        status: "active",
      }))
    : MOCK_CANDIDATES;

  return (
    <section className="ops-page">
      <PageHeader
        title="Candidates"
        description="Candidate invitations, test state, and submission progress."
      />
      <DataTable
        rows={candidates}
        getRowKey={(row) => row.id}
        isLoading={candidatesQuery.isPending}
        emptyState={
          <EmptyState
            title="No candidates yet"
            description="Imported candidates and invited users will appear here."
          />
        }
        columns={[
          {
            header: "Candidate",
            key: "candidate",
            render: (row) => (
              <div className="table-primary-cell">
                <strong>{row.name}</strong>
                <span>{row.email}</span>
              </div>
            ),
          },
          {
            header: "Assessment",
            key: "assessment",
            render: (row) => row.assessment,
          },
          {
            header: "Status",
            key: "status",
            render: (row) => <StatusBadge value={row.status} />,
          },
        ]}
      />
    </section>
  );
}
