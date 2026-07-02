import {
  ClipboardList,
  FileQuestion,
  Gauge,
  LogOut,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";

import { APP_NAME, NAVIGATION_ITEMS } from "../../config/constants";
import { useAuth } from "../../features/auth";

const ICONS: Record<(typeof NAVIGATION_ITEMS)[number]["icon"], LucideIcon> = {
  assessments: ClipboardList,
  dashboard: Gauge,
  questions: FileQuestion,
  settings: Settings,
};

export function Sidebar() {
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
    <aside className="sidebar" aria-label="Recruiter navigation">
      <div className="sidebar-header">
        <div className="sidebar-brand" aria-label={APP_NAME}>
          <span className="cap-logo" aria-hidden="true">
            <span />
          </span>
          <div className="sidebar-brand-copy">
            <strong>{APP_NAME}</strong>
            <span>Recruiter workspace</span>
          </div>
        </div>
      </div>

      <nav aria-label="Primary navigation">
        {NAVIGATION_ITEMS.map((item) => {
          const Icon = ICONS[item.icon];

          return (
            <NavLink
              key={item.path}
              to={item.path}
              title={item.label}
              aria-label={item.label}
            >
              <span className="nav-icon">
                <Icon size={21} strokeWidth={1.9} aria-hidden="true" />
              </span>
              <span className="nav-label">{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-user" aria-label="Signed in recruiter">
          {currentUser?.photoURL ? (
            <img src={currentUser.photoURL} alt="" className="user-avatar" />
          ) : (
            <span className="user-avatar user-avatar-fallback">
              {fallbackInitial}
            </span>
          )}
          <div className="sidebar-user-copy">
            <strong>{displayName}</strong>
            <span>{secondaryLabel}</span>
          </div>
          <button
            type="button"
            className="sidebar-logout"
            onClick={handleLogout}
            title="Logout"
            aria-label="Logout"
          >
            <LogOut size={17} aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>
  );
}
