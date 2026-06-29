export interface ExecutionJob {
  id: string;
  language: string;
  status: "queued" | "running" | "completed" | "failed";
}
