import {
  codeEvaluationApiClient,
  codeExecutionApiClient,
  coreApiClient,
} from "../lib/axios";
import type { HealthResponse } from "../types/api";

export async function fetchCoreHealth(): Promise<HealthResponse> {
  const response = await coreApiClient.get<HealthResponse>("/health");
  return response.data;
}

export async function fetchCodeExecutionHealth(): Promise<HealthResponse> {
  const response = await codeExecutionApiClient.get<HealthResponse>("/health");
  return response.data;
}

export async function fetchCodeEvaluationHealth(): Promise<HealthResponse> {
  const response = await codeEvaluationApiClient.get<HealthResponse>("/health");
  return response.data;
}
