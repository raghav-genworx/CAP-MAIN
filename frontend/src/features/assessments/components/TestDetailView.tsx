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
  Users,
  X,
  XCircle,
} from "lucide-react";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
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
  addMinutesToLocalInput,
  errorMessage,
  formatCountdown,
  formatDateTime,
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
import {
  DurationMinutesField,
  FutureDateTimeField,
} from "./FutureDateTimeField";
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
  monitoringConnected,
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
  monitoringConnected: boolean;
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

  const secondsUntilStart = Math.max(
    0,
    Math.floor((new Date(slot.start_at).getTime() - nowMs) / 1000),
  );
  const minimumEditEnd = addMinutesToLocalInput(
    editForm.start_at,
    editForm.duration_minutes,
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
      ? "continue this test"
      : pendingTestAction?.action === "extend"
        ? `extend this test by ${pendingTestAction.extend_minutes || extendMinutes} minutes`
        : pendingTestAction?.action === "close"
          ? "close this test now"
          : pendingTestAction?.action === "pause"
            ? "pause this test"
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
  const pendingConfirmLabel =
    pendingTestAction?.action === "pause"
      ? "Pause test"
      : pendingTestAction?.action === "continue"
        ? "Resume test"
        : pendingTestAction?.action === "extend"
          ? "Extend time"
          : pendingTestAction?.action === "close"
            ? "Close test"
            : "Confirm";

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

  async function saveSlotChanges() {
    setTestResponseMessage("");
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
      if (
        new Date(endAt).getTime() <
        new Date(startAt).getTime() + editForm.duration_minutes * 60_000
      ) {
        throw new Error(
          `End time must be at least ${editForm.duration_minutes} minutes after the start time.`,
        );
      }
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
        `Test details updated successfully. New window: ${formatDateTime(startAt)} to ${formatDateTime(endAt)}.`,
      );
      setShowTestSettings(false);
    } catch (error) {
      setTestResponseTone("warning");
      setTestResponseMessage(
        errorMessage(error) || "Choose a valid start and end time.",
      );
    }
  }

  return (
    <section className="assessment-drilldown test-slot-detail-view">
      <div className="assessment-breadcrumb">
        <button type="button" onClick={onBack}>
          Back to test slots
        </button>
        <span>/</span>
        <strong>{assessment.title}</strong>
        <span>/</span>
        <strong>{slot.title}</strong>
      </div>

      <Card className="assessment-panel assessment-command-center test-command-center workspace-page-header dashboard-style-detail-header">
        <div className="assessment-command-title">
          <span className="panel-eyebrow workspace-page-eyebrow">Test Slot</span>
          <h2 className="workspace-page-title">{slot.title}</h2>
          <p>
            {formatDateTime(slot.start_at)} to {formatDateTime(slot.end_at)}
          </p>
          <p className="slot-live-line">{statusLabel}</p>
        </div>

        <div
          className="assessment-header-metrics dashboard-header-metrics"
          aria-label="Test slot summary"
        >
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
            onClick={() => setShowTestSettings(true)}
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
            if (event.target === event.currentTarget && !slotUpdatePending) {
              closeManageTestModal();
            }
          }}
        >
          <div
            className="test-management-modal test-management-modal-friendly"
            role="dialog"
            aria-modal="true"
            aria-labelledby="test-management-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="test-management-header">
              <div>
                <span>Test slot controls</span>
                <h2 id="test-management-title">{slot.title}</h2>
              </div>
              <button
                type="button"
                className="test-management-close"
                onClick={closeManageTestModal}
                disabled={slotUpdatePending}
                aria-label="Close test slot controls"
              >
                <X size={20} aria-hidden="true" />
              </button>
            </header>

            <div className="test-management-progress" aria-label="Change progress">
              <div className={pendingTestAction ? "is-complete" : "is-active"}>
                <span>1</span>
                <strong>Choose an action</strong>
              </div>
              <div className={pendingTestAction ? "is-active" : ""}>
                <span>2</span>
                <strong>Review and confirm</strong>
              </div>
            </div>

            <div className="test-management-body">
              <section className="test-management-snapshot">
                <div className="test-management-snapshot-status">
                  <div>
                    <HealthDot status={effectiveStatus} />
                    <StatusBadge value={effectiveStatus} />
                  </div>
                  <p>{statusLabel}</p>
                </div>

                <div className="test-control-overview">
                  <div>
                    <CalendarClock size={18} aria-hidden="true" />
                    <span>Starts</span>
                    <strong>{formatDateTime(slot.start_at)}</strong>
                    <em>{slot.timezone_name}</em>
                  </div>
                  <div>
                    <Clock3 size={18} aria-hidden="true" />
                    <span>Ends</span>
                    <strong>{formatDateTime(slot.end_at)}</strong>
                    <em>
                      {effectiveStatus === "active"
                        ? `${formatCountdown(secondsUntilClose)} remaining`
                        : slot.is_accepting_responses
                          ? "Accepting responses"
                          : "Not accepting responses"}
                    </em>
                  </div>
                  <div>
                    <Users size={18} aria-hidden="true" />
                    <span>Candidates</span>
                    <strong>{slot.candidate_count}</strong>
                    <em>{inProgressCount} currently in progress</em>
                  </div>
                  <div>
                    <Timer size={18} aria-hidden="true" />
                    <span>Duration</span>
                    <strong>
                      {slot.duration_minutes || assessment.duration_minutes} minutes
                    </strong>
                    <em>{submittedCount} submitted</em>
                  </div>
                </div>
              </section>

              <section className="test-management-actions-section">
                <div className="test-management-section-heading">
                  <div>
                    <span>Available controls</span>
                    <h3>What would you like to change?</h3>
                  </div>
                  {pendingTestAction ? (
                    <button
                      type="button"
                      onClick={() => setPendingTestAction(null)}
                      disabled={slotUpdatePending}
                    >
                      Change selection
                    </button>
                  ) : null}
                </div>

                <div className="test-management-actions" aria-label="Test controls">
                  <button
                    type="button"
                    className={`test-action-card ${
                      pendingTestAction?.action === "pause" ? "is-selected" : ""
                    } ${canPauseTest ? "" : "is-unavailable"}`}
                    disabled={slotUpdatePending}
                    onClick={() =>
                      requestTestAction(
                        { action: "pause" },
                        canPauseTest
                          ? undefined
                          : effectiveStatus === "paused"
                            ? "This test is already paused. Resume it when candidates can continue."
                            : "This test is already closed, so it cannot be paused.",
                      )
                    }
                  >
                    <span className="test-action-icon">
                      <Pause size={19} aria-hidden="true" />
                    </span>
                    <strong>Pause test</strong>
                    <em>Temporarily stop candidate progress.</em>
                    {!canPauseTest ? <small>Unavailable now</small> : null}
                  </button>

                  <button
                    type="button"
                    className={`test-action-card ${
                      pendingTestAction?.action === "continue" ? "is-selected" : ""
                    } ${canContinueTest ? "" : "is-unavailable"}`}
                    disabled={slotUpdatePending}
                    onClick={() =>
                      requestTestAction(
                        { action: "continue" },
                        canContinueTest
                          ? undefined
                          : "Resume becomes available after this test is paused.",
                      )
                    }
                  >
                    <span className="test-action-icon">
                      <Play size={19} aria-hidden="true" />
                    </span>
                    <strong>Resume test</strong>
                    <em>Continue from every candidate's saved progress.</em>
                    {!canContinueTest ? <small>Available when paused</small> : null}
                  </button>

                  <div
                    className={`test-action-card test-extend-card ${
                      pendingTestAction?.action === "extend" ? "is-selected" : ""
                    } ${canExtendTest ? "" : "is-unavailable"}`}
                  >
                    <span className="test-action-icon">
                      <Timer size={19} aria-hidden="true" />
                    </span>
                    <strong>Extend time</strong>
                    <em>Add more time without interrupting candidates.</em>
                    <div className="test-extension-presets" aria-label="Extension presets">
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
                    <DurationMinutesField
                      label="Custom minutes"
                      value={extendMinutes}
                      minimum={1}
                      maximum={720}
                      onChange={setExtendMinutes}
                    />
                    <p className="test-extension-preview">
                      New end: <strong>{formatDateTime(proposedExtendedEndAt)}</strong>
                    </p>
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={slotUpdatePending}
                      onClick={() =>
                        requestTestAction(
                          {
                            action: "extend",
                            extend_minutes: Math.max(extendMinutes, 1),
                          },
                          canExtendTest
                            ? undefined
                            : "Closed tests cannot be extended from this screen.",
                        )
                      }
                    >
                      Review extension
                    </Button>
                  </div>

                  <button
                    type="button"
                    className={`test-action-card test-action-danger ${
                      pendingTestAction?.action === "close" ? "is-selected" : ""
                    } ${canCloseTest ? "" : "is-unavailable"}`}
                    disabled={slotUpdatePending}
                    onClick={() =>
                      requestTestAction(
                        { action: "close" },
                        canCloseTest
                          ? undefined
                          : "This test is already closed. No further action is needed.",
                      )
                    }
                  >
                    <span className="test-action-icon">
                      <XCircle size={19} aria-hidden="true" />
                    </span>
                    <strong>Close test</strong>
                    <em>Stop accepting candidate responses immediately.</em>
                    {!canCloseTest ? <small>Already closed</small> : null}
                  </button>
                </div>
              </section>

              {pendingTestAction ? (
                <section
                  className={`test-confirm-panel ${
                    pendingTestAction.action === "close" ? "is-danger" : ""
                  }`}
                  aria-live="polite"
                >
                  <span className="test-confirm-icon">
                    <AlertTriangle size={21} aria-hidden="true" />
                  </span>
                  <div>
                    <strong>Confirm this change</strong>
                    <p>You're about to {pendingActionLabel}.</p>
                    <p>{pendingActionImpact}</p>
                  </div>
                  <div className="test-confirm-actions">
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setPendingTestAction(null)}
                      disabled={slotUpdatePending}
                    >
                      Keep current
                    </Button>
                    <Button
                      type="button"
                      className={
                        pendingTestAction.action === "close"
                          ? "test-confirm-danger"
                          : ""
                      }
                      disabled={slotUpdatePending}
                      onClick={() => void confirmTestAction()}
                    >
                      {slotUpdatePending ? "Applying..." : pendingConfirmLabel}
                    </Button>
                  </div>
                </section>
              ) : null}

              {testResponseMessage && testResponseTone === "warning" ? (
                <div className="test-management-alert is-warning" role="alert">
                  <AlertTriangle size={18} aria-hidden="true" />
                  <p>{testResponseMessage}</p>
                  <button
                    type="button"
                    onClick={() => setTestResponseMessage("")}
                    aria-label="Dismiss warning"
                  >
                    <X size={16} aria-hidden="true" />
                  </button>
                </div>
              ) : testResponseMessage ? (
                <p className="test-feedback-message is-success">
                  {testResponseMessage}
                </p>
              ) : null}
              {slotUpdateError ? <p className="form-error">{slotUpdateError}</p> : null}
            </div>
          </div>
        </div>
      ) : null}

      {showTestSettings ? (
        <div
          className="dialog-backdrop test-settings-backdrop"
          onClick={() => setShowTestSettings(false)}
        >
          <Card
            className="test-settings-modal test-settings-modal-friendly"
            role="dialog"
            aria-modal="true"
            aria-labelledby="test-settings-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="settings-modal-header">
              <div>
                <span>Test slot</span>
                <h2 id="test-settings-title">Settings</h2>
              </div>
              <button
                type="button"
                className="test-management-close"
                onClick={() => setShowTestSettings(false)}
                aria-label="Close test settings"
              >
                <X size={20} aria-hidden="true" />
              </button>
            </div>
            <div className="assessment-form-stack slot-edit-form">
              <label className="field">
                <span>Test title</span>
                <input
                  value={editForm.title}
                  onChange={(event) =>
                    setEditForm({ ...editForm, title: event.target.value })
                  }
                />
              </label>
              <section className="slot-schedule-panel" aria-labelledby="edit-slot-schedule-title">
                <div className="slot-schedule-heading">
                  <div>
                    <strong id="edit-slot-schedule-title">Schedule</strong>
                    <span>Times are shown in the selected local region.</span>
                  </div>
                  <label className="field slot-timezone-field">
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
                        setEditForm({
                          ...editForm,
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
                </div>
                <div className="slot-schedule-grid">
                  <FutureDateTimeField
                    label="Start time"
                    value={editForm.start_at}
                    onChange={(startAt) =>
                      setEditForm({
                        ...editForm,
                        start_at: startAt,
                        end_at: addMinutesToLocalInput(
                          startAt,
                          editForm.duration_minutes,
                        ),
                      })
                    }
                  />
                  <DurationMinutesField
                    value={editForm.duration_minutes}
                    onChange={(duration) =>
                      setEditForm({
                        ...editForm,
                        duration_minutes: duration,
                        end_at: addMinutesToLocalInput(editForm.start_at, duration),
                      })
                    }
                  />
                  <FutureDateTimeField
                    label="End time"
                    minimum={minimumEditEnd}
                    value={editForm.end_at}
                    onChange={(endAt) => setEditForm({ ...editForm, end_at: endAt })}
                  />
                </div>
                <p className="slot-schedule-note">
                  End time updates automatically when start or duration changes.
                </p>
              </section>
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

      <div className="test-tab-bar" role="tablist" aria-label="Test sections">
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
            <small>{candidates.length} in this test</small>
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
          items={monitoringItems}
          loading={monitoringLoading}
          connected={monitoringConnected}
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
          assessmentId={assessment.id}
          slotId={slot.id}
          passingScore={assessment.passing_score}
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
