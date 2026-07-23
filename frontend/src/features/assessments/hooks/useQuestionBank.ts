import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { User } from "firebase/auth";

import {
  bulkImportQuestionBankQuestions,
  deleteQuestionBankQuestion,
  createQuestionBankQuestion,
  generateQuestionBankDraft,
  refineQuestionBankSolution,
  refineQuestionBankTestCases,
  streamQuestionBankDraft,
  validateQuestionBankDraft,
  fetchQuestionBankQuestions,
  fetchQuestionGroups,
  createQuestionGroup,
  updateQuestionGroup,
  deleteQuestionGroup,
  updateQuestionBankQuestion,
} from "../services/questionBankService";
import type {
  DifficultyLevel,
  QuestionAIDraftRequest,
  QuestionAIDraftProgressEvent,
  QuestionBulkImportRequest,
  QuestionCreatePayload,
  QuestionDraftRefinementRequest,
  QuestionDraftValidationRequest,
  QuestionGroupCreatePayload,
  QuestionGroupStatus,
  QuestionGroupUpdatePayload,
  QuestionStatus,
  QuestionUpdatePayload,
} from "../types/QuestionBank";

export interface QuestionBankFilters {
  search: string;
  difficulty: DifficultyLevel | "";
  status: QuestionStatus | "";
  tag: string;
}

export interface QuestionGroupFilters {
  search: string;
  status: QuestionGroupStatus | "";
}

async function getRequiredIdToken(user: User | null): Promise<string> {
  if (!user) {
    throw new Error("Recruiter session is required");
  }

  return user.getIdToken();
}

export function useQuestionBank(
  user: User | null,
  filters: QuestionBankFilters,
) {
  return useQuery({
    queryKey: ["question-bank", user?.uid, filters],
    queryFn: async () =>
      fetchQuestionBankQuestions(await getRequiredIdToken(user), filters),
    enabled: Boolean(user),
  });
}

export function useCreateQuestionBankQuestion(user: User | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: QuestionCreatePayload) =>
      createQuestionBankQuestion(await getRequiredIdToken(user), payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["question-bank"] });
    },
  });
}

export function useBulkImportQuestionBankQuestions(user: User | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: QuestionBulkImportRequest) =>
      bulkImportQuestionBankQuestions(await getRequiredIdToken(user), payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["question-bank"] });
    },
  });
}

export function useUpdateQuestionBankQuestion(user: User | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      questionId,
      payload,
    }: {
      questionId: string;
      payload: QuestionUpdatePayload;
    }) => updateQuestionBankQuestion(await getRequiredIdToken(user), questionId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["question-bank"] });
    },
  });
}

export function useDeleteQuestionBankQuestion(user: User | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (questionId: string) =>
      deleteQuestionBankQuestion(await getRequiredIdToken(user), questionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["question-bank"] });
    },
  });
}

export function useGenerateQuestionBankDraft(user: User | null) {
  return useMutation({
    mutationFn: async (payload: QuestionAIDraftRequest) =>
      generateQuestionBankDraft(await getRequiredIdToken(user), payload),
  });
}

export function useStreamQuestionBankDraft(user: User | null) {
  return useMutation({
    mutationFn: async ({
      payload,
      onProgress,
      signal,
    }: {
      payload: QuestionAIDraftRequest;
      onProgress: (event: QuestionAIDraftProgressEvent) => void;
      signal?: AbortSignal;
    }) => streamQuestionBankDraft(await getRequiredIdToken(user), payload, onProgress, signal),
  });
}

export function useValidateQuestionBankDraft(user: User | null) {
  return useMutation({
    mutationFn: async (variables: QuestionDraftValidationRequest & { signal?: AbortSignal }) => {
      const { signal, ...payload } = variables;
      return validateQuestionBankDraft(await getRequiredIdToken(user), payload, signal);
    },
  });
}

export function useRefineQuestionBankTestCases(user: User | null) {
  return useMutation({
    mutationFn: async (variables: QuestionDraftRefinementRequest & { signal?: AbortSignal }) => {
      const { signal, ...payload } = variables;
      return refineQuestionBankTestCases(await getRequiredIdToken(user), payload, signal);
    },
  });
}

export function useRefineQuestionBankSolution(user: User | null) {
  return useMutation({
    mutationFn: async (variables: QuestionDraftRefinementRequest & { signal?: AbortSignal }) => {
      const { signal, ...payload } = variables;
      return refineQuestionBankSolution(await getRequiredIdToken(user), payload, signal);
    },
  });
}

export function useQuestionGroups(
  user: User | null,
  filters: QuestionGroupFilters,
) {
  return useQuery({
    queryKey: ["question-groups", user?.uid, filters],
    queryFn: async () =>
      fetchQuestionGroups(await getRequiredIdToken(user), filters),
    enabled: Boolean(user),
  });
}

export function useCreateQuestionGroup(user: User | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: QuestionGroupCreatePayload) =>
      createQuestionGroup(await getRequiredIdToken(user), payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["question-groups"] });
    },
  });
}

export function useUpdateQuestionGroup(user: User | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      groupId,
      payload,
    }: {
      groupId: string;
      payload: QuestionGroupUpdatePayload;
    }) => updateQuestionGroup(await getRequiredIdToken(user), groupId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["question-groups"] });
    },
  });
}

export function useDeleteQuestionGroup(user: User | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (groupId: string) =>
      deleteQuestionGroup(await getRequiredIdToken(user), groupId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["question-groups"] });
    },
  });
}
