interface EnvConfig {
  coreApiBaseUrl: string;
  codeExecutionApiBaseUrl: string;
  codeEvaluationApiBaseUrl: string;
  firebaseApiKey?: string;
  firebaseAuthDomain?: string;
  firebaseProjectId?: string;
  firebaseAppId?: string;
}

function readEnvValue(key: keyof ImportMetaEnv, fallback: string): string {
  return import.meta.env[key] || fallback;
}

export const env: EnvConfig = {
  coreApiBaseUrl: readEnvValue(
    "VITE_CORE_API_BASE_URL",
    "/api/core",
  ),
  codeExecutionApiBaseUrl: readEnvValue(
    "VITE_CODE_EXECUTION_API_BASE_URL",
    "/api/execution",
  ),
  codeEvaluationApiBaseUrl: readEnvValue(
    "VITE_CODE_EVALUATION_API_BASE_URL",
    "/api/evaluation",
  ),
  firebaseApiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  firebaseAuthDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  firebaseProjectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  firebaseAppId: import.meta.env.VITE_FIREBASE_APP_ID,
};
