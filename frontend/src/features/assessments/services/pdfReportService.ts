import jsPDF from "jspdf";
import type { Assessment, AssessmentSlot } from "../../assessments/types/Assessment";
import type {
  AssessmentEvaluationDashboard,
  CandidateEvaluationSummary,
} from "../../codeEvaluation/types/EvaluationResult";

/* ------------------------------------------------------------------ */
/*  Colour palette                                                     */
/* ------------------------------------------------------------------ */
const COLORS = {
  primary: [17, 24, 39] as [number, number, number],       // #111827
  accent: [99, 102, 241] as [number, number, number],      // #6366f1  indigo
  accentLight: [165, 180, 252] as [number, number, number], // #a5b4fc
  white: [255, 255, 255] as [number, number, number],
  text: [30, 41, 59] as [number, number, number],          // #1e293b
  textMuted: [100, 116, 139] as [number, number, number],  // #64748b
  border: [226, 232, 240] as [number, number, number],     // #e2e8f0
  bgLight: [248, 250, 252] as [number, number, number],    // #f8fafc
  success: [34, 197, 94] as [number, number, number],      // #22c55e
  warning: [245, 158, 11] as [number, number, number],     // #f59e0b
  danger: [239, 68, 68] as [number, number, number],       // #ef4444
  barScore: [99, 102, 241] as [number, number, number],    // indigo
  barParticipation: [59, 130, 246] as [number, number, number], // blue
  barDuration: [245, 158, 11] as [number, number, number], // amber
};

const PAGE_WIDTH = 210;
const PAGE_HEIGHT = 297;
const MARGIN = 20;
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2;

/* ------------------------------------------------------------------ */
/*  Shared types used inside the PDF builder                           */
/* ------------------------------------------------------------------ */
interface SlotAnalyticsPdf {
  id: string;
  title: string;
  status: string;
  startsAt: string;
  candidateCount: number;
  submittedCount: number;
  evaluatedCount: number;
  averageScore: number;
  topScore: number;
  passRate: number;
  submissionRate: number;
  evaluationRate: number;
  hiddenPassRate: number;
  averageCodingScore: number;
  averageAiScore: number;
  averageDurationSeconds: number | null;
  bands: { excellent: number; pass: number; review: number };
}

interface SlotCandidateLookup {
  [slotId: string]: { candidate_assessment_id: string; assessment_status: string }[];
}

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */

export function generateAssessmentAnalyticsPdf(
  assessment: Assessment,
  slots: AssessmentSlot[],
  dashboard: AssessmentEvaluationDashboard,
  slotCandidates: SlotCandidateLookup,
): void {
  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });

  const slotAnalytics = buildSlotAnalyticsPdf(
    assessment.passing_score,
    slots,
    slotCandidates,
    dashboard.leaderboard,
  );

  /* ---------- Page 1: Cover ---------- */
  drawCoverPage(doc, assessment, dashboard);

  /* ---------- Page 2+: Assessment Details & Questions ---------- */
  doc.addPage();
  let y = MARGIN;
  y = drawSectionHeading(doc, y, "Assessment Details");
  y = drawAssessmentDetails(doc, y, assessment);

  y += 10;
  y = ensureSpace(doc, y, 40);
  y = drawSectionHeading(doc, y, "Questions");
  y = drawQuestionsTable(doc, y, assessment);

  /* ---------- Analytics Overview ---------- */
  y += 10;
  y = ensureSpace(doc, y, 60);
  y = drawSectionHeading(doc, y, "Analytics Overview");
  y = drawAnalyticsOverview(doc, y, dashboard);

  /* ---------- Slot Performance Comparison ---------- */
  if (slotAnalytics.length > 0) {
    y += 10;
    y = ensureSpace(doc, y, 60);
    y = drawSectionHeading(doc, y, "Slot Performance Comparison");
    y = drawSlotComparisonTable(doc, y, slotAnalytics);

    /* ---------- Visual Charts ---------- */
    y += 10;
    y = ensureSpace(doc, y, 60);
    y = drawSectionHeading(doc, y, "Visual Comparisons");
    drawBarCharts(doc, y, slotAnalytics);
  }

  /* ---------- Footer on every page ---------- */
  addFooters(doc, assessment.title);

  /* ---------- Trigger Download ---------- */
  const safeTitle = assessment.title
    .replace(/[^a-zA-Z0-9_\- ]/g, "")
    .replace(/\s+/g, "_")
    .substring(0, 50);
  doc.save(`Assessment_${safeTitle}_Report.pdf`);
}

/* ================================================================== */
/*  Cover Page                                                         */
/* ================================================================== */

function drawCoverPage(
  doc: jsPDF,
  assessment: Assessment,
  dashboard: AssessmentEvaluationDashboard,
) {
  // Full-page dark background
  doc.setFillColor(...COLORS.primary);
  doc.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, "F");

  // Accent stripe at top
  doc.setFillColor(...COLORS.accent);
  doc.rect(0, 0, PAGE_WIDTH, 6, "F");

  // Title area
  doc.setTextColor(...COLORS.white);
  doc.setFontSize(14);
  doc.setFont("helvetica", "normal");
  doc.text("ASSESSMENT ANALYTICS REPORT", PAGE_WIDTH / 2, 60, { align: "center" });

  doc.setFontSize(28);
  doc.setFont("helvetica", "bold");
  const titleLines = doc.splitTextToSize(assessment.title, CONTENT_WIDTH - 20);
  doc.text(titleLines, PAGE_WIDTH / 2, 78, { align: "center" });

  // Subtitle
  doc.setFontSize(11);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(...COLORS.accentLight);
  doc.text(
    assessment.description || "Comprehensive assessment analytics report",
    PAGE_WIDTH / 2,
    78 + titleLines.length * 12 + 8,
    { align: "center", maxWidth: CONTENT_WIDTH - 30 },
  );

  // Summary metrics boxes
  const overview = dashboard.overview;
  const metricsY = 160;
  const boxW = 38;
  const gap = 6;
  const totalW = boxW * 4 + gap * 3;
  const startX = (PAGE_WIDTH - totalW) / 2;

  const metrics = [
    { label: "Total Candidates", value: String(overview.total_candidates) },
    { label: "Evaluated", value: String(overview.completed_candidates) },
    { label: "Average Score", value: `${Math.round(overview.average_score)}%` },
    { label: "Pass Rate", value: `${Math.round(overview.pass_rate)}%` },
  ];

  metrics.forEach((metric, idx) => {
    const x = startX + idx * (boxW + gap);
    doc.setFillColor(30, 41, 59);
    roundedRect(doc, x, metricsY, boxW, 34, 4, "F");

    doc.setFontSize(20);
    doc.setFont("helvetica", "bold");
    doc.setTextColor(...COLORS.white);
    doc.text(metric.value, x + boxW / 2, metricsY + 16, { align: "center" });

    doc.setFontSize(7);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(...COLORS.textMuted);
    doc.text(metric.label.toUpperCase(), x + boxW / 2, metricsY + 26, {
      align: "center",
    });
  });

  // Generated date
  doc.setFontSize(9);
  doc.setTextColor(...COLORS.textMuted);
  doc.text(
    `Generated on ${new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}`,
    PAGE_WIDTH / 2,
    PAGE_HEIGHT - 30,
    { align: "center" },
  );

  // Bottom accent stripe
  doc.setFillColor(...COLORS.accent);
  doc.rect(0, PAGE_HEIGHT - 6, PAGE_WIDTH, 6, "F");
}

/* ================================================================== */
/*  Assessment Details                                                 */
/* ================================================================== */

function drawAssessmentDetails(doc: jsPDF, startY: number, assessment: Assessment): number {
  let y = startY;
  const labelX = MARGIN;
  const valueX = MARGIN + 52;
  const lineH = 7;

  const fields: [string, string][] = [
    ["Title", assessment.title],
    ["Description", assessment.description || "—"],
    ["Duration", `${assessment.duration_minutes} minutes`],
    ["Passing Score", `${assessment.passing_score}%`],
    ["Questions", `${assessment.question_count} total · ${assessment.question_count_per_candidate || assessment.question_count} per candidate`],
    ["Languages", assessment.supported_languages.join(", ").toUpperCase() || "—"],
    ["Proctoring", assessment.proctoring_mode || "Standard"],
    ["Shuffle", assessment.shuffle_questions ? "Yes" : "No"],
    ["Score Visible", assessment.show_score_to_candidate ? "Yes" : "No"],
    ["Score Weights", `Test cases: ${assessment.test_case_score_weight}% · Coding: ${assessment.coding_score_weight}% · AI: ${assessment.ai_score_weight}%`],
    ["Created", formatDateTime(assessment.created_at)],
    ["Status", assessment.status.charAt(0).toUpperCase() + assessment.status.slice(1)],
  ];

  // Card background
  const cardHeight = fields.length * lineH + 14;
  y = ensureSpace(doc, y, cardHeight);
  doc.setFillColor(...COLORS.bgLight);
  roundedRect(doc, MARGIN, y, CONTENT_WIDTH, cardHeight, 4, "F");
  doc.setDrawColor(...COLORS.border);
  roundedRect(doc, MARGIN, y, CONTENT_WIDTH, cardHeight, 4, "S");

  y += 8;
  for (const [label, value] of fields) {
    doc.setFontSize(9);
    doc.setFont("helvetica", "bold");
    doc.setTextColor(...COLORS.textMuted);
    doc.text(label, labelX + 6, y);

    doc.setFont("helvetica", "normal");
    doc.setTextColor(...COLORS.text);
    const wrappedValue = doc.splitTextToSize(value, CONTENT_WIDTH - 60);
    doc.text(wrappedValue[0], valueX, y);
    y += lineH;
  }

  y += 4;
  return y;
}

/* ================================================================== */
/*  Questions Table                                                    */
/* ================================================================== */

function drawQuestionsTable(doc: jsPDF, startY: number, assessment: Assessment): number {
  let y = startY;
  const questions = assessment.questions;

  if (!questions || questions.length === 0) {
    doc.setFontSize(10);
    doc.setTextColor(...COLORS.textMuted);
    doc.text("No questions assigned to this assessment.", MARGIN, y);
    return y + 8;
  }

  // Table header
  const colWidths = [12, 70, 28, 28, 32];
  const headers = ["#", "Question Title", "Difficulty", "Marks", "Languages"];
  const headerH = 9;

  y = ensureSpace(doc, y, headerH + 10);
  doc.setFillColor(...COLORS.accent);
  roundedRect(doc, MARGIN, y, CONTENT_WIDTH, headerH, 3, "F");
  doc.setFontSize(8);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(...COLORS.white);

  let colX = MARGIN + 4;
  headers.forEach((header, idx) => {
    doc.text(header, colX, y + 6);
    colX += colWidths[idx];
  });
  y += headerH;

  // Table rows
  questions.forEach((question, idx) => {
    const rowH = 8;
    y = ensureSpace(doc, y, rowH + 2);

    // Alternating row background
    if (idx % 2 === 0) {
      doc.setFillColor(...COLORS.bgLight);
      doc.rect(MARGIN, y, CONTENT_WIDTH, rowH, "F");
    }

    doc.setFontSize(8);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(...COLORS.text);

    colX = MARGIN + 4;
    const cells = [
      String(idx + 1),
      truncateText(question.title, 40),
      capitalizeFirst(question.difficulty),
      String(question.marks),
      question.supported_languages.join(", ").toUpperCase(),
    ];

    cells.forEach((cell, colIdx) => {
      // Difficulty badge coloring
      if (colIdx === 2) {
        const diffColor = question.difficulty === "easy" ? COLORS.success
          : question.difficulty === "medium" ? COLORS.warning
          : COLORS.danger;
        doc.setTextColor(...diffColor);
        doc.setFont("helvetica", "bold");
      }
      doc.text(cell, colX, y + 5.5);
      if (colIdx === 2) {
        doc.setTextColor(...COLORS.text);
        doc.setFont("helvetica", "normal");
      }
      colX += colWidths[colIdx];
    });
    y += rowH;
  });

  // Bottom border
  doc.setDrawColor(...COLORS.border);
  doc.line(MARGIN, y, MARGIN + CONTENT_WIDTH, y);

  return y + 4;
}

/* ================================================================== */
/*  Analytics Overview                                                 */
/* ================================================================== */

function drawAnalyticsOverview(
  doc: jsPDF,
  startY: number,
  dashboard: AssessmentEvaluationDashboard,
): number {
  let y = startY;
  const overview = dashboard.overview;

  const metricRows: [string, string][] = [
    ["Total Candidates", String(overview.total_candidates)],
    ["Evaluated Candidates", String(overview.completed_candidates)],
    ["Average Score", `${Math.round(overview.average_score)}%`],
    ["Highest Score", `${Math.round(overview.highest_score)}%`],
    ["Pass Rate", `${Math.round(overview.pass_rate)}%`],
    ["Avg Test Case Score", `${Math.round(overview.average_test_case_score)}%`],
    ["Avg Coding Score", `${Math.round(overview.average_coding_score)}%`],
    ["Avg AI Score", `${Math.round(overview.average_ai_score)}%`],
    ["Pending Jobs", String(overview.pending_jobs)],
    ["Failed Jobs", String(overview.failed_jobs)],
  ];

  // Draw metric cards in a 2-column grid
  const cardW = (CONTENT_WIDTH - 6) / 2;
  const cardH = 12;

  for (let i = 0; i < metricRows.length; i += 2) {
    y = ensureSpace(doc, y, cardH + 3);

    for (let j = 0; j < 2 && i + j < metricRows.length; j++) {
      const [label, value] = metricRows[i + j];
      const x = MARGIN + j * (cardW + 6);

      doc.setFillColor(...COLORS.bgLight);
      roundedRect(doc, x, y, cardW, cardH, 3, "F");
      doc.setDrawColor(...COLORS.border);
      roundedRect(doc, x, y, cardW, cardH, 3, "S");

      doc.setFontSize(8);
      doc.setFont("helvetica", "normal");
      doc.setTextColor(...COLORS.textMuted);
      doc.text(label, x + 5, y + 5);

      doc.setFontSize(11);
      doc.setFont("helvetica", "bold");
      doc.setTextColor(...COLORS.accent);
      doc.text(value, x + cardW - 5, y + 8.5, { align: "right" });
    }

    y += cardH + 3;
  }

  return y;
}

/* ================================================================== */
/*  Slot Comparison Table                                              */
/* ================================================================== */

function drawSlotComparisonTable(
  doc: jsPDF,
  startY: number,
  slotAnalytics: SlotAnalyticsPdf[],
): number {
  let y = startY;

  // Column config
  const colW = [42, 18, 18, 18, 22, 22, 18, 18];
  const colHeaders = ["Test Slot", "Score", "Pass %", "Subs", "Duration", "Coding", "AI", "Hidden"];
  const headerH = 9;
  const rowH = 8;

  // Header
  y = ensureSpace(doc, y, headerH + slotAnalytics.length * rowH + 4);
  doc.setFillColor(...COLORS.accent);
  roundedRect(doc, MARGIN, y, CONTENT_WIDTH, headerH, 3, "F");
  doc.setFontSize(7.5);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(...COLORS.white);

  let cx = MARGIN + 3;
  colHeaders.forEach((h, i) => {
    doc.text(h, cx, y + 6);
    cx += colW[i];
  });
  y += headerH;

  // Data rows
  slotAnalytics.forEach((slot, idx) => {
    y = ensureSpace(doc, y, rowH + 2);

    if (idx % 2 === 0) {
      doc.setFillColor(...COLORS.bgLight);
      doc.rect(MARGIN, y, CONTENT_WIDTH, rowH, "F");
    }

    doc.setFontSize(7.5);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(...COLORS.text);

    cx = MARGIN + 3;
    const cells = [
      truncateText(slot.title, 24),
      `${Math.round(slot.averageScore)}%`,
      `${Math.round(slot.passRate)}%`,
      `${slot.submittedCount}/${slot.candidateCount}`,
      formatDuration(slot.averageDurationSeconds),
      `${Math.round(slot.averageCodingScore)}%`,
      `${Math.round(slot.averageAiScore)}%`,
      `${Math.round(slot.hiddenPassRate)}%`,
    ];

    cells.forEach((cell, i) => {
      doc.text(cell, cx, y + 5.5);
      cx += colW[i];
    });

    y += rowH;
  });

  doc.setDrawColor(...COLORS.border);
  doc.line(MARGIN, y, MARGIN + CONTENT_WIDTH, y);

  return y + 4;
}

/* ================================================================== */
/*  Visual Bar Charts                                                  */
/* ================================================================== */

function drawBarCharts(
  doc: jsPDF,
  startY: number,
  slotAnalytics: SlotAnalyticsPdf[],
): number {
  let y = startY;

  const charts: {
    title: string;
    color: [number, number, number];
    getValue: (s: SlotAnalyticsPdf) => number;
    format: (s: SlotAnalyticsPdf) => string;
    maxValue: number;
  }[] = [
    {
      title: "Average Final Score",
      color: COLORS.barScore,
      getValue: (s) => s.averageScore,
      format: (s) => `${Math.round(s.averageScore)}%`,
      maxValue: 100,
    },
    {
      title: "Participation Rate",
      color: COLORS.barParticipation,
      getValue: (s) => s.submissionRate,
      format: (s) => `${Math.round(s.submissionRate)}%`,
      maxValue: 100,
    },
    {
      title: "Average Duration",
      color: COLORS.barDuration,
      getValue: (s) => s.averageDurationSeconds ?? 0,
      format: (s) => formatDuration(s.averageDurationSeconds),
      maxValue: Math.max(
        ...slotAnalytics.map((s) => s.averageDurationSeconds ?? 0),
        1,
      ),
    },
  ];

  for (const chart of charts) {
    const chartH = slotAnalytics.length * 14 + 22;
    y = ensureSpace(doc, y, chartH);

    // Chart title
    doc.setFontSize(10);
    doc.setFont("helvetica", "bold");
    doc.setTextColor(...COLORS.text);
    doc.text(chart.title, MARGIN, y + 4);
    y += 10;

    // Background card
    const cardH = slotAnalytics.length * 14 + 8;
    doc.setFillColor(...COLORS.bgLight);
    roundedRect(doc, MARGIN, y, CONTENT_WIDTH, cardH, 4, "F");
    doc.setDrawColor(...COLORS.border);
    roundedRect(doc, MARGIN, y, CONTENT_WIDTH, cardH, 4, "S");

    let barY = y + 6;
    const labelW = 42;
    const valueW = 22;
    const barMaxW = CONTENT_WIDTH - labelW - valueW - 14;

    for (const slot of slotAnalytics) {
      // Label
      doc.setFontSize(7.5);
      doc.setFont("helvetica", "normal");
      doc.setTextColor(...COLORS.text);
      doc.text(truncateText(slot.title, 24), MARGIN + 5, barY + 4);

      // Bar
      const rawValue = chart.getValue(slot);
      const barW = chart.maxValue > 0
        ? (rawValue / chart.maxValue) * barMaxW
        : 0;
      const barH = 6;
      const barX = MARGIN + labelW + 2;

      // Background track
      doc.setFillColor(230, 230, 235);
      roundedRect(doc, barX, barY, barMaxW, barH, 2, "F");

      // Filled bar
      if (barW > 0) {
        doc.setFillColor(...chart.color);
        roundedRect(doc, barX, barY, Math.max(barW, 3), barH, 2, "F");
      }

      // Value label
      doc.setFontSize(7.5);
      doc.setFont("helvetica", "bold");
      doc.setTextColor(...chart.color);
      doc.text(chart.format(slot), barX + barMaxW + 3, barY + 4.5);

      barY += 14;
    }

    y += cardH + 8;
  }

  return y;
}

/* ================================================================== */
/*  Page Footers                                                       */
/* ================================================================== */

function addFooters(doc: jsPDF, assessmentTitle: string) {
  const pageCount = doc.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);

    // Bottom accent line
    doc.setDrawColor(...COLORS.accent);
    doc.setLineWidth(0.5);
    doc.line(MARGIN, PAGE_HEIGHT - 14, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 14);

    // Left footer text
    doc.setFontSize(7);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(...COLORS.textMuted);
    doc.text(
      truncateText(assessmentTitle, 50),
      MARGIN,
      PAGE_HEIGHT - 9,
    );

    // Right page number
    doc.text(`Page ${i} of ${pageCount}`, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 9, {
      align: "right",
    });
  }
}

/* ================================================================== */
/*  Build slot analytics (mirrors UI logic)                            */
/* ================================================================== */

function buildSlotAnalyticsPdf(
  passingScore: number,
  slots: AssessmentSlot[],
  slotCandidates: SlotCandidateLookup,
  leaderboard: CandidateEvaluationSummary[],
): SlotAnalyticsPdf[] {
  const evalMap = new Map(
    leaderboard.map((c) => [c.candidate_assessment_id, c]),
  );

  return slots.map((slot) => {
    const candidates = slotCandidates[slot.id] ?? [];
    const submitted = candidates.filter((c) =>
      ["submitted", "auto_submitted"].includes(c.assessment_status),
    ).length;
    const evaluated = candidates
      .map((c) => evalMap.get(c.candidate_assessment_id))
      .filter((c): c is CandidateEvaluationSummary => Boolean(c));
    const candidateCount = Math.max(slot.candidate_count, candidates.length);
    const submittedCount = Math.max(slot.submitted_count, submitted);

    const scoreTotal = evaluated.reduce((s, c) => s + c.scores.final_score, 0);
    const codingTotal = evaluated.reduce((s, c) => s + c.scores.coding_score, 0);
    const aiTotal = evaluated.reduce((s, c) => s + c.scores.ai_score, 0);
    const hiddenPassed = evaluated.reduce((s, c) => s + c.hidden_passed, 0);
    const hiddenTotal = evaluated.reduce((s, c) => s + c.hidden_total, 0);
    const durations = evaluated
      .map((c) => c.time_taken_seconds ?? c.activity?.total_time_seconds)
      .filter((d): d is number => typeof d === "number");

    const bands = evaluated.reduce(
      (acc, c) => {
        const score = c.scores.final_score;
        if (score >= Math.max(90, passingScore + 15)) acc.excellent += 1;
        else if (score >= passingScore) acc.pass += 1;
        else acc.review += 1;
        return acc;
      },
      { excellent: 0, pass: 0, review: 0 },
    );

    const avg = (t: number, n: number) => (n ? t / n : 0);
    const pct = (v: number, t: number) => (t ? (v / t) * 100 : 0);

    return {
      id: slot.id,
      title: slot.title,
      status: slot.effective_status,
      startsAt: slot.start_at,
      candidateCount,
      submittedCount,
      evaluatedCount: evaluated.length,
      averageScore: avg(scoreTotal, evaluated.length),
      topScore: evaluated.length
        ? Math.max(...evaluated.map((c) => c.scores.final_score))
        : 0,
      passRate: pct(
        evaluated.filter((c) => c.scores.final_score >= passingScore).length,
        evaluated.length,
      ),
      submissionRate: pct(submittedCount, candidateCount),
      evaluationRate: pct(evaluated.length, submittedCount),
      hiddenPassRate: pct(hiddenPassed, hiddenTotal),
      averageCodingScore: avg(codingTotal, evaluated.length),
      averageAiScore: avg(aiTotal, evaluated.length),
      averageDurationSeconds: durations.length
        ? avg(durations.reduce((s, d) => s + d, 0), durations.length)
        : null,
      bands,
    };
  });
}

/* ================================================================== */
/*  Helpers                                                            */
/* ================================================================== */

function roundedRect(
  doc: jsPDF,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
  style: "F" | "S" | "FS",
) {
  // jsPDF doesn't have built-in rounded rects so we draw with lines & arcs
  doc.roundedRect(x, y, w, h, r, r, style);
}

function ensureSpace(doc: jsPDF, currentY: number, requiredH: number): number {
  if (currentY + requiredH > PAGE_HEIGHT - 20) {
    doc.addPage();
    return MARGIN;
  }
  return currentY;
}

function truncateText(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.substring(0, maxLen - 1) + "…";
}

function capitalizeFirst(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "—";
  const rounded = Math.round(seconds);
  const m = Math.floor(rounded / 60);
  const s = rounded % 60;
  return m < 1 ? `${s}s` : `${m}m ${s}s`;
}

function formatDateTime(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(d);
}

function drawSectionHeading(doc: jsPDF, currentY: number, title: string): number {
  const y = ensureSpace(doc, currentY, 15);
  // Left indicator block
  doc.setFillColor(...COLORS.accent);
  doc.rect(MARGIN, y, 3, 6, "F");
  
  // Section heading text
  doc.setFontSize(12);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(...COLORS.primary);
  doc.text(title, MARGIN + 6, y + 5.2);
  
  return y + 10;
}
