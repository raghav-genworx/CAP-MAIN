import axios from "axios";

import { env } from "../config/env";

type ApiErrorBody = {
  detail?: unknown;
  trace_id?: unknown;
};

export class ApiError extends Error {
  readonly status: number | undefined;
  readonly traceId: string | undefined;

  constructor(
    message: string,
    options: {
      cause: unknown;
      status?: number;
      traceId?: string;
    },
  ) {
    super(message, { cause: options.cause });
    this.name = "ApiError";
    this.status = options.status;
    this.traceId = options.traceId;
  }
}

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object" || !("msg" in item)) {
          return null;
        }
        return typeof item.msg === "string" ? item.msg : null;
      })
      .filter((message): message is string => Boolean(message));
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }

  return fallback;
}

export const coreApiClient = axios.create({
  baseURL: env.coreApiBaseUrl,
  withCredentials: true,
});

export const codeExecutionApiClient = axios.create({
  baseURL: env.codeExecutionApiBaseUrl,
  withCredentials: true,
});

export const codeEvaluationApiClient = axios.create({
  baseURL: env.codeEvaluationApiBaseUrl,
  withCredentials: true,
});

for (const client of [
  coreApiClient,
  codeExecutionApiClient,
  codeEvaluationApiClient,
]) {
  client.interceptors.response.use(
    (response) => response,
    (error: unknown) => {
      if (!axios.isAxiosError(error)) {
        return Promise.reject(error);
      }

      const body = error.response?.data as ApiErrorBody | undefined;
      const responseRequestId = error.response?.headers["x-request-id"];
      const traceId =
        typeof body?.trace_id === "string"
          ? body.trace_id
          : typeof responseRequestId === "string"
            ? responseRequestId
            : undefined;

      return Promise.reject(
        new ApiError(errorMessage(body?.detail, error.message), {
          cause: error,
          status: error.response?.status,
          traceId,
        }),
      );
    },
  );
}
