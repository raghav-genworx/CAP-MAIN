import {
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
} from "lucide-react";
import type { ReactNode } from "react";

export type ToastTone = "warning" | "error" | "success" | "info";

interface ToastNotificationProps {
  title: string;
  message: ReactNode;
  tone?: ToastTone;
  onClose: () => void;
  live?: "polite" | "assertive" | "off";
}

const TONE_ICON = {
  warning: AlertTriangle,
  error: AlertTriangle,
  success: CheckCircle2,
  info: Info,
} as const;

export function ToastNotification({
  title,
  message,
  tone = "warning",
  onClose,
  live = "assertive",
}: ToastNotificationProps) {
  const Icon = TONE_ICON[tone];

  return (
    <div
      className="question-flow-toast-stack"
      aria-live={live}
      aria-label="Notifications"
    >
      <div className={`question-flow-toast is-${tone}`} role="alert">
        <div className="question-flow-toast-icon" aria-hidden="true">
          <Icon size={22} strokeWidth={2.4} />
        </div>
        <div className="question-flow-toast-copy">
          <strong>{title}</strong>
          {typeof message === "string" ? <p>{message}</p> : message}
        </div>
        <button
          type="button"
          className="question-flow-toast-dismiss"
          onClick={onClose}
          aria-label="Dismiss notification"
          title="Close"
        >
          <X size={20} strokeWidth={2.6} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

interface ToastStackProps {
  children: ReactNode;
  live?: "polite" | "assertive" | "off";
  label?: string;
}

export function ToastStack({
  children,
  live = "polite",
  label = "Notifications",
}: ToastStackProps) {
  return (
    <div
      className="question-flow-toast-stack"
      aria-live={live}
      aria-label={label}
    >
      {children}
    </div>
  );
}

interface ToastItemProps {
  title: string;
  message: ReactNode;
  tone?: ToastTone;
  onClose: () => void;
}

export function ToastItem({
  title,
  message,
  tone = "warning",
  onClose,
}: ToastItemProps) {
  const Icon = TONE_ICON[tone];

  return (
    <div className={`question-flow-toast is-${tone}`} role="alert">
      <div className="question-flow-toast-icon" aria-hidden="true">
        <Icon size={22} strokeWidth={2.4} />
      </div>
      <div className="question-flow-toast-copy">
        <strong>{title}</strong>
        {typeof message === "string" ? <p>{message}</p> : message}
      </div>
      <button
        type="button"
        className="question-flow-toast-dismiss"
        onClick={onClose}
        aria-label="Dismiss notification"
        title="Close"
      >
        <X size={20} strokeWidth={2.6} aria-hidden="true" />
      </button>
    </div>
  );
}
