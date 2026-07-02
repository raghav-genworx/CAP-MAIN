import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { User } from "firebase/auth";

import {
  backfillAssessmentEvaluations,
  createAssessment,
  createAssessmentSlot,
  controlAssessmentSlot,
  deleteAssessment,
  fetchAssessments,
  fetchAssessmentSlots,
  fetchSlotCandidates,
  fetchSlotMonitoring,
  importSlotCandidates,
  resendCandidateInvite,
  sendSlotInvites,
  setAssessmentQuestions,
  updateAssessment,
  updateAssessmentSlot,
} from "../services/assessmentService";
import type {
  AssessmentCreatePayload,
  AssessmentQuestionsPayload,
  AssessmentSlotActionPayload,
  AssessmentSlotCreatePayload,
  AssessmentSlotUpdatePayload,
  CandidateImportPayload,
  EvaluationBackfillPayload,
  InviteDispatchPayload,
} from "../types/Assessment";

async function getRequiredIdToken(user: User | null): Promise<string> {
  if (!user) {
    throw new Error("Recruiter session is required");
  }
  return user.getIdToken();
}

export function useAssessments(user: User | null) {
  return useQuery({
    queryKey: ["assessments", user?.uid],
    queryFn: async () => fetchAssessments(await getRequiredIdToken(user)),
    enabled: Boolean(user),
  });
}

export function useCreateAssessment(user: User | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: AssessmentCreatePayload) =>
      createAssessment(await getRequiredIdToken(user), payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["assessments"] });
    },
  });
}

export function useUpdateAssessment(user: User | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      assessmentId,
      payload,
    }: {
      assessmentId: string;
      payload: Partial<AssessmentCreatePayload>;
    }) => updateAssessment(await getRequiredIdToken(user), assessmentId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["assessments"] });
    },
  });
}

export function useDeleteAssessment(user: User | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (assessmentId: string) =>
      deleteAssessment(await getRequiredIdToken(user), assessmentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["assessments"] });
      await queryClient.invalidateQueries({ queryKey: ["assessment-slots"] });
      await queryClient.invalidateQueries({ queryKey: ["slot-monitoring"] });
    },
  });
}

export function useSetAssessmentQuestions(user: User | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      assessmentId,
      payload,
    }: {
      assessmentId: string;
      payload: AssessmentQuestionsPayload;
    }) =>
      setAssessmentQuestions(await getRequiredIdToken(user), assessmentId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["assessments"] });
    },
  });
}

export function useAssessmentSlots(user: User | null, assessmentId: string | null) {
  return useQuery({
    queryKey: ["assessment-slots", user?.uid, assessmentId],
    queryFn: async () =>
      fetchAssessmentSlots(await getRequiredIdToken(user), assessmentId || ""),
    enabled: Boolean(user && assessmentId),
  });
}

export function useCreateAssessmentSlot(user: User | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      assessmentId,
      payload,
    }: {
      assessmentId: string;
      payload: AssessmentSlotCreatePayload;
    }) =>
      createAssessmentSlot(await getRequiredIdToken(user), assessmentId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["assessment-slots"] });
    },
  });
}

export function useUpdateAssessmentSlot(user: User | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      slotId,
      payload,
    }: {
      slotId: string;
      payload: AssessmentSlotUpdatePayload;
    }) => updateAssessmentSlot(await getRequiredIdToken(user), slotId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["assessment-slots"] });
      await queryClient.invalidateQueries({ queryKey: ["slot-monitoring"] });
    },
  });
}

export function useControlAssessmentSlot(user: User | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      slotId,
      payload,
    }: {
      slotId: string;
      payload: AssessmentSlotActionPayload;
    }) => controlAssessmentSlot(await getRequiredIdToken(user), slotId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["assessment-slots"] });
      await queryClient.invalidateQueries({ queryKey: ["slot-monitoring"] });
      await queryClient.invalidateQueries({ queryKey: ["slot-candidates"] });
    },
  });
}

export function useImportSlotCandidates(user: User | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      slotId,
      payload,
    }: {
      slotId: string;
      payload: CandidateImportPayload;
    }) => importSlotCandidates(await getRequiredIdToken(user), slotId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["slot-candidates"] });
      await queryClient.invalidateQueries({ queryKey: ["assessment-slots"] });
    },
  });
}

export function useSlotCandidates(user: User | null, slotId: string | null) {
  return useQuery({
    queryKey: ["slot-candidates", user?.uid, slotId],
    queryFn: async () =>
      fetchSlotCandidates(await getRequiredIdToken(user), slotId || ""),
    enabled: Boolean(user && slotId),
  });
}

export function useBackfillAssessmentEvaluations(user: User | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      assessmentId,
      payload = {},
    }: {
      assessmentId: string;
      payload?: EvaluationBackfillPayload;
    }) =>
      backfillAssessmentEvaluations(
        await getRequiredIdToken(user),
        assessmentId,
        payload,
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["assessments"] }),
        queryClient.invalidateQueries({ queryKey: ["assessment-slots"] }),
        queryClient.invalidateQueries({ queryKey: ["slot-candidates"] }),
        queryClient.invalidateQueries({ queryKey: ["code-evaluation-dashboard"] }),
      ]);
    },
  });
}

export function useSendSlotInvites(user: User | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      slotId,
      payload = {},
    }: {
      slotId: string;
      payload?: InviteDispatchPayload;
    }) => sendSlotInvites(await getRequiredIdToken(user), slotId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["slot-candidates"] });
    },
  });
}

export function useResendCandidateInvite(user: User | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (candidateAssessmentId: string) =>
      resendCandidateInvite(await getRequiredIdToken(user), candidateAssessmentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["slot-candidates"] });
    },
  });
}

export function useSlotMonitoring(user: User | null, slotId: string | null) {
  return useQuery({
    queryKey: ["slot-monitoring", user?.uid, slotId],
    queryFn: async () =>
      fetchSlotMonitoring(await getRequiredIdToken(user), slotId || ""),
    enabled: Boolean(user && slotId),
    refetchInterval: 15000,
  });
}
