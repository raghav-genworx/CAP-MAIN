import { coreApiClient } from "../../../lib/axios";
import type { Recruiter } from "../types/Recruiter";

export async function fetchRecruiters(): Promise<Recruiter[]> {
  const response = await coreApiClient.get<Recruiter[]>("/recruiters");
  return response.data;
}
