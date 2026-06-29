import type { ReactNode } from "react";

interface EmptyStateProps {
  action?: ReactNode;
  description?: string;
  title: string;
}

export function EmptyState({ action, description, title }: EmptyStateProps) {
  return (
    <div className="empty-state empty-state-panel">
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
      {action ? <div>{action}</div> : null}
    </div>
  );
}
