import type {
  Assessment,
  AssessmentQuestionRecord,
  AssessmentSlot,
  SlotCandidate,
} from "../../assessments";
import type {
  AssessmentEvaluationDashboard,
  CandidateEvaluationSummary,
  EvaluationJobResponse,
  QuestionEvaluationBreakdown,
} from "../types/EvaluationResult";

export interface EvaluationAssessmentOption {
  id: string;
  title: string;
  description: string;
  status: string;
  testCount: number;
  candidateCount: number;
  submittedCount: number;
  questions: AssessmentQuestionRecord[];
  slots: AssessmentSlot[];
}

export type EvaluationTest =
  | {
      id: string;
      type: "slot";
      title: string;
      status: string;
      candidateCount: number;
      submittedCount: number;
      startAt: string | null;
      endAt: string | null;
    }
  | {
      id: string;
      type: "question";
      title: string;
      status: string;
      candidateCount: number;
      submittedCount: number;
      averageScore: number;
    };

export function buildAssessmentOptions(
  assessments: Assessment[],
): EvaluationAssessmentOption[] {
  return assessments.map((assessment) => {
    const candidateCount = assessment.slots.reduce(
      (total, slot) => total + slot.candidate_count,
      0,
    );
    const submittedCount = assessment.slots.reduce(
      (total, slot) => total + slot.submitted_count,
      0,
    );
    return {
      id: assessment.id,
      title: assessment.title,
      description: assessment.description,
      status: assessment.status,
      testCount: assessment.test_count || assessment.slots.length,
      candidateCount,
      submittedCount,
      questions: assessment.questions,
      slots: assessment.slots,
    };
  });
}

export function buildTests(
  assessment: EvaluationAssessmentOption,
  slots: AssessmentSlot[],
  dashboard: AssessmentEvaluationDashboard,
): EvaluationTest[] {
  if (slots.length) {
    return slots.map((slot) => ({
      id: slot.id,
      type: "slot",
      title: slot.title,
      status: slot.effective_status || slot.status,
      candidateCount: slot.candidate_count,
      submittedCount: slot.submitted_count,
      startAt: slot.start_at,
      endAt: slot.end_at,
    }));
  }

  const questionMap = new Map<string, QuestionEvaluationBreakdown>();
  dashboard.leaderboard.forEach((candidate) => {
    candidate.question_breakdown.forEach((question) => {
      if (!questionMap.has(question.question_id)) {
        questionMap.set(question.question_id, question);
      }
    });
  });
  assessment.questions.forEach((question) => {
    if (!questionMap.has(question.question_id)) {
      questionMap.set(question.question_id, {
        question_id: question.question_id,
        question_title: question.title,
        language: "",
        submitted_code: "",
        passed_count: 0,
        total_count: 0,
        earned_points: 0,
        total_points: question.marks,
        score: 0,
        mandatory_failed: false,
        test_cases: [],
      });
    }
  });

  return Array.from(questionMap.values()).map((question) => {
    const candidates = dashboard.leaderboard.filter((candidate) =>
      candidate.question_breakdown.some(
        (candidateQuestion) => candidateQuestion.question_id === question.question_id,
      ),
    );
    return {
      id: question.question_id,
      type: "question",
      title: question.question_title,
      status: "evaluated",
      candidateCount: candidates.length,
      submittedCount: candidates.length,
      averageScore: averageQuestionScore(candidates, question.question_id),
    };
  });
}

export function buildCandidatesForTest(
  test: EvaluationTest | undefined,
  leaderboard: CandidateEvaluationSummary[],
  slotCandidates?: SlotCandidate[],
): CandidateEvaluationSummary[] {
  if (!test) {
    return leaderboard;
  }
  if (test.type === "question") {
    return leaderboard.filter((candidate) =>
      candidate.question_breakdown.some((question) => question.question_id === test.id),
    );
  }
  if (!slotCandidates) {
    return [];
  }
  const slotCandidateIds = new Set(
    slotCandidates.map((candidate) => candidate.candidate_assessment_id),
  );
  return leaderboard.filter((candidate) =>
    slotCandidateIds.has(candidate.candidate_assessment_id),
  );
}

export function buildPipelineItems(jobs: EvaluationJobResponse[]) {
  const completed = jobs.filter((job) => job.status === "completed").length;
  const failed = jobs.filter((job) => job.status === "failed").length;
  const pending = jobs.filter(
    (job) => job.status === "pending" || job.status === "processing",
  ).length;

  return [
    {
      label: "Final hidden execution",
      detail: `${completed} submissions have execution evidence`,
      state: completed ? "done" : "waiting",
    },
    {
      label: "Weighted score calculation",
      detail: "60% tests, 20% coding metrics, 20% AI quality",
      state: completed ? "done" : "waiting",
    },
    {
      label: "AI quality review",
      detail: "Approach, complexity, readability, and improvement areas",
      state: completed ? "done" : "waiting",
    },
    {
      label: "Ranking and reports",
      detail: failed ? `${failed} jobs need retry` : `${pending} jobs pending`,
      state: failed ? "warning" : completed ? "done" : "waiting",
    },
  ];
}

export function makeEmptyDashboard(
  assessment: EvaluationAssessmentOption,
): AssessmentEvaluationDashboard {
  return {
    overview: {
      assessment_id: assessment.id,
      title: assessment.title,
      total_candidates: assessment.candidateCount,
      completed_candidates: assessment.submittedCount,
      pending_jobs: assessment.submittedCount,
      failed_jobs: 0,
      average_score: 0,
      average_test_case_score: 0,
      average_coding_score: 0,
      average_ai_score: 0,
      pass_rate: 0,
      highest_score: 0,
      report_status: "pending",
      generated_at: new Date().toISOString(),
    },
    leaderboard: [],
    jobs: [],
  };
}

export function averageScore(candidates: CandidateEvaluationSummary[]) {
  return average(candidates.map((candidate) => candidate.scores.final_score));
}

export function averageRuntime(candidates: CandidateEvaluationSummary[]) {
  return average(
    candidates.map((candidate) => candidate.total_execution_time_ms).filter(Boolean),
  );
}

export function averageHiddenPassRate(candidates: CandidateEvaluationSummary[]) {
  return average(
    candidates.map((candidate) =>
      candidate.hidden_total ? (candidate.hidden_passed / candidate.hidden_total) * 100 : 0,
    ),
  );
}

export function averageQuestionScore(
  candidates: CandidateEvaluationSummary[],
  questionId: string,
) {
  return average(
    candidates
      .map(
        (candidate) =>
          candidate.question_breakdown.find(
            (question) => question.question_id === questionId,
          )?.score,
      )
      .filter((score): score is number => typeof score === "number"),
  );
}

export function buildQuestionAnalytics(candidates: CandidateEvaluationSummary[]) {
  const analytics = new Map<
    string,
    {
      questionId: string;
      title: string;
      candidateCount: number;
      scoreTotal: number;
      passedCases: number;
      totalCases: number;
    }
  >();

  candidates.forEach((candidate) => {
    candidate.question_breakdown.forEach((question) => {
      const row = analytics.get(question.question_id) ?? {
        questionId: question.question_id,
        title: question.question_title,
        candidateCount: 0,
        scoreTotal: 0,
        passedCases: 0,
        totalCases: 0,
      };
      row.candidateCount += 1;
      row.scoreTotal += question.score;
      row.passedCases += question.passed_count;
      row.totalCases += question.total_count;
      analytics.set(question.question_id, row);
    });
  });

  return Array.from(analytics.values()).map((row) => ({
    ...row,
    averageScore: row.candidateCount ? row.scoreTotal / row.candidateCount : 0,
    passRate: row.totalCases ? (row.passedCases / row.totalCases) * 100 : 0,
  }));
}

function average(values: number[]) {
  if (!values.length) {
    return 0;
  }
  return values.reduce((total, value) => total + value, 0) / values.length;
}
