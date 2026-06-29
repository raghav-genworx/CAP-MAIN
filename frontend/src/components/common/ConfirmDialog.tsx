import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "../ui/Button";

interface ConfirmDialogProps {
  body: ReactNode;
  confirmLabel?: string;
  onCancel: () => void;
  onConfirm: () => void;
  open: boolean;
  title: string;
}

export function ConfirmDialog({
  body,
  confirmLabel = "Confirm",
  onCancel,
  onConfirm,
  open,
  title,
}: ConfirmDialogProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="confirm-dialog" role="dialog" aria-modal="true" aria-label={title}>
        <div className="confirm-dialog-icon">
          <AlertTriangle size={18} aria-hidden="true" />
        </div>
        <div>
          <h2>{title}</h2>
          <p>{body}</p>
        </div>
        <div className="confirm-dialog-actions">
          <Button type="button" variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </section>
    </div>
  );
}
