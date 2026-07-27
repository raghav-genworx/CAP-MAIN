import type { ReactNode } from "react";

/**
 * Minimal candidate-only brand mark. No recruiter navigation is ever rendered
 * inside the candidate portal.
 */
export function CandidateBrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`cap-brand ${compact ? "is-compact" : ""}`}>
      <span className="cap-brand-mark" aria-hidden="true">
        CAP
      </span>
      <span className="cap-brand-label">Candidate Assessment Portal</span>
    </span>
  );
}

interface CandidatePageShellProps {
  children: ReactNode;
  /** Optional footer note replacing the default security reassurance line. */
  footnote?: string;
}

/**
 * Restrained centered layout shared by code entry, the lobby, and the
 * completion receipt so all three read as one product.
 */
export function CandidatePageShell({ children, footnote }: CandidatePageShellProps) {
  return (
    <div className="cap-root cap-page">
      <header className="cap-page-header">
        <CandidateBrandMark />
      </header>
      <main className="cap-page-main">{children}</main>
      <footer className="cap-page-footer">
        <p>
          {footnote ||
            "Secure assessment environment. Your assessment link is personal — please do not share it."}
        </p>
      </footer>
    </div>
  );
}
