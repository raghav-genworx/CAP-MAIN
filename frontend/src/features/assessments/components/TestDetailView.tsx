import { useEffect, useState } from "react";
import { BadgeCheck, BarChart3, Gauge, Settings } from "lucide-react";

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
  const minimumEditStart = nextAvailableTimeInput(
    editForm.timezone_name,
    editForm.timezone_offset_minutes,
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
      if (new Date(startAt).getTime() < Date.now()) {
        throw new Error("Past times are unavailable. Choose a future start time.");
      }
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
    <section className="assessment-drilldown">
      <div className="assessment-breadcrumb">
        <button type="button" onClick={onBack}>
          Back to tests
        </button>
        <span>/</span>
        <strong>{assessment.title}</strong>
        <span>/</span>
        <strong>{slot.title}</strong>
      </div>

      <Card className="assessment-panel assessment-command-center test-command-center">
        <div className="assessment-command-main">
          <div>
            <span className="panel-eyebrow">Test Session</span>
            <h2>{slot.title}</h2>
            <p>
              {formatDateTime(slot.start_at)} to {formatDateTime(slot.end_at)}
            </p>
            <p className="slot-live-line">{statusLabel}</p>
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
              title="Test settings"
            >
              <Settings size={18} aria-hidden="true" />
              <span className="sr-only">Test settings</span>
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsManagingTest(true)}
            >
              Manage Test
            </Button>
          </div>
        </div>

        <div className="assessment-hero-metrics assessment-command-metrics">
          <span>
            <strong>{slot.candidate_count}</strong>
            Candidates
          </span>
          <span>
            <strong>{inProgressCount}</strong>
            In progress
          </span>
          <span>
            <strong>{submittedCount}</strong>
            Submitted
          </span>
          <span>
            <strong>{slot.duration_minutes || assessment.duration_minutes}m</strong>
            Duration
          </span>
        </div>
      </Card>

      {!isManagingTest && testResponseMessage ? (
        <p className={`test-feedback-message is-${testResponseTone}`}>
          {testResponseMessage}
        </p>
      ) : null}

      {isManagingTest ? (
        <div className="dialog-backdrop">
          <div className="test-management-modal" role="dialog" aria-modal="true">
            <div className="panel-heading">
              <div>
                <span>Manage Test</span>
                <h2>{slot.title}</h2>
                <p>
                  Review the current test window, choose one action, then confirm
                  before the change is applied.
                </p>
              </div>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setIsManagingTest(false);
                  setPendingTestAction(null);
                  setTestResponseMessage("");
                }}
              >
                Close
              </Button>
            </div>

            <div className="test-control-overview">
              <div>
                <span>Current status</span>
                <strong>{effectiveStatus.replace("_", " ")}</strong>
                <em>{statusLabel}</em>
              </div>
              <div>
                <span>Start time</span>
                <strong>{formatDateTime(slot.start_at)}</strong>
                <em>{slot.timezone_name}</em>
              </div>
              <div>
                <span>End time</span>
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
                <span>After extension</span>
                <strong>{formatDateTime(proposedExtendedEndAt)}</strong>
                <em>Based on +{Math.max(extendMinutes, 1)} minutes</em>
              </div>
            </div>

            <div className="test-management-actions" aria-label="Test controls">
              <button
                type="button"
                className={`test-action-card ${canPauseTest ? "" : "is-unavailable"}`}
                disabled={slotUpdatePending}
                onClick={() =>
                  requestTestAction(
                    { action: "pause" },
                    canPauseTest
                      ? undefined
                      : effectiveStatus === "paused"
                        ? "This test is already paused. Use Continue Test when candidates can resume."
                        : "This test is already closed, so it cannot be paused.",
                  )
                }
              >
                <span>Pause</span>
                <strong>Pause Test</strong>
                <em>
                  {canPauseTest
                    ? "Temporarily block candidate progress."
                    : "Not available for the current status."}
                </em>
              </button>
              <button
                type="button"
                className={`test-action-card ${canContinueTest ? "" : "is-unavailable"}`}
                disabled={slotUpdatePending}
                onClick={() =>
                  requestTestAction(
                    { action: "continue" },
                    canContinueTest
                      ? undefined
                      : "Continue becomes available only after this test is paused.",
                  )
                }
              >
                <span>Resume</span>
                <strong>Continue Test</strong>
                <em>
                  {canContinueTest
                    ? "Let candidates continue from saved progress."
                    : "Available only while paused."}
                </em>
              </button>
              <div className={`test-action-card test-extend-card ${canExtendTest ? "" : "is-unavailable"}`}>
                <span>Extend</span>
                <strong>Extend Time</strong>
                <label>
                  <small>Minutes</small>
                  <input
                    type="number"
                    min={1}
                    max={720}
                    value={extendMinutes}
                    onChange={(event) => setExtendMinutes(Number(event.target.value))}
                  />
                </label>
                <em>New end: {formatDateTime(proposedExtendedEndAt)}</em>
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
                        : "This test is closed. Reopening closed tests is not supported in this flow.",
                    )
                  }
                >
                  Prepare extension
                </Button>
              </div>
              <button
                type="button"
                className={`test-action-card test-action-danger ${canCloseTest ? "" : "is-unavailable"
                  }`}
                disabled={slotUpdatePending}
                onClick={() =>
                  requestTestAction(
                    { action: "close" },
                    canCloseTest
                      ? undefined
                      : "This test is already closed. No further close action is needed.",
                  )
                }
              >
                <span>Close</span>
                <strong>Close Test</strong>
                <em>
                  {canCloseTest
                    ? "Stop accepting candidate responses now."
                    : "Already closed."}
                </em>
              </button>
            </div>

            {pendingTestAction ? (
              <div className="test-confirm-panel">
                <div>
                  <strong>Confirm action</strong>
                  <p>Are you sure you want to {pendingActionLabel}?</p>
                  <p>{pendingActionImpact}</p>
                </div>
                <div className="assessment-row-actions">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setPendingTestAction(null)}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="button"
                    disabled={slotUpdatePending}
                    onClick={() => void confirmTestAction()}
                  >
                    {slotUpdatePending ? "Applying..." : "Confirm"}
                  </Button>
                </div>
              </div>
            ) : null}
            {testResponseMessage && testResponseTone === "warning" ? (
              <div className="question-flow-toast-stack" aria-live="assertive">
                <div className="question-flow-toast is-warning" role="alert">
                  <div><strong>Schedule warning</strong><p>{testResponseMessage}</p></div>
                  <button type="button" className="question-flow-toast-dismiss" onClick={() => setTestResponseMessage("")}>Close</button>
                </div>
              </div>
            ) : testResponseMessage ? (
              <p className="test-feedback-message is-success">{testResponseMessage}</p>
            ) : null}
            {slotUpdateError ? <p className="form-error">{slotUpdateError}</p> : null}
          </div>
        </div>
      ) : null}

      {showTestSettings ? (
        <div className="dialog-backdrop" onClick={() => setShowTestSettings(false)}>
          <Card
            className="test-settings-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="test-settings-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="settings-modal-header">
              <div>
                <span>Settings</span>
                <h2 id="test-settings-title">Test settings</h2>
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
                <span>Test title</span>
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
                <label className="field">
                  <span>Start time</span>
                  <input
                    type="datetime-local"
                    min={minimumEditStart}
                    value={editForm.start_at}
                    onChange={(event) => {
                      const startAt = event.target.value;
                      setEditForm({
                        ...editForm,
                        start_at: startAt,
                        end_at: addMinutesToLocalInput(
                          startAt,
                          editForm.duration_minutes,
                        ),
                      });
                    }}
                  />
                </label>
                <label className="field">
                  <span>Test duration (minutes)</span>
                  <input
                    type="number"
                    min={15}
                    max={360}
                    value={editForm.duration_minutes}
                    onChange={(event) => {
                      const duration = Math.max(15, Number(event.target.value) || 15);
                      setEditForm({
                        ...editForm,
                        duration_minutes: duration,
                        end_at: addMinutesToLocalInput(editForm.start_at, duration),
                      });
                    }}
                  />
                </label>
                <label className="field">
                  <span>End time</span>
                  <input
                    type="datetime-local"
                    min={minimumEditEnd}
                    value={editForm.end_at}
                    onChange={(event) =>
                      setEditForm({ ...editForm, end_at: event.target.value })
                    }
                  />
                </label>
              </div>
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
