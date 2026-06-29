import { Bell } from "lucide-react";

export function Topbar() {
  return (
    <header className="topbar">
      <div className="topbar-product" aria-label="Coding Assessment Platform">
        <span className="cap-logo topbar-logo" aria-hidden="true">
          <span />
        </span>
        <strong>Coding Assessment Platform</strong>
      </div>

      <button
        type="button"
        className="icon-button"
        title="Notifications"
        aria-label="Notifications"
      >
        <Bell size={18} aria-hidden="true" />
      </button>
    </header>
  );
}
