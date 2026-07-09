import { statusTone } from "../utils/recruiterAssessmentViewModel";

function isLiveStatus(value: string) {
  return ["active", "live"].includes(value.toLowerCase());
}

function formatStatus(value: string) {
  if (value.toLowerCase() === "active") {
    return "Live";
  }

  return value.replaceAll("_", " ");
}

export function StatusBadge({ value }: { value: string }) {
  return (
    <span
      className={[
        "status-badge",
        `status-${statusTone(value)}`,
        isLiveStatus(value) ? "is-live-status" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {formatStatus(value)}
    </span>
  );
}

export function HealthDot({ status }: { status: string }) {
  return (
    <span
      aria-label={`${status} status`}
      className={[
        "status-dot",
        `status-dot-${statusTone(status)}`,
        isLiveStatus(status) ? "is-live-status" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    />
  );
}

export function EmptyState({ label }: { label: string }) {
  return <p className="empty-state">{label}</p>;
}

export function MetricTile({
  label,
  value,
}: {
  label: string;
  value: number | string;
}) {
  return (
    <div className="assessment-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
