import { coreApiClient } from "../../../lib/axios";
import type { Candidate } from "../types/Candidate";

export async function fetchCandidates(): Promise<Candidate[]> {
  const response = await coreApiClient.get<Candidate[]>("/candidates");
  return response.data;
}
