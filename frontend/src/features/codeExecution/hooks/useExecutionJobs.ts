import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../../auth";
import { fetchExecutionJobs } from "../services/codeExecutionService";

export function useExecutionJobs() {
  const { currentUser } = useAuth();

  return useQuery({
    queryKey: ["execution-jobs", currentUser?.uid],
    queryFn: async () => {
      if (!currentUser) {
        throw new Error("Recruiter session is required");
      }
      return fetchExecutionJobs(await currentUser.getIdToken());
    },
    enabled: Boolean(currentUser),
  });
}
