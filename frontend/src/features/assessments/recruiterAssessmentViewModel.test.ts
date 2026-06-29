import { describe, expect, it } from "vitest";

import {
  buildAssessmentQuestionAssignments,
  buildCandidateCsv,
  createQuestionBlueprint,
  formatCountdown,
  reorderQuestionIds,
  timezoneOffsetMinutesForLocalDateTime,
  toIsoDateTimeForTimezone,
  toTimezoneInputValue,
  type ManualCandidateRow,
} from "./recruiterAssessmentViewModel";

function candidate(
  name: string,
  email: string,
  externalId = "",
): ManualCandidateRow {
  return {
    row_id: email,
    name,
    email,
    external_id: externalId,
  };
}

describe("recruiter assessment view model", () => {
  it("builds RFC-compatible candidate CSV and omits blank rows", () => {
    const csv = buildCandidateCsv([
      candidate('Ada "A" Lovelace', "ada@example.com", "ENG,1"),
      candidate("", ""),
    ]);

    expect(csv).toBe(
      'name,email,external_id\n"Ada ""A"" Lovelace",ada@example.com,"ENG,1"',
    );
  });

  it("converts London and New York local times with daylight saving", () => {
    expect(toIsoDateTimeForTimezone("2026-06-15T09:00", "Europe/London", 0)).toBe(
      "2026-06-15T08:00:00.000Z",
    );
    expect(toIsoDateTimeForTimezone("2026-12-15T09:00", "Europe/London", 0)).toBe(
      "2026-12-15T09:00:00.000Z",
    );
    expect(
      toIsoDateTimeForTimezone("2026-06-15T09:00", "America/New_York", -300),
    ).toBe("2026-06-15T13:00:00.000Z");
    expect(
      timezoneOffsetMinutesForLocalDateTime(
        "2026-06-15T09:00",
        "America/New_York",
        -300,
      ),
    ).toBe(-240);
  });

  it("rejects a nonexistent local time during the spring DST transition", () => {
    expect(() =>
      toIsoDateTimeForTimezone(
        "2026-03-08T02:30",
        "America/New_York",
        -300,
      ),
    ).toThrow("does not exist in America/New_York");
    expect(
      toIsoDateTimeForTimezone(
        "2026-11-01T01:30",
        "America/New_York",
        -300,
      ),
    ).toBe("2026-11-01T05:30:00.000Z");
  });

  it("round-trips scheduled instants and falls back for unknown zones", () => {
    const instant = toIsoDateTimeForTimezone(
      "2026-06-15T09:00",
      "Asia/Kolkata",
      330,
    );
    expect(instant).toBe("2026-06-15T03:30:00.000Z");
    expect(toTimezoneInputValue(instant, "Asia/Kolkata", 330)).toBe(
      "2026-06-15T09:00",
    );
    expect(toIsoDateTimeForTimezone("2026-06-15T09:00", "Invalid/Zone", 120)).toBe(
      "2026-06-15T07:00:00.000Z",
    );
    expect(() =>
      toIsoDateTimeForTimezone("2026-02-30T09:00", "Etc/UTC", 0),
    ).toThrow("invalid calendar value");
  });

  it("allocates exactly 100 marks by difficulty and preserves order", () => {
    const assignments = buildAssessmentQuestionAssignments(
      ["easy", "hard", "medium"],
      new Map([
        ["easy", { difficulty: "easy" }],
        ["hard", { difficulty: "hard" }],
        ["medium", { difficulty: "medium" }],
      ]),
    );

    expect(assignments.map((item) => item.marks)).toEqual([17, 50, 33]);
    expect(assignments.reduce((total, item) => total + item.marks, 0)).toBe(100);
    expect(assignments.map((item) => item.question_order)).toEqual([1, 2, 3]);
  });

  it("keeps question reordering immutable and guards invalid indexes", () => {
    const original = ["a", "b", "c"];
    expect(reorderQuestionIds(original, 0, 2)).toEqual(["b", "c", "a"]);
    expect(reorderQuestionIds(original, -1, 2)).toEqual(original);
    expect(original).toEqual(["a", "b", "c"]);
    expect(createQuestionBlueprint(4)).toEqual(["easy", "hard", "medium", "medium"]);
    expect(formatCountdown(3661)).toBe("1h 01m 01s");
  });
});
