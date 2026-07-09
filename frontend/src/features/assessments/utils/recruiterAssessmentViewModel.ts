import type {
  Assessment,
  AssessmentCreatePayload,
  AssessmentQuestionAssignment,
} from "../types/Assessment";
import type { DifficultyLevel } from "../types/QuestionBank";

export interface ManualCandidateRow {
  row_id: string;
  name: string;
  email: string;
  external_id: string;
}

export const TIME_ZONE_OPTIONS = [
  { label: "India (GMT+05:30)", name: "Asia/Kolkata", fallbackOffset: 330 },
  { label: "GMT / UTC", name: "Etc/UTC", fallbackOffset: 0 },
  { label: "Singapore (GMT+08:00)", name: "Asia/Singapore", fallbackOffset: 480 },
  { label: "Dubai (GMT+04:00)", name: "Asia/Dubai", fallbackOffset: 240 },
  { label: "London local time", name: "Europe/London", fallbackOffset: 0 },
  { label: "New York local time", name: "America/New_York", fallbackOffset: -300 },
] as const;

const MINUTE_MS = 60_000;

export function addMinutesToLocalInput(value: string, minutes: number) {
  if (!value) {
    return "";
  }
  const [datePart, timePart] = value.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute] = timePart.split(":").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day, hour, minute + minutes));
  return shifted.toISOString().slice(0, 16);
}

export function compareLocalDateTimeInputs(left: string, right: string) {
  if (!left && !right) {
    return 0;
  }
  if (!left) {
    return -1;
  }
  if (!right) {
    return 1;
  }
  return left.localeCompare(right);
}

export function isLocalInputBefore(value: string, minimum: string) {
  return Boolean(value && minimum && compareLocalDateTimeInputs(value, minimum) < 0);
}

export function maxLocalDateTimeInput(left: string, right: string) {
  if (!left) {
    return right;
  }
  if (!right) {
    return left;
  }
  return compareLocalDateTimeInputs(left, right) >= 0 ? left : right;
}

export function clampLocalInputToMinimum(value: string, minimum: string) {
  if (!minimum) {
    return value;
  }
  return maxLocalDateTimeInput(value, minimum);
}

export function createDefaultSlotSchedule(
  timezoneName: string,
  offsetMinutes: number,
  durationMinutes: number,
  nowMs: number = Date.now(),
) {
  const start_at = nextAvailableTimeInput(timezoneName, offsetMinutes, nowMs);
  return {
    start_at,
    end_at: addMinutesToLocalInput(start_at, durationMinutes),
  };
}

export function minimumSlotEndInput(
  startAt: string,
  durationMinutes: number,
  timezoneName: string,
  offsetMinutes: number,
  nowMs: number = Date.now(),
) {
  const minimumStart = nextAvailableTimeInput(timezoneName, offsetMinutes, nowMs);
  const effectiveStart = clampLocalInputToMinimum(startAt, minimumStart) || minimumStart;
  return addMinutesToLocalInput(effectiveStart, durationMinutes);
}

export function splitLocalDateTimeInput(value: string) {
  if (!value) {
    return { date: "", time: "" };
  }
  const [date = "", time = ""] = value.split("T");
  return { date, time: time.slice(0, 5) };
}

export function formatSlotDateTimeLabel(value: string) {
  const { date, time } = splitLocalDateTimeInput(value);
  if (!date || !time) {
    return value;
  }
  const parsed = new Date(`${date}T${time}:00`);
  if (Number.isNaN(parsed.getTime())) {
    return `${date} ${time}`;
  }
  return parsed.toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function buildScheduleTimeOptions(
  selectedDate: string,
  minimum: string,
  minuteStep = 15,
) {
  const { date: minDate, time: minTime } = splitLocalDateTimeInput(minimum);
  const options: Array<{ value: string; label: string; disabled: boolean }> = [];

  for (let hour = 0; hour < 24; hour += 1) {
    for (let minute = 0; minute < 60; minute += minuteStep) {
      const value = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
      const candidate = selectedDate ? `${selectedDate}T${value}` : "";
      const disabled = Boolean(
        selectedDate &&
          minDate &&
          (selectedDate < minDate ||
            (selectedDate === minDate &&
              minTime &&
              compareLocalDateTimeInputs(candidate, minimum) < 0)),
      );
      options.push({
        value,
        label: value,
        disabled,
      });
    }
  }

  return options;
}

export function getSlotScheduleFieldErrors(
  form: {
    start_at: string;
    end_at: string;
    duration_minutes: number;
    timezone_name: string;
    timezone_offset_minutes: number;
  },
  nowMs: number = Date.now(),
) {
  const errors = {
    start_at: "",
    end_at: "",
    general: "",
  };

  if (!form.start_at) {
    errors.start_at = "Choose a start time.";
    return errors;
  }

  const minimumStart = nextAvailableTimeInput(
    form.timezone_name,
    form.timezone_offset_minutes,
    nowMs,
  );
  if (isLocalInputBefore(form.start_at, minimumStart)) {
    errors.start_at = `Pick ${formatSlotDateTimeLabel(minimumStart)} or later.`;
  }

  if (!form.end_at) {
    errors.end_at = "Choose an end time.";
    return errors;
  }

  const minimumEnd = minimumSlotEndInput(
    form.start_at,
    form.duration_minutes,
    form.timezone_name,
    form.timezone_offset_minutes,
    nowMs,
  );
  if (isLocalInputBefore(form.end_at, minimumEnd)) {
    errors.end_at = `End time must be at least ${form.duration_minutes} minutes after the start time.`;
  }

  try {
    const timezoneOffsetMinutes = timezoneOffsetMinutesForLocalDateTime(
      form.start_at || form.end_at,
      form.timezone_name,
      form.timezone_offset_minutes,
    );
    const startAt = toIsoDateTimeForTimezone(
      form.start_at,
      form.timezone_name,
      timezoneOffsetMinutes,
    );
    const endAt = toIsoDateTimeForTimezone(
      form.end_at,
      form.timezone_name,
      timezoneOffsetMinutes,
    );
    if (new Date(startAt).getTime() < nowMs) {
      errors.start_at = "Start time must be in the future.";
    }
    if (
      new Date(endAt).getTime() <
      new Date(startAt).getTime() + form.duration_minutes * MINUTE_MS
    ) {
      errors.end_at = `End time must be at least ${form.duration_minutes} minutes after the start time.`;
    }
  } catch (error) {
    const message = errorMessage(error) || "Choose a valid start and end time.";
    if (!errors.start_at) {
      errors.start_at = message;
    } else {
      errors.general = message;
    }
  }

  return errors;
}

export function nextAvailableTimeInput(
  timezoneName: string,
  offsetMinutes: number,
  nowMs: number = Date.now(),
) {
  const nextMinute = new Date(Math.ceil(nowMs / MINUTE_MS) * MINUTE_MS);
  return toTimezoneInputValue(nextMinute.toISOString(), timezoneName, offsetMinutes);
}

export function buildCandidateCsv(rows: ManualCandidateRow[]) {
  const body = rows
    .filter((row) => row.name.trim() || row.email.trim() || row.external_id.trim())
    .map((row) =>
      [row.name, row.email, row.external_id].map((value) => csvEscape(value)).join(","),
    );
  return ["name,email,external_id", ...body].join("\n");
}

export function toIsoDateTimeForTimezone(
  value: string,
  timezoneName: string,
  fallbackOffsetMinutes: number,
) {
  if (!value) {
    return value;
  }
  const localTimestamp = localDateTimeAsUtc(value);
  const initialOffset = timezoneOffsetAtInstant(
    timezoneName,
    new Date(localTimestamp),
    fallbackOffsetMinutes,
  );
  let instant = new Date(localTimestamp - initialOffset * MINUTE_MS);
  const refinedOffset = timezoneOffsetAtInstant(
    timezoneName,
    instant,
    fallbackOffsetMinutes,
  );
  if (refinedOffset !== initialOffset) {
    instant = new Date(localTimestamp - refinedOffset * MINUTE_MS);
  }
  const isoValue = instant.toISOString();
  try {
    const roundTrip = toTimezoneInputValue(
      isoValue,
      timezoneName,
      fallbackOffsetMinutes,
    );
    if (roundTrip !== value.slice(0, 16)) {
      throw new Error(
        `${value.slice(11, 16)} does not exist in ${timezoneName} because of a daylight-saving transition. Choose another time.`,
      );
    }
  } catch (error) {
    if (!(error instanceof RangeError)) {
      throw error;
    }
  }
  return isoValue;
}

export function toTimezoneInputValue(
  value: string,
  timezoneName: string,
  fallbackOffsetMinutes: number,
) {
  if (!value) {
    return value;
  }
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) {
    return "";
  }
  try {
    const parts = dateTimeParts(timezoneName, instant);
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  } catch {
    const shifted = new Date(instant.getTime() + fallbackOffsetMinutes * MINUTE_MS);
    return shifted.toISOString().slice(0, 16);
  }
}

export function timezoneOffsetMinutesForLocalDateTime(
  value: string,
  timezoneName: string,
  fallbackOffsetMinutes: number,
) {
  if (!value) {
    return fallbackOffsetMinutes;
  }
  const instant = new Date(
    toIsoDateTimeForTimezone(value, timezoneName, fallbackOffsetMinutes),
  );
  return timezoneOffsetAtInstant(timezoneName, instant, fallbackOffsetMinutes);
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "Not set";
  }
  return new Date(value).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatDuration(seconds: number | null) {
  if (seconds === null) {
    return "Not started";
  }
  const safeSeconds = Math.max(0, seconds);
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = safeSeconds % 60;
  return `${minutes}m ${String(remainder).padStart(2, "0")}s`;
}

export function formatCountdown(seconds: number) {
  const safeSeconds = Math.max(0, seconds);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const remainder = safeSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${String(minutes).padStart(2, "0")}m ${String(remainder).padStart(2, "0")}s`;
  }
  return `${minutes}m ${String(remainder).padStart(2, "0")}s`;
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "";
}

export function createEmptyAssessment(): AssessmentCreatePayload {
  return {
    title: "",
    description: "",
    instructions: "",
    duration_minutes: 60,
    passing_score: 40,
    test_case_score_weight: 60,
    coding_score_weight: 20,
    ai_score_weight: 20,
    allow_resume: true,
    shuffle_questions: false,
    question_count_per_candidate: 4,
    difficulty_blueprint: createQuestionBlueprint(4),
    show_score_to_candidate: false,
    proctoring_mode: "basic",
    hidden_feedback_mode: "summary",
    max_hidden_checks: 0,
    hidden_check_cooldown_seconds: 5,
    supported_languages: ["python", "java", "cpp", "c"],
    status: "available",
  };
}

export function assessmentToPayload(assessment: Assessment): AssessmentCreatePayload {
  return {
    title: assessment.title,
    description: assessment.description,
    instructions: assessment.instructions,
    duration_minutes: assessment.duration_minutes,
    passing_score: assessment.passing_score,
    test_case_score_weight: assessment.test_case_score_weight,
    coding_score_weight: assessment.coding_score_weight,
    ai_score_weight: assessment.ai_score_weight,
    allow_resume: assessment.allow_resume,
    shuffle_questions: assessment.shuffle_questions,
    question_count_per_candidate: assessment.question_count_per_candidate,
    difficulty_blueprint: assessment.difficulty_blueprint?.length
      ? assessment.difficulty_blueprint
      : createQuestionBlueprint(assessment.question_count_per_candidate || 1),
    show_score_to_candidate: assessment.show_score_to_candidate,
    proctoring_mode: assessment.proctoring_mode,
    hidden_feedback_mode: "summary",
    max_hidden_checks: 0,
    hidden_check_cooldown_seconds: 5,
    supported_languages: assessment.supported_languages,
    status: assessment.status,
  };
}

export function statusTone(status: string) {
  if (["live", "sent", "submitted", "auto_submitted", "active", "passed"].includes(status)) {
    return "success";
  }
  if (["failed", "revoked", "closed", "archived"].includes(status)) {
    return "danger";
  }
  if (["in_progress", "scheduled", "available", "pending", "paused"].includes(status)) {
    return "warning";
  }
  return "neutral";
}

export function createQuestionBlueprint(count: number) {
  return Array.from({ length: Math.max(1, count) }, (_, index) =>
    index === 0 ? "easy" : index === 1 ? "hard" : "medium",
  ) as DifficultyLevel[];
}

export function calculateQuestionTemplateMarks(blueprint: DifficultyLevel[]) {
  const ratios = blueprint.map((difficulty) => difficultyRatio(difficulty));
  const totalRatio = ratios.reduce((sum, ratio) => sum + ratio, 0) || 1;
  const rawMarks = ratios.map((ratio) => (ratio / totalRatio) * 100);
  const marks = rawMarks.map((mark) => Math.floor(mark));
  const remainder = 100 - marks.reduce((sum, mark) => sum + mark, 0);
  rawMarks
    .map((mark, index) => ({ index, remainder: mark - marks[index] }))
    .sort((left, right) => right.remainder - left.remainder)
    .slice(0, remainder)
    .forEach(({ index }) => {
      marks[index] += 1;
    });
  return marks;
}

export function marksSummaryForDifficulty(
  difficulty: DifficultyLevel,
  blueprint: DifficultyLevel[],
  marks: number[],
) {
  const values = blueprint.flatMap((item, index) =>
    item === difficulty ? [marks[index] ?? 0] : [],
  );
  if (!values.length) {
    return "";
  }
  const unique = Array.from(new Set(values));
  if (unique.length === 1) {
    return `${unique[0]} marks each`;
  }
  return `${Math.min(...unique)}-${Math.max(...unique)} marks`;
}

export function buildAssessmentQuestionAssignments(
  questionIds: string[],
  questionById: Map<string, { difficulty: string }>,
): AssessmentQuestionAssignment[] {
  const marks = calculateQuestionTemplateMarks(
    questionIds.map(
      (questionId) =>
        (questionById.get(questionId)?.difficulty || "medium") as DifficultyLevel,
    ),
  );
  return questionIds.map((questionId, index) => ({
    question_id: questionId,
    question_order: index + 1,
    marks: marks[index],
    is_mandatory: true,
  }));
}

export function reorderQuestionIds(
  questionIds: string[],
  fromIndex: number,
  toIndex: number,
) {
  if (
    fromIndex < 0 ||
    fromIndex >= questionIds.length ||
    toIndex < 0 ||
    toIndex >= questionIds.length
  ) {
    return [...questionIds];
  }
  const next = [...questionIds];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
}

function csvEscape(value: string) {
  const trimmed = value.trim();
  if (!/[",\n\r]/.test(trimmed)) {
    return trimmed;
  }
  return `"${trimmed.replaceAll('"', '""')}"`;
}

function difficultyRatio(difficulty: string) {
  if (difficulty === "easy") {
    return 1;
  }
  if (difficulty === "hard") {
    return 3;
  }
  return 2;
}

function localDateTimeAsUtc(value: string) {
  const match =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(value);
  if (!match) {
    throw new Error("Date and time must use the expected local format.");
  }
  const [, year, month, day, hour, minute, second = "0"] = match;
  const timestamp = Date.UTC(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second),
  );
  const normalized = new Date(timestamp).toISOString().slice(0, 19);
  if (normalized !== `${year}-${month}-${day}T${hour}:${minute}:${second.padStart(2, "0")}`) {
    throw new Error("Date and time contain an invalid calendar value.");
  }
  return timestamp;
}

function timezoneOffsetAtInstant(
  timezoneName: string,
  instant: Date,
  fallbackOffsetMinutes: number,
) {
  try {
    const parts = dateTimeParts(timezoneName, instant);
    const representedAsUtc = Date.UTC(
      Number(parts.year),
      Number(parts.month) - 1,
      Number(parts.day),
      Number(parts.hour),
      Number(parts.minute),
      Number(parts.second),
    );
    return Math.round((representedAsUtc - instant.getTime()) / MINUTE_MS);
  } catch {
    return fallbackOffsetMinutes;
  }
}

function dateTimeParts(timezoneName: string, instant: Date) {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezoneName,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  const parts = Object.fromEntries(
    formatter
      .formatToParts(instant)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );
  return {
    year: parts.year,
    month: parts.month,
    day: parts.day,
    hour: parts.hour,
    minute: parts.minute,
    second: parts.second,
  };
}
