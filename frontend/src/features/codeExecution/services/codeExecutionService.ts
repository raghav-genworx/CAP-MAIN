import { codeExecutionApiClient } from "../../../lib/axios";
import type { ExecutionJob } from "../types/ExecutionJob";

export async function fetchExecutionJobs(): Promise<ExecutionJob[]> {
  const response = await codeExecutionApiClient.get<ExecutionJob[]>("/executions");
  return response.data;
}
