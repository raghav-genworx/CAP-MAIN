import { useEffect, useMemo, useState } from "react";
import {
  ListChecks,
  Plus,
  Send,
  Trash2,
  Upload,
  UserPlus,
} from "lucide-react";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import type {
  AssessmentSlot,
  CandidateAssessmentStatus,
  MonitoringCandidate,
  SlotCandidate,
} from "../types/Assessment";
import {
  buildCandidateCsv,
  formatDateTime,
  formatDuration,
  type ManualCandidateRow,
} from "../utils/recruiterAssessmentViewModel";
import {
  EmptyState,
  HealthDot,
  MetricTile,
  StatusBadge,
} from "./AssessmentStatusPrimitives";

type CandidateEntryMode = "csv" | "manual";

function createManualCandidateRow(): ManualCandidateRow {
  return {
    row_id: `candidate-${crypto.randomUUID()}`,
    name: "",
    email: "",
    external_id: "",
  };
}

export function CandidatesTab({
  slot,
  passingScore,
  candidateCsv,
  candidates,
  importPending,
  invitePending,
  importErrors,
  importError,
  inviteError,
  resendPendingId,
  onCsvChange,
  onImport,
  onSendInvites,
  onResend,
}: {
  slot: AssessmentSlot;
  passingScore: number;
  candidateCsv: string;
  candidates: SlotCandidate[];
  importPending: boolean;
  invitePending: boolean;
  importErrors: Array<{ row_number: number; email: string; errors: string[] }>;
  importError: string;
  inviteError: string;
  resendPendingId: string | null;
  onCsvChange: (value: string) => void;
  onImport: (csvText: string) => void;
  onSendInvites: (candidateAssessmentIds?: string[]) => void;
  onResend: (candidateAssessmentId: string) => void;
}) {
  const [entryMode, setEntryMode] = useState<CandidateEntryMode>("manual");
  const [showCandidateEntry, setShowCandidateEntry] = useState(false);
  const [manualRows, setManualRows] = useState<ManualCandidateRow[]>([
    createManualCandidateRow(),
  ]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<string>>(
    () => new Set(),
  );

  useEffect(() => {
    const visibleCandidateIds = new Set(
      candidates.map((candidate) => candidate.candidate_assessment_id),
    );
    setSelectedCandidateIds((current) => {
      const next = new Set(
        [...current].filter((candidateId) => visibleCandidateIds.has(candidateId)),
      );
      return next.size === current.size ? current : next;
    });
  }, [candidates]);

  const manualCsv = useMemo(() => buildCandidateCsv(manualRows), [manualRows]);
  const manualHasRows = manualRows.some(
    (row) => row.name.trim() || row.email.trim() || row.external_id.trim(),
  );
  const selectedIds = [...selectedCandidateIds];
  const allSelected = Boolean(candidates.length) && selectedIds.length === candidates.length;

  function updateManualRow(
    rowId: string,
    field: keyof Omit<ManualCandidateRow, "row_id">,
    value: string,
  ) {
    setManualRows((current) =>
      current.map((row) => (row.row_id === rowId ? { ...row, [field]: value } : row)),
    );
  }

  function removeManualRow(rowId: string) {
    setManualRows((current) =>
      current.length === 1
        ? [createManualCandidateRow()]
        : current.filter((row) => row.row_id !== rowId),
    );
  }

  function toggleCandidateSelection(candidateAssessmentId: string, checked: boolean) {
    setSelectedCandidateIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(candidateAssessmentId);
      } else {
        next.delete(candidateAssessmentId);
      }
      return next;
    });
  }

  function toggleAllCandidates(checked: boolean) {
    setSelectedCandidateIds(
      checked
        ? new Set(candidates.map((candidate) => candidate.candidate_assessment_id))
        : new Set(),
    );
  }

  return (
    <section
      className={[
        "assessment-console",
        "candidates-console",
        showCandidateEntry ? "is-adding-candidate" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <Card className="assessment-panel candidates-list-card">
        <div className="panel-heading candidates-list-heading">
          <div>
            <span>Candidate List</span>
            <h2>{candidates.length} candidates</h2>
          </div>
          <div className="candidate-invite-actions">
            <Button
              type="button"
              className="candidate-action-add"
              variant={candidates.length ? "secondary" : "primary"}
              onClick={() => setShowCandidateEntry(true)}
              disabled={showCandidateEntry}
            >
              <UserPlus size={16} aria-hidden="true" />
              Add Candidate
            </Button>
            <Button
              type="button"
              className="candidate-action-send-all"
              disabled={invitePending || candidates.length === 0}
              onClick={() => onSendInvites()}
            >
              <Send size={16} aria-hidden="true" />
              {invitePending ? "Sending..." : "Send invites"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              className={
                selectedIds.length
                  ? "candidate-action-send-selected is-ready"
                  : "candidate-action-send-selected"
              }
              disabled={invitePending || selectedIds.length === 0}
              onClick={() => onSendInvites(selectedIds)}
            >
              <ListChecks size={16} aria-hidden="true" />
              Send selected ({selectedIds.length})
            </Button>
          </div>
        </div>
        <CandidateTable
          candidates={candidates}
          passingScore={passingScore}
          resendPendingId={resendPendingId}
          selectedCandidateIds={selectedCandidateIds}
          allSelected={allSelected}
          onToggleAll={toggleAllCandidates}
          onToggleCandidate={toggleCandidateSelection}
          onResend={onResend}
        />
      </Card>

      {showCandidateEntry ? (
        <Card className="assessment-panel candidate-import-card candidate-import-popup">
          <div className="panel-heading">
            <div>
              <span>Candidate Setup</span>
              <h2>Add candidates</h2>
            </div>
            <div className="assessment-row-actions">
              <StatusBadge value={slot.status} />
              <Button
                type="button"
                variant="secondary"
                onClick={() => setShowCandidateEntry(false)}
              >
                Close
              </Button>
            </div>
          </div>
          <div className="candidate-entry-tabs">
            <button
              type="button"
              className={entryMode === "manual" ? "is-active" : ""}
              onClick={() => setEntryMode("manual")}
            >
              Individual candidate
            </button>
            <button
              type="button"
              className={entryMode === "csv" ? "is-active" : ""}
              onClick={() => setEntryMode("csv")}
            >
              Group upload
            </button>
          </div>

          {entryMode === "manual" ? (
            <div className="candidate-entry-panel">
              <p className="assessment-context-banner">
                Add candidates one by one. External ID is optional and useful for
                college roll numbers or HR IDs.
              </p>
              <div className="manual-candidate-list">
                {manualRows.map((row, index) => (
                  <div className="manual-candidate-row" key={row.row_id}>
                    <div className="manual-candidate-row-heading">
                      <strong>Candidate {index + 1}</strong>
                      <button
                        type="button"
                        className="manual-candidate-delete"
                        onClick={() => removeManualRow(row.row_id)}
                        title={`Remove candidate ${index + 1}`}
                        aria-label={`Remove candidate ${index + 1}`}
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </button>
                    </div>
                    <label className="field">
                      <span>Name</span>
                      <input
                        placeholder={`Candidate ${index + 1}`}
                        value={row.name}
                        onChange={(event) =>
                          updateManualRow(row.row_id, "name", event.target.value)
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Email</span>
                      <input
                        type="email"
                        placeholder="candidate@example.com"
                        value={row.email}
                        onChange={(event) =>
                          updateManualRow(row.row_id, "email", event.target.value)
                        }
                      />
                    </label>
                    <label className="field">
                      <span>External ID</span>
                      <input
                        placeholder="Optional"
                        value={row.external_id}
                        onChange={(event) =>
                          updateManualRow(
                            row.row_id,
                            "external_id",
                            event.target.value,
                          )
                        }
                      />
                    </label>
                  </div>
                ))}
              </div>
              <div className="assessment-actions-row candidate-entry-actions">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() =>
                    setManualRows((current) => [...current, createManualCandidateRow()])
                  }
                >
                  <Plus size={16} aria-hidden="true" />
                  Add another
                </Button>
                <Button
                  type="button"
                  onClick={() => onImport(manualCsv)}
                  disabled={importPending || !manualHasRows}
                >
                  <Upload size={16} aria-hidden="true" />
                  {importPending ? "Importing..." : "Import candidates"}
                </Button>
              </div>
            </div>
          ) : (
            <div className="candidate-entry-panel">
              <p className="assessment-context-banner">
                Use columns: name, email, external_id. You can upload a CSV file or
                paste rows below.
              </p>
              <label className="candidate-upload-dropzone">
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (!file) {
                      return;
                    }
                    void file.text().then((text) => onCsvChange(text));
                    event.target.value = "";
                  }}
                />
                <strong>Upload CSV</strong>
                <span>or paste/edit the same content below</span>
              </label>
              <textarea
                className="candidate-csv-box"
                value={candidateCsv}
                onChange={(event) => onCsvChange(event.target.value)}
              />
              <div className="assessment-actions-row">
                <Button
                  type="button"
                  onClick={() => onImport(candidateCsv)}
                  disabled={importPending || !candidateCsv.trim()}
                >
                  <Upload size={16} aria-hidden="true" />
                  {importPending ? "Importing..." : "Import group"}
                </Button>
              </div>
            </div>
          )}

          {importError ? <p className="form-error">{importError}</p> : null}
          {inviteError ? <p className="form-error">{inviteError}</p> : null}
          {importErrors.length ? (
            <div className="import-error-list">
              {importErrors.map((error) => (
                <p key={`${error.row_number}-${error.email}`}>
                  Row {error.row_number}: {error.errors.join(", ")}
                </p>
              ))}
            </div>
          ) : null}
        </Card>
      ) : null}
    </section>
  );
}

function CandidateTable({
  candidates,
  passingScore,
  resendPendingId,
  selectedCandidateIds,
  allSelected,
  onToggleAll,
  onToggleCandidate,
  onResend,
}: {
  candidates: SlotCandidate[];
  passingScore: number;
  resendPendingId: string | null;
  selectedCandidateIds: Set<string>;
  allSelected: boolean;
  onToggleAll: (checked: boolean) => void;
  onToggleCandidate: (candidateAssessmentId: string, checked: boolean) => void;
  onResend: (candidateAssessmentId: string) => void;
}) {
  if (!candidates.length) {
    return <EmptyState label="Imported candidates for this test slot will appear here." />;
  }

  return (
    <div className="assessment-table-shell">
      <table className="assessment-table compact-table">
        <thead>
          <tr>
            <th className="candidate-select-cell">
              <input
                type="checkbox"
                aria-label="Select all candidates"
                checked={allSelected}
                onChange={(event) => onToggleAll(event.target.checked)}
              />
            </th>
            <th>Candidate</th>
            <th>Invite</th>
            <th>Assessment</th>
            <th>Activity</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => {
            const resultStatus = candidate.percentage === null
              ? null
              : candidate.percentage >= passingScore
                ? "passed"
                : "failed";
            return (
              <tr key={candidate.candidate_assessment_id}>
              <td className="candidate-select-cell">
                <input
                  type="checkbox"
                  aria-label={`Select ${candidate.name}`}
                  checked={selectedCandidateIds.has(
                    candidate.candidate_assessment_id,
                  )}
                  onChange={(event) =>
                    onToggleCandidate(
                      candidate.candidate_assessment_id,
                      event.target.checked,
                    )
                  }
                />
              </td>
              <td>
                <div className="assessment-name-cell">
                  <strong>{candidate.name}</strong>
                  <span>{candidate.email}</span>
                </div>
              </td>
              <td>
                <StatusBadge value={candidate.invite_status} />
              </td>
              <td>
                <div className="status-with-dot">
                  <HealthDot status={resultStatus ?? candidate.assessment_status} />
                  <StatusBadge value={resultStatus ?? candidate.assessment_status} />
                  {candidate.percentage !== null ? (
                    <small>{Math.round(candidate.percentage)}%</small>
                  ) : null}
                </div>
              </td>
              <td>{formatDateTime(candidate.last_activity_at)}</td>
              <td>
                {(() => {
                  const canResend =
                    candidate.invite_status === "sent" ||
                    candidate.invite_status === "failed";
                  const isSending =
                    resendPendingId === candidate.candidate_assessment_id;
                  return (
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={isSending || !canResend}
                      title={
                        canResend
                          ? "Send this invite again"
                          : "Resend is available after the first send attempt."
                      }
                      onClick={() => onResend(candidate.candidate_assessment_id)}
                    >
                      {isSending ? "Sending..." : "Resend"}
                    </Button>
                  );
                })()}
              </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function LiveMonitoringTab({
  items,
  loading,
  connected,
  liveSummary,
}: {
  items: MonitoringCandidate[];
  loading: boolean;
  connected: boolean;
  liveSummary?: {
    isLive: boolean;
    statusLabel: string;
    secondsUntilClose: number;
    inProgressCount: number;
    submittedCount: number;
    candidateCount: number;
  };
}) {
  const statusCounts = items.reduce(
    (counts, item) => ({
      ...counts,
      [item.status]: (counts[item.status] || 0) + 1,
    }),
    {} as Record<CandidateAssessmentStatus, number>,
  );

  return (
    <Card className="assessment-panel assessment-panel-wide">
      <div className="panel-heading">
        <div>
          <span>Live Monitoring</span>
          <h2>Candidate Activity</h2>
        </div>
        <strong>
          {connected ? "Live stream connected" : "Reconnecting · 15s fallback"}
        </strong>
      </div>

      {liveSummary?.isLive ? (
        <div className="live-monitoring-bar" role="status" aria-live="polite">
          <div className="live-monitoring-pulse">
            <span />
            <strong>Live test running</strong>
          </div>
          <div className="live-monitoring-copy">
            <strong>{liveSummary.statusLabel}</strong>
            <span>
              {liveSummary.inProgressCount} active · {liveSummary.submittedCount} submitted ·{" "}
              {liveSummary.candidateCount} candidates
            </span>
          </div>
          <div className="live-monitoring-countdown">
            <strong>{formatDuration(liveSummary.secondsUntilClose)}</strong>
            <span>remaining</span>
          </div>
        </div>
      ) : null}

      <div className="monitoring-status-strip">
        <MetricTile label="Not started" value={statusCounts.not_started || 0} />
        <MetricTile label="In progress" value={statusCounts.in_progress || 0} />
        <MetricTile label="Submitted" value={(statusCounts.submitted || 0) + (statusCounts.auto_submitted || 0)} />
      </div>

      {loading ? <EmptyState label="Loading live activity..." /> : null}
      {!loading && items.length ? (
        <div className="assessment-table-shell">
          <table className="assessment-table compact-table">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Status</th>
                <th>Current Q</th>
                <th>Questions touched</th>
                <th>Hidden checks</th>
                <th>Time left</th>
                <th>Submit reason</th>
              </tr>
            </thead>
            <tbody>
              {items.map((candidate) => (
                <tr key={candidate.candidate_assessment_id}>
                  <td>
                    <div className="assessment-name-cell">
                      <strong>{candidate.name}</strong>
                      <span>{candidate.email}</span>
                    </div>
                  </td>
                  <td>
                    <div className="status-with-dot">
                      <HealthDot status={candidate.status} />
                      <StatusBadge value={candidate.status} />
                    </div>
                  </td>
                  <td>Q{candidate.current_question_order || "-"}</td>
                  <td>{candidate.questions_attempted}</td>
                  <td>{candidate.hidden_checks_used}</td>
                  <td>{formatDuration(candidate.time_remaining_seconds)}</td>
                  <td>
                    {candidate.submission_tag ? (
                      <div className="assessment-name-cell">
                        <strong>{candidate.submission_tag}</strong>
                        <span>{candidate.submission_message || "Auto submit"}</span>
                      </div>
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {!loading && !items.length ? (
        <EmptyState label="Live activity appears after candidates open their invite links." />
      ) : null}
    </Card>
  );
}
