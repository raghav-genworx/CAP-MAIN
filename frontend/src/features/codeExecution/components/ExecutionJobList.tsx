import { Card } from "../../../components/ui/Card";
import type { ExecutionJob } from "../types/ExecutionJob";

interface ExecutionJobListProps {
  jobs: ExecutionJob[];
}

export function ExecutionJobList({ jobs }: ExecutionJobListProps) {
  return (
    <div className="service-grid">
      {jobs.map((job) => (
        <Card key={job.id}>
          <h2>{job.language}</h2>
          <p>{job.status}</p>
        </Card>
      ))}
    </div>
  );
}
