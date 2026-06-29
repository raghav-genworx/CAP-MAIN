import { codeExecutionApiClient } from "../../../lib/axios";
import type { ExecutionJob } from "../types/ExecutionJob";

export async function fetchExecutionJobs(idToken: string): Promise<ExecutionJob[]> {
  const response = await codeExecutionApiClient.get<ExecutionJob[]>("/executions", {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  return response.data;
}
