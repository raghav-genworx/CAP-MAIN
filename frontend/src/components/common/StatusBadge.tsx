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
  not_passed: "warning",
  passed: "success",
  published: "success",
  revoked: "danger",
  scheduled: "info",
  submitted: "success",
};

function formatStatus(value: string) {
  if (value.toLowerCase() === "active") {
    return "Live";
  }

  return value.replaceAll("_", " ");
}

function isLiveStatus(value: string) {
  return ["active", "live"].includes(value.toLowerCase());
}

function statusTone(value: string): StatusTone {
  return STATUS_TONES[value.toLowerCase()] || "neutral";
}

export function StatusBadge({ value }: { value: string }) {
  const tone = statusTone(value);

  return (
    <span
      className={[
        "status-badge",
        `status-${tone}`,
        isLiveStatus(value) ? "is-live-status" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {formatStatus(value)}
    </span>
  );
}
