import {
  codeEvaluationApiClient,
  codeExecutionApiClient,
  coreApiClient,
} from "../../../lib/axios";
import type { HealthResponse } from "../../../types/api";

function authHeader(idToken: string) {
  return { Authorization: `Bearer ${idToken}` };
}

export async function fetchCoreHealth(idToken: string): Promise<HealthResponse> {
  const response = await coreApiClient.get<HealthResponse>("/health", {
    headers: authHeader(idToken),
  });
  return response.data;
}

export async function fetchCodeExecutionHealth(
  idToken: string,
): Promise<HealthResponse> {
  const response = await codeExecutionApiClient.get<HealthResponse>("/health", {
    headers: authHeader(idToken),
  });
  return response.data;
}

export async function fetchCodeEvaluationHealth(
  idToken: string,
): Promise<HealthResponse> {
  const response = await codeEvaluationApiClient.get<HealthResponse>("/health", {
    headers: authHeader(idToken),
  });
  return response.data;
}
