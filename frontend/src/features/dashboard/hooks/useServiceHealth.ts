import { useQuery } from "@tanstack/react-query";

import {
  fetchCodeExecutionHealth,
  fetchCoreHealth,
} from "../services/healthService";
import { useAuth } from "../../auth";

export function useServiceHealth() {
  const { currentUser } = useAuth();

  return useQuery({
    queryKey: ["service-health", currentUser?.uid],
    queryFn: async () => {
      if (!currentUser) {
        throw new Error("Recruiter session is required");
      }
      const idToken = await currentUser.getIdToken();
      const [core, execution] = await Promise.all([
        fetchCoreHealth(idToken),
        fetchCodeExecutionHealth(idToken),
      ]);

      return [
        { label: core.service, status: core.status, version: core.version },
        {
          label: execution.service,
          status: execution.status,
          version: execution.version,
        },
      ];
    },
    enabled: Boolean(currentUser),
  });
}
