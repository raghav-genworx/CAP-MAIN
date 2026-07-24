import { Bell, Info } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { FormField } from "../../../components/common/FormField";
import { useAuth } from "../../auth";
import {
  useNotificationSettings,
  useUpdateNotificationSettings,
} from "../hooks/useNotifications";
import type { NotificationMode } from "../types/Notification";

const MODE_OPTIONS: { value: NotificationMode; label: string }[] = [
  { value: "per_candidate", label: "Notify for every candidate" },
  { value: "milestone", label: "Notify at milestones" },
  { value: "one_per_test", label: "One grouped notification per test slot" },
];

const PRESET_MILESTONES = [10, 25, 50, 75, 90, 100];

export function NotificationPreferences() {
  const { currentUser } = useAuth();
  const settingsQuery = useNotificationSettings(currentUser);
  const updateSettings = useUpdateNotificationSettings(currentUser);

  const [submissionMode, setSubmissionMode] =
    useState<NotificationMode>("milestone");
  const [evaluationMode, setEvaluationMode] =
    useState<NotificationMode>("milestone");
  const [milestones, setMilestones] = useState<number[]>([25, 50, 75, 100]);
  const [enableSubmission, setEnableSubmission] = useState(true);
  const [enableEvaluation, setEnableEvaluation] = useState(true);
  const [enableReportReady, setEnableReportReady] = useState(true);
  const [saved, setSaved] = useState(false);

  const settings = settingsQuery.data;
  useEffect(() => {
    if (!settings) {
      return;
    }
    setSubmissionMode(settings.submission_notification_mode);
    setEvaluationMode(settings.evaluation_notification_mode);
    setMilestones(settings.milestone_percentages);
    setEnableSubmission(settings.enable_submission_notifications);
    setEnableEvaluation(settings.enable_evaluation_notifications);
    setEnableReportReady(settings.enable_report_ready_notification);
  }, [settings]);

  const milestoneChoices = useMemo(() => {
    const merged = new Set<number>([...PRESET_MILESTONES, ...milestones]);
    return Array.from(merged).sort((a, b) => a - b);
  }, [milestones]);

  const milestonesRelevant =
    submissionMode === "milestone" || evaluationMode === "milestone";
  const milestoneError = milestonesRelevant && milestones.length === 0;

  function toggleMilestone(value: number) {
    setSaved(false);
    setMilestones((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value].sort((a, b) => a - b),
    );
  }

  async function handleSave() {
    if (milestoneError) {
      return;
    }
    await updateSettings.mutateAsync({
      submission_notification_mode: submissionMode,
      evaluation_notification_mode: evaluationMode,
      milestone_percentages: [...milestones].sort((a, b) => a - b),
      enable_submission_notifications: enableSubmission,
      enable_evaluation_notifications: enableEvaluation,
      enable_report_ready_notification: enableReportReady,
    });
    setSaved(true);
  }

  return (
    <section className="settings-panel notification-preferences">
      <div className="settings-panel-heading">
        <Bell size={18} aria-hidden="true" />
        <h2>Notification preferences</h2>
      </div>

      <p className="settings-panel-subtitle">
        Choose how the dashboard notifies you as candidates submit and get
        evaluated.
      </p>

      {settingsQuery.isError ? (
        <p className="notification-load-error">
          Could not load your saved notification preferences.
        </p>
      ) : null}

      <div className="settings-form-grid">
        <FormField
          kind="select"
          label="Submission notifications"
          selectProps={{
            value: submissionMode,
            onChange: (event) => {
              setSaved(false);
              setSubmissionMode(event.target.value as NotificationMode);
            },
            disabled: !enableSubmission || settingsQuery.isLoading,
          }}
        >
          {MODE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </FormField>

        <FormField
          kind="select"
          label="Evaluation notifications"
          selectProps={{
            value: evaluationMode,
            onChange: (event) => {
              setSaved(false);
              setEvaluationMode(event.target.value as NotificationMode);
            },
            disabled: !enableEvaluation || settingsQuery.isLoading,
          }}
        >
          {MODE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </FormField>
      </div>

      {milestonesRelevant ? (
        <div className="milestone-config">
          <span className="milestone-config-label">Milestone percentages</span>
          <div className="milestone-chips">
            {milestoneChoices.map((value) => {
              const active = milestones.includes(value);
              return (
                <button
                  key={value}
                  type="button"
                  className={`milestone-chip${active ? " is-active" : ""}`}
                  aria-pressed={active}
                  onClick={() => toggleMilestone(value)}
                >
                  {value}%
                </button>
              );
            })}
          </div>
          {milestoneError ? (
            <em className="milestone-error">Select at least one milestone.</em>
          ) : null}
        </div>
      ) : null}

      <div className="notification-toggles">
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={enableSubmission}
            onChange={(event) => {
              setSaved(false);
              setEnableSubmission(event.target.checked);
            }}
          />
          <span>Notify me about candidate submissions</span>
        </label>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={enableEvaluation}
            onChange={(event) => {
              setSaved(false);
              setEnableEvaluation(event.target.checked);
            }}
          />
          <span>Notify me about candidate evaluations</span>
        </label>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={enableReportReady}
            onChange={(event) => {
              setSaved(false);
              setEnableReportReady(event.target.checked);
            }}
          />
          <span>Notify me when an assessment report is ready</span>
        </label>
      </div>

      <div className="notification-recommendation">
        <Info size={15} aria-hidden="true" />
        <span>
          For large assessments, milestone or grouped notifications prevent a
          flooded inbox while keeping progress visible.
        </span>
      </div>

      <div className="notification-actions">
        {saved && !updateSettings.isPending ? (
          <span className="notification-saved">Preferences saved.</span>
        ) : null}
        {updateSettings.isError ? (
          <span className="notification-save-error">
            Could not save preferences. Try again.
          </span>
        ) : null}
        <button
          type="button"
          className="button button-primary"
          onClick={() => void handleSave()}
          disabled={
            settingsQuery.isLoading ||
            settingsQuery.isError ||
            updateSettings.isPending ||
            milestoneError
          }
        >
          {updateSettings.isPending ? "Saving…" : "Save preferences"}
        </button>
      </div>
    </section>
  );
}
