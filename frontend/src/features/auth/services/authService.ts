import { coreApiClient } from "../../../lib/axios";

export type SubscriptionStatus = "pending" | "free_trial";

export interface RecruiterAccount {
  uid: string;
  email: string | null;
  name: string | null;
  picture: string | null;
  email_verified: boolean;
  role: "recruiter";
  subscription_status: SubscriptionStatus;
  trial_started_at: string | null;
}

function authHeader(idToken: string) {
  return { Authorization: `Bearer ${idToken}` };
}

export async function fetchRecruiterAccount(
  idToken: string,
): Promise<RecruiterAccount> {
  const response = await coreApiClient.get<RecruiterAccount>("/auth/me", {
    headers: authHeader(idToken),
  });
  return response.data;
}

export async function startFreeTrial(
  idToken: string,
): Promise<RecruiterAccount> {
  const response = await coreApiClient.post<RecruiterAccount>(
    "/auth/start-free-trial",
    undefined,
    { headers: authHeader(idToken) },
  );
  return response.data;
}
