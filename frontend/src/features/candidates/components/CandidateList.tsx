import { Card } from "../../../components/ui/Card";
import type { Candidate } from "../types/Candidate";

interface CandidateListProps {
  candidates: Candidate[];
}

export function CandidateList({ candidates }: CandidateListProps) {
  return (
    <div className="service-grid">
      {candidates.map((candidate) => (
        <Card key={candidate.id}>
          <h2>{candidate.name}</h2>
          <p>{candidate.email}</p>
        </Card>
      ))}
    </div>
  );
}
