export interface ApiErrorResponse {
  detail: string;
}

export interface HealthResponse {
  service: string;
  environment: string;
  status: string;
  version: string;
}
