import { Card } from "../../../components/ui/Card";
import type { Recruiter } from "../types/Recruiter";

interface RecruiterListProps {
  recruiters: Recruiter[];
}

export function RecruiterList({ recruiters }: RecruiterListProps) {
  return (
    <div className="service-grid">
      {recruiters.map((recruiter) => (
        <Card key={recruiter.id}>
          <h2>{recruiter.name}</h2>
          <p>{recruiter.company}</p>
        </Card>
      ))}
    </div>
  );
}
