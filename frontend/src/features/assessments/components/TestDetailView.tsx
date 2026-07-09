import { useEffect, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  BarChart3,
  CalendarClock,
  Clock3,
  Gauge,
  Pause,
  Play,
  Settings,
  Timer,
  X,
  XCircle,
} from "lucide-react";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { ScheduleDateTimePicker } from "../../../components/ui/ScheduleDateTimePicker";
import type {
  Assessment,
  AssessmentSlot,
  AssessmentSlotActionPayload,
  AssessmentSlotUpdatePayload,
  EvaluationBackfillResponse,
  MonitoringCandidate,
  SlotCandidate,
} from "../types/Assessment";
import {
  clampLocalInputToMinimum,
  errorMessage,
  formatCountdown,
  formatDateTime,
  getSlotScheduleFieldErrors,
  minimumSlotEndInput,
  nextAvailableTimeInput,
  TIME_ZONE_OPTIONS,
  timezoneOffsetMinutesForLocalDateTime,
  toIsoDateTimeForTimezone,
  toTimezoneInputValue,
} from "../utils/recruiterAssessmentViewModel";
import {
  CandidatesTab,
  LiveMonitoringTab,
} from "./CandidateManagementPanels";
import { HealthDot, StatusBadge } from "./AssessmentStatusPrimitives";
import { TestResultsTab } from "./TestResultsTab";

export type TestTab = "candidates" | "live" | "results";

const EXTEND_MINUTE_PRESETS = [15, 30, 60];

export function TestDetailView({
  assessment,
  slot,
  tab,
  candidates,
  monitoringItems,
  monitoringLoading,
  submittedCount,
  inProgressCount,
  candidateCsv,
  importPending,
  invitePending,
  slotUpdatePending,
  importErrors,
  importError,
  inviteError,
  slotUpdateError,
  evaluationBackfillPending,
  evaluationBackfillError,
  evaluationBackfillResult,
  resendPendingId,
  onBack,
  onTabChange,
  onCsvChange,
  onImport,
  onSendInvites,
  onUpdateSlot,
  onControlSlot,
  onBackfillEvaluations,
  onResend,
}: {
  assessment: Assessment;
  slot: AssessmentSlot;
  tab: TestTab;
  candidates: SlotCandidate[];
  monitoringItems: MonitoringCandidate[];
  monitoringLoading: boolean;
  submittedCount: number;
  inProgressCount: number;
  candidateCsv: string;
  importPending: boolean;
  invitePending: boolean;
  slotUpdatePending: boolean;
  importErrors: Array<{ row_number: number; email: string; errors: string[] }>;
  importError: string;
  inviteError: string;
  slotUpdateError: string;
  evaluationBackfillPending: boolean;
  evaluationBackfillError: string;
  evaluationBackfillResult: EvaluationBackfillResponse | null;
  resendPendingId: string | null;
  onBack: () => void;
  onTabChange: (tab: TestTab) => void;
  onCsvChange: (value: string) => void;
  onImport: (csvText: string) => void;
  onSendInvites: (candidateAssessmentIds?: string[]) => void;
  onUpdateSlot: (payload: AssessmentSlotUpdatePayload) => Promise<unknown> | void;
  onControlSlot: (payload: AssessmentSlotActionPayload) => Promise<unknown> | void;
  onBackfillEvaluations: (
    candidateAssessmentIds: string[],
  ) => Promise<unknown> | void;
  onResend: (candidateAssessmentId: string) => void;
}) {
  const [isManagingTest, setIsManagingTest] = useState(false);
  const [showTestSettings, setShowTestSettings] = useState(false);
  const [scheduleNowMs, setScheduleNowMs] = useState(() => Date.now());
  const [slotFieldErrors, setSlotFieldErrors] = useState({
    start_at: "",
    end_at: "",
    general: "",
  });
  const [pendingTestAction, setPendingTestAction] =
    useState<AssessmentSlotActionPayload | null>(null);
  const [testResponseMessage, setTestResponseMessage] = useState("");
  const [testResponseTone, setTestResponseTone] = useState<"success" | "warning">(
    "success",
  );
  const [extendMinutes, setExtendMinutes] = useState(15);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [editForm, setEditForm] = useState({
    title: slot.title,
    start_at: toTimezoneInputValue(
      slot.start_at,
      slot.timezone_name,
      slot.timezone_offset_minutes,
    ),
    end_at: toTimezoneInputValue(
      slot.end_at,
      slot.timezone_name,
      slot.timezone_offset_minutes,
    ),
    duration_minutes: slot.duration_minutes || assessment.duration_minutes || 60,
    timezone_name: slot.timezone_name,
    timezone_offset_minutes: slot.timezone_offset_minutes,
    instructions_override: slot.instructions_override,
    status: slot.status,
  });

  useEffect(() => {
    setEditForm({
      title: slot.title,
      start_at: toTimezoneInputValue(
        slot.start_at,
        slot.timezone_name,
        slot.timezone_offset_minutes,
      ),
      end_at: toTimezoneInputValue(
        slot.end_at,
        slot.timezone_name,
        slot.timezone_offset_minutes,
      ),
      duration_minutes: slot.duration_minutes || assessment.duration_minutes || 60,
      timezone_name: slot.timezone_name,
      timezone_offset_minutes: slot.timezone_offset_minutes,
      instructions_override: slot.instructions_override,
      status: slot.status,
    });
  }, [assessment.duration_minutes, slot]);

  useEffect(() => {
    const interval = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!showTestSettings) {
      return;
    }
    const interval = window.setInterval(() => setScheduleNowMs(Date.now()), 30_000);
    return () => window.clearInterval(interval);
  }, [showTestSettings]);

  const secondsUntilStart = Math.max(
    0,
    Math.floor((new Date(slot.start_at).getTime() - nowMs) / 1000),
  );
  const minimumEditStart = nextAvailableTimeInput(
    editForm.timezone_name,
    editForm.timezone_offset_minutes,
    scheduleNowMs,
  );
  const minimumEditEnd = minimumSlotEndInput(
    editForm.start_at,
    editForm.duration_minutes,
    editForm.timezone_name,
    editForm.timezone_offset_minutes,
    scheduleNowMs,
  );
  const secondsUntilClose = Math.max(
    0,
    Math.floor((new Date(slot.end_at).getTime() - nowMs) / 1000),
  );
  const effectiveStatus =
    slot.status === "paused" || slot.status === "closed" || slot.status === "draft"
      ? slot.status
      : secondsUntilStart > 0
        ? "scheduled"
        : secondsUntilClose > 0
          ? "active"
          : "closed";
  const statusLabel =
    effectiveStatus === "scheduled"
      ? `To be started in ${formatCountdown(secondsUntilStart)}`
      : effectiveStatus === "active"
        ? `Accepting responses closes in ${formatCountdown(secondsUntilClose)}`
        : effectiveStatus === "paused"
          ? "Paused. Candidate work is temporarily blocked."
          : "Closed for responses";
  const pendingActionLabel =
    pendingTestAction?.action === "continue"
      ? "continue this test slot"
      : pendingTestAction?.action === "extend"
        ? `extend this test slot by ${pendingTestAction.extend_minutes || extendMinutes} minutes`
        : pendingTestAction?.action === "close"
          ? "close this test slot now"
          : pendingTestAction?.action === "pause"
            ? "pause this test slot"
            : "";
  const proposedExtendedEndAt = new Date(
    new Date(slot.end_at).getTime() + Math.max(extendMinutes, 1) * 60_000,
  ).toISOString();
  const canPauseTest = effectiveStatus !== "paused" && effectiveStatus !== "closed";
  const canContinueTest = effectiveStatus === "paused";
  const canExtendTest = effectiveStatus !== "closed";
  const canCloseTest = effectiveStatus !== "closed";
  const pendingActionImpact =
    pendingTestAction?.action === "pause"
      ? "Candidates will see that the assessment is paused and cannot continue until you resume it."
      : pendingTestAction?.action === "continue"
        ? "Candidates will be able to continue from their saved progress."
        : pendingTestAction?.action === "extend"
          ? `The end time will move from ${formatDateTime(slot.end_at)} to ${formatDateTime(proposedExtendedEndAt)}.`
          : pendingTestAction?.action === "close"
            ? "Candidate access will close immediately. Submitted work remains available for results."
            : "";

  function closeManageTestModal() {
    setIsManagingTest(false);
    setPendingTestAction(null);
    setTestResponseMessage("");
  }

  function requestTestAction(
    action: AssessmentSlotActionPayload,
    unavailableMessage?: string,
  ) {
    setPendingTestAction(null);
    if (unavailableMessage) {
      setTestResponseTone("warning");
      setTestResponseMessage(unavailableMessage);
      return;
    }
    setTestResponseMessage("");
    setPendingTestAction(action);
  }

  async function confirmTestAction() {
    if (!pendingTestAction) {
      return;
    }
    setTestResponseMessage("");
    try {
      await onControlSlot(pendingTestAction);
      const completionMessage =
        pendingTestAction.action === "extend"
          ? `Action completed: extended by ${pendingTestAction.extend_minutes || extendMinutes} minutes. New planned end: ${formatDateTime(proposedExtendedEndAt)}.`
          : `Action completed: ${pendingActionLabel}.`;
      setTestResponseTone("success");
      setTestResponseMessage(completionMessage);
      setPendingTestAction(null);
    } catch {
      setTestResponseMessage("");
    }
  }

  function openTestSettings() {
    setScheduleNowMs(Date.now());
    setSlotFieldErrors({ start_at: "", end_at: "", general: "" });
    setShowTestSettings(true);
  }

  function updateEditSchedule(
    patch: Partial<typeof editForm>,
    currentForm: typeof editForm = editForm,
  ) {
    const nextForm = { ...currentForm, ...patch };
    const minimumStart = nextAvailableTimeInput(
      nextForm.timezone_name,
      nextForm.timezone_offset_minutes,
      scheduleNowMs,
    );
    const startAt =
      clampLocalInputToMinimum(nextForm.start_at, minimumStart) || minimumStart;
    const minimumEnd = minimumSlotEndInput(
      startAt,
      nextForm.duration_minutes,
      nextForm.timezone_name,
      nextForm.timezone_offset_minutes,
      scheduleNowMs,
    );
    const endAt =
      "end_at" in patch
        ? clampLocalInputToMinimum(nextForm.end_at, minimumEnd) || minimumEnd
        : "start_at" in patch || "duration_minutes" in patch
          ? minimumEnd
          : clampLocalInputToMinimum(nextForm.end_at, minimumEnd) || minimumEnd;
    const resolvedForm = {
      ...nextForm,
      start_at: startAt,
      end_at: endAt,
    };
    setEditForm(resolvedForm);
    setSlotFieldErrors(getSlotScheduleFieldErrors(resolvedForm, scheduleNowMs));
  }

  async function saveSlotChanges() {
    setTestResponseMessage("");
    const scheduleErrors = getSlotScheduleFieldErrors(editForm, scheduleNowMs);
    setSlotFieldErrors(scheduleErrors);
    if (scheduleErrors.start_at || scheduleErrors.end_at || scheduleErrors.general) {
      return;
    }
    try {
      const timezoneOffsetMinutes = timezoneOffsetMinutesForLocalDateTime(
        editForm.start_at || editForm.end_at,
        editForm.timezone_name,
        editForm.timezone_offset_minutes,
      );
      const startAt = toIsoDateTimeForTimezone(
        editForm.start_at,
        editForm.timezone_name,
        timezoneOffsetMinutes,
      );
      const endAt = toIsoDateTimeForTimezone(
        editForm.end_at,
        editForm.timezone_name,
        timezoneOffsetMinutes,
      );
      await onUpdateSlot({
        title: editForm.title,
        start_at: startAt,
        end_at: endAt,
        duration_minutes: editForm.duration_minutes,
        timezone_name: editForm.timezone_name,
        timezone_offset_minutes: timezoneOffsetMinutes,
        instructions_override: editForm.instructions_override,
        status: editForm.status,
      });
      setTestResponseTone("success");
      setTestResponseMessage(
        `Test slot details updated successfully. New window: ${formatDateTime(startAt)} to ${formatDateTime(endAt)}.`,
      );
      setShowTestSettings(false);
      setSlotFieldErrors({ start_at: "", end_at: "", general: "" });
    } catch (error) {
      setTestResponseTone("warning");
      setTestResponseMessage(
        errorMessage(error) || "Choose a valid start and end time.",
      );
      setSlotFieldErrors((current) => ({
        ...current,
        general: errorMessage(error) || "Unable to save test slot settings.",
      }));
    }
  }

  return (
    <section className="assessment-drilldown">
      <div className="assessment-breadcrumb">
        <button type="button" onClick={onBack}>
          Back to test slots
        </button>
        <span>/</span>
        <strong>{assessment.title}</strong>
        <span>/</span>
        <strong>{slot.title}</strong>
      </div>

      <Card className="assessment-panel assessment-command-center test-command-center">
        <div className="assessment-command-title">
          <span className="panel-eyebrow">Test Slot</span>
          <h2>{slot.title}</h2>
          <p>
            {formatDateTime(slot.start_at)} to {formatDateTime(slot.end_at)}
          </p>
          <p className="slot-live-line">{statusLabel}</p>
        </div>

        <div className="assessment-header-metrics" aria-label="Test slot summary">
          <div className="assessment-header-metric">
            <strong>{slot.candidate_count}</strong>
            <span>Candidates</span>
          </div>
          <div className="assessment-header-metric">
            <strong>{inProgressCount}</strong>
            <span>In progress</span>
          </div>
          <div className="assessment-header-metric">
            <strong>{submittedCount}</strong>
            <span>Submitted</span>
          </div>
          <div className="assessment-header-metric">
            <strong>{slot.duration_minutes || assessment.duration_minutes}m</strong>
            <span>Duration</span>
          </div>
        </div>

        <div className="assessment-row-actions">
          <div className="status-with-dot">
            <HealthDot status={effectiveStatus} />
            <StatusBadge value={effectiveStatus} />
          </div>
          <Button
            type="button"
            variant="secondary"
            className="icon-only-button"
            onClick={openTestSettings}
            title="Test slot settings"
          >
            <Settings size={18} aria-hidden="true" />
            <span className="sr-only">Test slot settings</span>
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setIsManagingTest(true)}
          >
            Manage Test Slot
          </Button>
        </div>
      </Card>

      {!isManagingTest && testResponseMessage ? (
        <p className={`test-feedback-message is-${testResponseTone}`}>
          {testResponseMessage}
        </p>
      ) : null}

      {isManagingTest ? (
        <div
          className="dialog-backdrop test-management-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeManageTestModal();
            }
          }}
        >
          <div
            className="test-management-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="test-management-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="test-management-header">
              <div className="test-management-header-copy">
                <span>Test slot controls</span>
                <h2 id="test-management-title">{slot.title}</h2>
              </div>
              <button
                type="button"
                className="test-management-close"
                onClick={closeManageTestModal}
                aria-label="Close manage test slot dialog"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </header>

            <div className="test-management-progress" aria-label="Manage test slot steps">
              <div
                className={[
                  "test-management-progress-item",
                  pendingTestAction ? "is-complete" : "is-active",
                ].join(" ")}
              >
                <span>1</span>
                <strong>Choose action</strong>
              </div>
              <div
                className={[
                  "test-management-progress-item",
                  pendingTestAction ? "is-active" : "",
                ].join(" ")}
              >
                <span>2</span>
                <strong>Confirm change</strong>
              </div>
            </div>

            <div className="test-management-body">
              <section className="test-management-snapshot">
                <div className="test-management-snapshot-status">
                  <div className="status-with-dot">
                    <HealthDot status={effectiveStatus} />
                    <StatusBadge value={effectiveStatus} />
                  </div>
                  <p>{statusLabel}</p>
                </div>

                <div className="test-control-overview">
                  <div>
                    <span>
                      <CalendarClock size={14} aria-hidden="true" />
                      Start time
                    </span>
                    <strong>{formatDateTime(slot.start_at)}</strong>
                    <em>{slot.timezone_name}</em>
                  </div>
                  <div>
                    <span>
                      <Clock3 size={14} aria-hidden="true" />
                      End time
                    </span>
                    <strong>{formatDateTime(slot.end_at)}</strong>
                    <em>
                      {effectiveStatus === "active"
                        ? `${formatCountdown(secondsUntilClose)} remaining`
                        : slot.is_accepting_responses
                          ? "Window is accepting responses"
                          : "Window is not accepting responses"}
                    </em>
                  </div>
                  <div>
                    <span>
                      <Timer size={14} aria-hidden="true" />
                      After extension
                    </span>
                    <strong>{formatDateTime(proposedExtendedEndAt)}</strong>
                    <em>Based on +{Math.max(extendMinutes, 1)} minutes</em>
                  </div>
                  <div>
                    <span>
                      <Gauge size={14} aria-hidden="true" />
                      Candidates
                    </span>
                    <strong>{slot.candidate_count}</strong>
                    <em>
                      {inProgressCount} in progress · {submittedCount} submitted
                    </em>
                  </div>
                </div>
              </section>

              <section className="test-management-actions-section">
                <div className="test-management-section-head">
                  <h3>Available actions</h3>
                </div>

                <div className="test-management-actions" aria-label="Test slot controls">
                  <button
                    type="button"
                    className={[
                      "test-action-card",
                      "test-action-card-pause",
                      canPauseTest ? "" : "is-unavailable",
                      pendingTestAction?.action === "pause" ? "is-selected" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    disabled={slotUpdatePending}
                    onClick={() =>
                      requestTestAction(
                        { action: "pause" },
                        canPauseTest
                          ? undefined
                          : effectiveStatus === "paused"
                            ? "This test slot is already paused. Use Continue Test Slot when candidates can resume."
                            : "This test slot is already closed, so it cannot be paused.",
                      )
                    }
                  >
                    <div className="test-action-card-icon">
                      <Pause size={18} aria-hidden="true" />
                    </div>
                    <span>Pause</span>
                    <strong>Pause Test Slot</strong>
                    <em>
                      {canPauseTest
                        ? "Temporarily block candidate progress until you resume."
                        : "Not available for the current status."}
                    </em>
                  </button>

                  <button
                    type="button"
                    className={[
                      "test-action-card",
                      "test-action-card-resume",
                      canContinueTest ? "" : "is-unavailable",
                      pendingTestAction?.action === "continue" ? "is-selected" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    disabled={slotUpdatePending}
                    onClick={() =>
                      requestTestAction(
                        { action: "continue" },
                        canContinueTest
                          ? undefined
                          : "Continue becomes available only after this test slot is paused.",
                      )
                    }
                  >
                    <div className="test-action-card-icon">
                      <Play size={18} aria-hidden="true" />
                    </div>
                    <span>Resume</span>
                    <strong>Continue Test Slot</strong>
                    <em>
                      {canContinueTest
                        ? "Let candidates continue from saved progress."
                        : "Available only while paused."}
                    </em>
                  </button>

                  <div
                    className={[
                      "test-action-card",
                      "test-extend-card",
                      canExtendTest ? "" : "is-unavailable",
                      pendingTestAction?.action === "extend" ? "is-selected" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    <div className="test-action-card-icon">
                      <Timer size={18} aria-hidden="true" />
                    </div>
                    <span>Extend</span>
                    <strong>Extend Time</strong>
                    <p>Add extra minutes to the current end time.</p>
                    <div className="test-extend-presets" role="group" aria-label="Extension presets">
                      {EXTEND_MINUTE_PRESETS.map((minutes) => (
                        <button
                          key={minutes}
                          type="button"
                          className={extendMinutes === minutes ? "is-active" : ""}
                          disabled={!canExtendTest || slotUpdatePending}
                          onClick={() => setExtendMinutes(minutes)}
                        >
                          +{minutes}m
                        </button>
                      ))}
                    </div>
                    <label>
                      <small>Custom minutes</small>
                      <input
                        type="number"
                        min={1}
                        max={720}
                        value={extendMinutes}
                        disabled={!canExtendTest || slotUpdatePending}
                        onChange={(event) =>
                          setExtendMinutes(Number(event.target.value))
                        }
                      />
                    </label>
                    <em>New end: {formatDateTime(proposedExtendedEndAt)}</em>
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={slotUpdatePending || !canExtendTest}
                      onClick={() =>
                        requestTestAction(
                          {
                            action: "extend",
                            extend_minutes: Math.max(extendMinutes, 1),
                          },
                          canExtendTest
                            ? undefined
                            : "This test slot is closed. Reopening closed test slots is not supported in this flow.",
                        )
                      }
                    >
                      Use this extension
                    </Button>
                  </div>

                  <button
                    type="button"
                    className={[
                      "test-action-card",
                      "test-action-card-close",
                      "test-action-danger",
                      canCloseTest ? "" : "is-unavailable",
                      pendingTestAction?.action === "close" ? "is-selected" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    disabled={slotUpdatePending}
                    onClick={() =>
                      requestTestAction(
                        { action: "close" },
                        canCloseTest
                          ? undefined
                          : "This test slot is already closed. No further close action is needed.",
                      )
                    }
                  >
                    <div className="test-action-card-icon">
                      <XCircle size={18} aria-hidden="true" />
                    </div>
                    <span>Close</span>
                    <strong>Close Test Slot</strong>
                    <em>
                      {canCloseTest
                        ? "Stop accepting candidate responses immediately."
                        : "Already closed."}
                    </em>
                  </button>
                </div>
              </section>

              {pendingTestAction ? (
                <section
                  className={[
                    "test-confirm-panel",
                    pendingTestAction.action === "close" ? "is-danger" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  <div className="test-confirm-panel-copy">
                    <div className="test-confirm-panel-icon">
                      <AlertTriangle size={18} aria-hidden="true" />
                    </div>
                    <div>
                      <strong>Confirm {pendingActionLabel}</strong>
                      <p>{pendingActionImpact}</p>
                    </div>
                  </div>
                  <div className="test-confirm-panel-actions">
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setPendingTestAction(null)}
                    >
                      Go back
                    </Button>
                    <Button
                      type="button"
                      disabled={slotUpdatePending}
                      onClick={() => void confirmTestAction()}
                    >
                      {slotUpdatePending ? "Applying..." : "Confirm change"}
                    </Button>
                  </div>
                </section>
              ) : null}

              {testResponseMessage && testResponseTone === "warning" ? (
                <div className="test-management-alert is-warning" role="alert">
                  <AlertTriangle size={18} aria-hidden="true" />
                  <div>
                    <strong>Action unavailable</strong>
                    <p>{testResponseMessage}</p>
                  </div>
                  <button
                    type="button"
                    className="test-management-alert-dismiss"
                    onClick={() => setTestResponseMessage("")}
                  >
                    Dismiss
                  </button>
                </div>
              ) : testResponseMessage ? (
                <div className="test-management-alert is-success" role="status">
                  <BadgeCheck size={18} aria-hidden="true" />
                  <div>
                    <strong>Action completed</strong>
                    <p>{testResponseMessage}</p>
                  </div>
                </div>
              ) : null}
              {slotUpdateError ? (
                <p className="form-error test-management-error">{slotUpdateError}</p>
              ) : null}
            </div>

            <footer className="test-management-footer">
              <p>
                {pendingTestAction
                  ? "Confirm or go back to choose a different action."
                  : "No changes apply until you confirm."}
              </p>
            </footer>
          </div>
        </div>
      ) : null}

      {showTestSettings ? (
        <div
          className="dialog-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setShowTestSettings(false);
            }
          }}
        >
          <Card
            className="test-settings-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="test-settings-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="settings-modal-header">
              <div>
                <span>Settings</span>
                <h2 id="test-settings-title">Test slot settings</h2>
              </div>
              <button
                type="button"
                className="modal-close-button"
                onClick={() => setShowTestSettings(false)}
              >
                Close
              </button>
            </div>
            <div className="assessment-form-stack slot-edit-form">
              <label className="field">
                <span>Test slot title</span>
                <input
                  value={editForm.title}
                  onChange={(event) =>
                    setEditForm({ ...editForm, title: event.target.value })
                  }
                />
              </label>
              <div className="assessment-inline-fields">
                <label className="field">
                  <span>Time region</span>
                  <select
                    value={editForm.timezone_name}
                    onChange={(event) => {
                      const timezone = TIME_ZONE_OPTIONS.find(
                        (option) => option.name === event.target.value,
                      );
                      if (!timezone) {
                        return;
                      }
                      updateEditSchedule({
                        timezone_name: timezone.name,
                        timezone_offset_minutes:
                          timezoneOffsetMinutesForLocalDateTime(
                            editForm.start_at || editForm.end_at,
                            timezone.name,
                            timezone.fallbackOffset,
                          ),
                      });
                    }}
                  >
                    {TIME_ZONE_OPTIONS.map((timezone) => (
                      <option key={timezone.name} value={timezone.name}>
                        {timezone.label}
                      </option>
                    ))}
                  </select>
                </label>
                <ScheduleDateTimePicker
                  label="Start time"
                  value={editForm.start_at}
                  min={minimumEditStart}
                  error={slotFieldErrors.start_at}
                  onChange={(startAt) => updateEditSchedule({ start_at: startAt })}
                />
              </div>
              <p className="assessment-context-banner">
                Times use {editForm.timezone_name}. Past times are disabled in the
                picker. Earliest start: {minimumEditStart.replace("T", " ")}.
              </p>
              <div className="assessment-inline-fields">
                <label className="field">
                  <span>Test slot duration (minutes)</span>
                  <input
                    type="number"
                    min={15}
                    max={360}
                    value={editForm.duration_minutes}
                    onChange={(event) => {
                      const duration = Math.max(
                        15,
                        Number(event.target.value) || 15,
                      );
                      updateEditSchedule({ duration_minutes: duration });
                    }}
                  />
                </label>
                <div className="field">
                  <ScheduleDateTimePicker
                    label="End time"
                    value={editForm.end_at}
                    min={minimumEditEnd}
                    error={slotFieldErrors.end_at}
                    onChange={(endAt) => updateEditSchedule({ end_at: endAt })}
                  />
                </div>
              </div>
              {slotFieldErrors.general ? (
                <p className="form-error" role="alert">
                  {slotFieldErrors.general}
                </p>
              ) : null}
              <label className="field">
                <span>Batch instructions override</span>
                <textarea
                  value={editForm.instructions_override}
                  onChange={(event) =>
                    setEditForm({
                      ...editForm,
                      instructions_override: event.target.value,
                    })
                  }
                />
              </label>
              <div className="settings-modal-actions">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setShowTestSettings(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  disabled={slotUpdatePending}
                  onClick={() => void saveSlotChanges()}
                >
                  {slotUpdatePending ? "Saving..." : "Save Settings"}
                </Button>
              </div>
            </div>
            {slotUpdateError ? <p className="form-error">{slotUpdateError}</p> : null}
          </Card>
        </div>
      ) : null}

      <div className="test-tab-bar" role="tablist" aria-label="Test slot sections">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "candidates"}
          className={tab === "candidates" ? "is-active" : ""}
          onClick={() => onTabChange("candidates")}
        >
          <BadgeCheck size={20} aria-hidden="true" />
          <span>
            <strong>Candidates</strong>
            <small>{candidates.length} in this test slot</small>
          </span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "live"}
          className={tab === "live" ? "is-active" : ""}
          onClick={() => onTabChange("live")}
        >
          <Gauge size={20} aria-hidden="true" />
          <span>
            <strong>Live Monitoring</strong>
            <small>{inProgressCount} currently active</small>
          </span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "results"}
          className={tab === "results" ? "is-active" : ""}
          onClick={() => onTabChange("results")}
        >
          <BarChart3 size={20} aria-hidden="true" />
          <span>
            <strong>Results</strong>
            <small>{submittedCount} submitted</small>
          </span>
        </button>
      </div>

      {tab === "candidates" ? (
        <CandidatesTab
          slot={slot}
          passingScore={assessment.passing_score}
          candidateCsv={candidateCsv}
          candidates={candidates}
          importPending={importPending}
          invitePending={invitePending}
          importErrors={importErrors}
          importError={importError}
          inviteError={inviteError}
          resendPendingId={resendPendingId}
          onCsvChange={onCsvChange}
          onImport={onImport}
          onSendInvites={onSendInvites}
          onResend={onResend}
        />
      ) : null}

      {tab === "live" ? (
        <LiveMonitoringTab
          candidates={candidates}
          items={monitoringItems}
          loading={monitoringLoading}
          liveSummary={{
            isLive: effectiveStatus === "active",
            statusLabel,
            secondsUntilClose,
            inProgressCount,
            submittedCount,
            candidateCount: slot.candidate_count,
          }}
        />
      ) : null}

      {tab === "results" ? (
        <TestResultsTab
          assessment={assessment}
          slot={slot}
          candidates={candidates}
          backfillPending={evaluationBackfillPending}
          backfillError={evaluationBackfillError}
          backfillResult={evaluationBackfillResult}
          onBackfillEvaluations={onBackfillEvaluations}
        />
      ) : null}
    </section>
  );
}
