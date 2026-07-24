import { Fragment, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { StatusBadge } from "../../../components/common/StatusBadge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { formatDateTime, statusTone } from "../utils/recruiterAssessmentViewModel";
import { assessmentPath, assessmentTestPath } from "../utils/assessmentRoutes";
import type { Assessment } from "../types/Assessment";

interface AssessmentListProps {
  assessments: Assessment[];
  loading: boolean;
  onAddNew: () => void;
}

function HealthDot({ status }: { status: string }) {
  return (
    <span
      aria-label={`${status} status`}
      className={`status-dot status-dot-${statusTone(status)}`}
    />
  );
}

function ListMessage({ children }: { children: string }) {
  return (
    <p aria-live="polite" className="empty-state">
      {children}
    </p>
  );
}

export function AssessmentList({
  assessments,
  loading,
  onAddNew,
}: AssessmentListProps) {
  const navigate = useNavigate();
  const [expandedAssessmentIds, setExpandedAssessmentIds] = useState<Set<string>>(
    () => new Set(),
  );
  const liveCount = assessments.filter((item) => item.status === "live").length;
  const scheduledCount = assessments.filter(
    (item) => item.status === "scheduled",
  ).length;

  function toggleExpanded(assessmentId: string) {
    setExpandedAssessmentIds((current) => {
      const next = new Set(current);
      if (next.has(assessmentId)) {
        next.delete(assessmentId);
      } else {
        next.add(assessmentId);
      }
      return next;
    });
  }

  function shouldIgnoreRowOpen(target: EventTarget | null) {
    return (
      target instanceof HTMLElement &&
      Boolean(target.closest("a, button, input, select, textarea"))
    );
  }

  function openAssessment(assessmentId: string) {
    const found = assessments.find((a) => a.id === assessmentId);
    navigate(assessmentPath(assessmentId, found?.title));
  }

  return (
    <section className="assessment-list-view">
      <Card className="assessment-library-hero workspace-page-header">
        <div>
          <span className="panel-eyebrow workspace-page-eyebrow">Recruiter Workspace</span>
          <h2 className="workspace-page-title">Assessments</h2>
        </div>
        <div className="assessment-hero-metrics dashboard-header-metrics">
          <span>
            <strong>{assessments.length}</strong>
            Total
          </span>
          <span>
            <strong>{liveCount}</strong>
            Live
          </span>
          <span>
            <strong>{scheduledCount}</strong>
            Scheduled
          </span>
          <span>
            <strong>
              {assessments.reduce((sum, item) => sum + item.question_count, 0)}
            </strong>
            Questions
          </span>
        </div>
        <Button type="button" onClick={onAddNew}>
          Add New Assessment
        </Button>
      </Card>

      <Card className="assessment-panel assessment-table-card">
        {loading ? <ListMessage>Loading assessments...</ListMessage> : null}
        {!loading && assessments.length ? (
          <div className="assessment-table-shell">
            <table className="assessment-table">
              <thead>
                <tr>
                  <th>Assessment</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Questions</th>
                  <th>Tests</th>
                  <th>Live</th>
                  <th>Scheduled</th>
                  <th>Passing</th>
                  <th>Updated</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {assessments.map((assessment) => {
                  const visibleTests = assessment.slots.filter((slot) =>
                    ["active", "paused", "scheduled"].includes(
                      slot.effective_status,
                    ),
                  );
                  const expanded = expandedAssessmentIds.has(assessment.id);
                  const testsRegionId = `assessment-tests-${assessment.id}`;
                  return (
                    <Fragment key={assessment.id}>
                      <tr
                        aria-label={`Open ${assessment.title}`}
                        className="assessment-clickable-row"
                        role="button"
                        tabIndex={0}
                        onClick={(event) => {
                          if (shouldIgnoreRowOpen(event.target)) {
                            return;
                          }
                          openAssessment(assessment.id);
                        }}
                        onKeyDown={(event) => {
                          if (shouldIgnoreRowOpen(event.target)) {
                            return;
                          }
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            openAssessment(assessment.id);
                          }
                        }}
                      >
                        <td>
                          <div className="assessment-name-cell">
                            <Link
                              className="entity-link"
                              to={assessmentPath(assessment.id, assessment.title)}
                            >
                              {assessment.title}
                            </Link>
                            <span>
                              {assessment.description || "No description added yet"}
                            </span>
                          </div>
                        </td>
                        <td>
                          <div className="status-with-dot">
                            <HealthDot status={assessment.status} />
                            <StatusBadge value={assessment.status} />
                          </div>
                        </td>
                        <td>{assessment.duration_minutes} min</td>
                        <td>{assessment.question_count}</td>
                        <td>{assessment.test_count}</td>
                        <td>{assessment.live_test_count}</td>
                        <td>{assessment.scheduled_test_count}</td>
                        <td>{assessment.passing_score}%</td>
                        <td>{formatDateTime(assessment.updated_at)}</td>
                        <td>
                          <div className="assessment-row-actions">
                            {visibleTests.length ? (
                              <Button
                                aria-controls={testsRegionId}
                                aria-expanded={expanded}
                                type="button"
                                variant="secondary"
                                onClick={() => toggleExpanded(assessment.id)}
                              >
                                {expanded ? "Hide Tests" : "Show Tests"}
                              </Button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                      {expanded && visibleTests.length ? (
                        <tr className="assessment-test-drop-row">
                          <td colSpan={10}>
                            <div
                              className="assessment-test-dropdown"
                              id={testsRegionId}
                            >
                              {visibleTests.map((slot) => (
                                <article
                                  key={slot.id}
                                  className="assessment-test-mini-card"
                                >
                                  <div>
                                    <Link
                                      className="entity-link"
                                      to={assessmentTestPath(assessment.id, slot.id, assessment.title, slot.title)}
                                    >
                                      {slot.title}
                                    </Link>
                                    <span>
                                      {formatDateTime(slot.start_at)} to{" "}
                                      {formatDateTime(slot.end_at)}
                                    </span>
                                  </div>
                                  <div className="status-with-dot">
                                    <HealthDot status={slot.effective_status} />
                                    <StatusBadge value={slot.effective_status} />
                                  </div>
                                  <span>{slot.candidate_count} candidates</span>
                                  <Link
                                    className="button button-secondary assessment-open-link"
                                    to={assessmentTestPath(assessment.id, slot.id, assessment.title, slot.title)}
                                  >
                                    Open Test
                                  </Link>
                                </article>
                              ))}
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
        {!loading && !assessments.length ? (
          <ListMessage>
            No assessments yet. Create one to start scheduling tests.
          </ListMessage>
        ) : null}
      </Card>
    </section>
  );
}
