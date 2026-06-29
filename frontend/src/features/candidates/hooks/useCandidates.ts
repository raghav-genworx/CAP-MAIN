import { useQuery } from "@tanstack/react-query";

import { fetchCandidates } from "../services/candidateService";

export function useCandidates() {
  return useQuery({
    queryKey: ["candidates"],
    queryFn: fetchCandidates,
  });
}
