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

const firebaseDefaults = {
  apiKey: "AIzaSyA1kA885hpNti9JJGAkRCwlUCLpFoli77k",
  authDomain: "book-search-vembarasu.firebaseapp.com",
  projectId: "book-search-vembarasu",
  appId: "1:220470398914:web:0c4065a667e1d51a00505b",
};

function readEnvValue(key: keyof ImportMetaEnv, fallback: string): string {
  return import.meta.env[key] || fallback;
}

const apiGatewayBaseUrl = readEnvValue("VITE_API_GATEWAY_BASE_URL", "/api");

export const env: EnvConfig = {
  apiGatewayBaseUrl,
  coreApiBaseUrl: `${apiGatewayBaseUrl}/core`,
  codeExecutionApiBaseUrl: `${apiGatewayBaseUrl}/code-execution`,
  codeEvaluationApiBaseUrl: `${apiGatewayBaseUrl}/code-evaluation`,
  firebaseApiKey: readEnvValue("VITE_FIREBASE_API_KEY", firebaseDefaults.apiKey),
  firebaseAuthDomain: readEnvValue(
    "VITE_FIREBASE_AUTH_DOMAIN",
    firebaseDefaults.authDomain,
  ),
  firebaseProjectId: readEnvValue(
    "VITE_FIREBASE_PROJECT_ID",
    firebaseDefaults.projectId,
  ),
  firebaseAppId: readEnvValue("VITE_FIREBASE_APP_ID", firebaseDefaults.appId),
};
