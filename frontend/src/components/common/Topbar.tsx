import { Bell, ChevronDown, LogOut } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../../features/auth";

export function Topbar() {
  const navigate = useNavigate();
  const { currentUser, logout } = useAuth();
  const displayName = currentUser?.displayName || currentUser?.email || "Recruiter";
  const secondaryLabel =
    currentUser?.displayName && currentUser?.email
      ? currentUser.email
      : "Recruiter workspace";
  const fallbackInitial = displayName.trim().charAt(0).toUpperCase() || "R";

  async function handleLogout() {
    await logout();
    navigate("/recruiter/login", { replace: true });
  }

  return (
    <header className="topbar">
      <Link
        className="topbar-product"
        to="/recruiter/dashboard"
        aria-label="Coding Assessment Platform home"
      >
        <span className="cap-logo topbar-logo" aria-hidden="true">
          <span />
        </span>
        <strong>Coding Assessment Platform</strong>
      </Link>

      <div className="topbar-actions">
        <button
          type="button"
          className="icon-button"
          title="Notifications"
          aria-label="Notifications"
        >
          <Bell size={18} aria-hidden="true" />
        </button>

        <details className="topbar-user-menu">
          <summary aria-label="Open account menu">
            {currentUser?.photoURL ? (
              <img src={currentUser.photoURL} alt="" className="user-avatar" />
            ) : (
              <span className="user-avatar user-avatar-fallback">
                {fallbackInitial}
              </span>
            )}
            <div className="topbar-user-copy">
              <strong>{displayName}</strong>
              <span>{secondaryLabel}</span>
            </div>
            <ChevronDown size={16} aria-hidden="true" />
          </summary>

          <div className="topbar-user-popover" role="menu">
            <div className="topbar-user-popover-copy">
              <strong>{displayName}</strong>
              <span>{secondaryLabel}</span>
            </div>
            <button type="button" onClick={handleLogout} role="menuitem">
              <LogOut size={16} aria-hidden="true" />
              Sign out
            </button>
          </div>
        </details>
      </div>
    </header>
  );
}
