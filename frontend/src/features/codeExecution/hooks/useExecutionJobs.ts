import { useQuery } from "@tanstack/react-query";

import { fetchExecutionJobs } from "../services/codeExecutionService";

export function useExecutionJobs() {
  return useQuery({
    queryKey: ["execution-jobs"],
    queryFn: fetchExecutionJobs,
  });
}
