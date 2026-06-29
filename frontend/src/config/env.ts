interface EnvConfig {
  apiGatewayBaseUrl: string;
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

const apiGatewayBaseUrl = readEnvValue("VITE_API_GATEWAY_BASE_URL", "/api");

export const env: EnvConfig = {
  apiGatewayBaseUrl,
  coreApiBaseUrl: `${apiGatewayBaseUrl}/core`,
  codeExecutionApiBaseUrl: `${apiGatewayBaseUrl}/code-execution`,
  codeEvaluationApiBaseUrl: `${apiGatewayBaseUrl}/code-evaluation`,
  firebaseApiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  firebaseAuthDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  firebaseProjectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  firebaseAppId: import.meta.env.VITE_FIREBASE_APP_ID,
};
