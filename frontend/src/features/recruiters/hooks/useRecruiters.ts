import { useQuery } from "@tanstack/react-query";

import { fetchRecruiters } from "../services/recruiterService";

export function useRecruiters() {
  return useQuery({
    queryKey: ["recruiters"],
    queryFn: fetchRecruiters,
  });
}
