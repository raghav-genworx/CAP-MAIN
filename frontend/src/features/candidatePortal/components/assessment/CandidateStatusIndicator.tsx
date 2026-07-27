import { AlertTriangle, Check, CloudOff, LoaderCircle, RefreshCw } from "lucide-react";

import type { SaveState } from "./types";
import { formatTimeOfDay } from "../../utils/format";

function describe(state: SaveState) {
  switch (state.kind) {
    case "saving":
      return { icon: LoaderCircle, tone: "is-busy", text: "Saving…", spin: true };
    case "saved": {
      const at = formatTimeOfDay(state.at);
      return {
        icon: Check,
        tone: "is-ok",
        text: at ? `Saved at ${at}` : "Saved",
        spin: false,
      };
    }
    case "error":
      return {
        icon: CloudOff,
        tone: "is-warning",
        text: "Unable to save — retrying",
        spin: false,
      };
    case "conflict":
      return {
        icon: AlertTriangle,
        tone: "is-danger",
        text: "Version conflict — reload required",
        spin: false,
      };
    default:
      return {
        icon: RefreshCw,
        tone: "is-muted",
        text: "Autosaves every 15 seconds",
        spin: false,
      };
  }
}

/**
 * Subtle, always-present autosave and connection state. Announced politely so
 * it never interrupts typing.
 */
export function CandidateStatusIndicator({
  state,
  className = "",
}: {
  state: SaveState;
  className?: string;
}) {
  const { icon: Icon, tone, text, spin } = describe(state);
  const detail =
    state.kind === "error" || state.kind === "conflict" ? state.message : "";

  return (
    <p
      className={`cap-save-state ${tone} ${className}`}
      role="status"
      aria-live="polite"
      title={detail || undefined}
    >
      <Icon size={14} className={spin ? "cap-spin" : ""} aria-hidden="true" />
      <span>{text}</span>
    </p>
  );
}
