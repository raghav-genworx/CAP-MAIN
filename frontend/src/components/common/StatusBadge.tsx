type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

const STATUS_TONES: Record<string, StatusTone> = {
  active: "success",
  archived: "neutral",
  available: "neutral",
  auto_submitted: "success",
  completed: "success",
  draft: "neutral",
  evaluating: "warning",
  failed: "danger",
  in_progress: "info",
  live: "success",
  passed: "success",
  published: "success",
  revoked: "danger",
  scheduled: "info",
  submitted: "success",
};

function formatStatus(value: string) {
  return value.replaceAll("_", " ");
}

function statusTone(value: string): StatusTone {
  return STATUS_TONES[value.toLowerCase()] || "neutral";
}

export function StatusBadge({ value }: { value: string }) {
  const tone = statusTone(value);

  return (
    <span className={`status-badge status-${tone}`}>
      {formatStatus(value)}
    </span>
  );
}
