import {
  ClipboardList,
  FileQuestion,
  Gauge,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { useMemo } from "react";
import { Link, NavLink } from "react-router-dom";

import { APP_NAME, NAVIGATION_ITEMS } from "../../config/constants";
import { useAssessments } from "../../features/assessments/hooks/useAssessments";
import { assessmentPath } from "../../features/assessments/utils/assessmentRoutes";
import { useAuth } from "../../features/auth";

const ICONS: Record<(typeof NAVIGATION_ITEMS)[number]["icon"], LucideIcon> = {
  assessments: ClipboardList,
  dashboard: Gauge,
  questions: FileQuestion,
  settings: Settings,
};

export function Sidebar() {
  const { currentUser } = useAuth();
  const assessmentsQuery = useAssessments(currentUser);
  const primaryNavigationItems = NAVIGATION_ITEMS.filter(
    (item) => item.icon !== "settings",
  );
  const settingsItem = NAVIGATION_ITEMS.find((item) => item.icon === "settings");
  const recentAssessments = useMemo(
    () =>
      [...(assessmentsQuery.data?.items ?? [])]
        .sort(
          (left, right) =>
            Date.parse(right.updated_at) - Date.parse(left.updated_at),
        )
        .slice(0, 5),
    [assessmentsQuery.data?.items],
  );

  return (
    <aside className="sidebar" aria-label="Recruiter navigation">
      <div className="sidebar-header">
        <Link
          className="sidebar-brand"
          to="/recruiter/dashboard"
          aria-label={`${APP_NAME} home`}
          title="Dashboard"
        >
          <span className="cap-logo" aria-hidden="true">
            <span />
          </span>
          <div className="sidebar-brand-copy">
            <strong>{APP_NAME}</strong>
            <span>Recruiter workspace</span>
          </div>
        </Link>
      </div>

      <nav aria-label="Primary navigation">
        {primaryNavigationItems.map((item) => {
          const Icon = ICONS[item.icon];

          return (
            <div className="sidebar-nav-group" key={item.path}>
              <NavLink
                to={item.path}
                title={item.label}
                aria-label={item.label}
              >
                <span className="nav-icon">
                  <Icon size={21} strokeWidth={1.9} aria-hidden="true" />
                </span>
                <span className="nav-label">{item.label}</span>
              </NavLink>

              {item.icon === "assessments" && recentAssessments.length ? (
                <div
                  className="sidebar-subnav"
                  aria-label="Recent assessments"
                >
                  <span className="sidebar-subnav-label">Recent</span>
                  {recentAssessments.map((assessment) => (
                    <NavLink
                      className="sidebar-assessment-link"
                      key={assessment.id}
                      to={assessmentPath(assessment.id)}
                      title={assessment.title}
                    >
                      <span>{assessment.title}</span>
                    </NavLink>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
      </nav>

      {settingsItem ? (
        <div className="sidebar-footer">
          <nav aria-label="Workspace settings">
            <NavLink
              to={settingsItem.path}
              title={settingsItem.label}
              aria-label={settingsItem.label}
            >
              <span className="nav-icon">
                <Settings size={21} strokeWidth={1.9} aria-hidden="true" />
              </span>
              <span className="nav-label">{settingsItem.label}</span>
            </NavLink>
          </nav>
        </div>
      ) : null}
    </aside>
  );
}
