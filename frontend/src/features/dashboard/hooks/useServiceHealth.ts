import { useQuery } from "@tanstack/react-query";

import {
  fetchCodeExecutionHealth,
  fetchCoreHealth,
} from "../../../services/healthService";

export function useServiceHealth() {
  return useQuery({
    queryKey: ["service-health"],
    queryFn: async () => {
      const [core, execution] = await Promise.all([
        fetchCoreHealth(),
        fetchCodeExecutionHealth(),
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
  });
}
