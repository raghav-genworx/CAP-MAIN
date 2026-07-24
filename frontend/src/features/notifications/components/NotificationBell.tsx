import { Bell, CheckCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../auth";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
  useNotificationStream,
  useUnreadNotificationCount,
} from "../hooks/useNotifications";
import type { NotificationItem } from "../types/Notification";

function formatRelativeTime(iso: string): string {
  const timestamp = new Date(iso).getTime();
  if (Number.isNaN(timestamp)) {
    return "";
  }
  const diffSeconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (diffSeconds < 60) {
    return "just now";
  }
  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  return `${Math.round(diffHours / 24)}d ago`;
}

export function NotificationBell() {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  useNotificationStream(currentUser);
  const notificationsQuery = useNotifications(currentUser);
  const unreadQuery = useUnreadNotificationCount(currentUser);
  const markRead = useMarkNotificationRead(currentUser);
  const markAllRead = useMarkAllNotificationsRead(currentUser);

  const items = notificationsQuery.data?.items ?? [];
  const unreadCount =
    unreadQuery.data?.unread_count ?? notificationsQuery.data?.unread_count ?? 0;

  function handleOpenItem(item: NotificationItem) {
    if (!item.is_read) {
      markRead.mutate(item.id);
    }
    if (item.assessment_id) {
      navigate(`/recruiter/assessments/${item.assessment_id}`);
    }
  }

  return (
    <details className="notification-menu">
      <summary
        className="icon-button notification-trigger"
        aria-label={
          unreadCount > 0
            ? `Notifications, ${unreadCount} unread`
            : "Notifications"
        }
        title="Notifications"
      >
        <Bell size={18} aria-hidden="true" />
        {unreadCount > 0 ? (
          <span className="notification-badge" aria-hidden="true">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        ) : null}
      </summary>

      <div className="notification-popover">
        <div className="notification-popover-header">
          <div>
            <strong>Notifications</strong>
            <span>{unreadCount} unread</span>
          </div>
          <button
            type="button"
            className="notification-markall"
            onClick={() => markAllRead.mutate()}
            disabled={unreadCount === 0 || markAllRead.isPending}
          >
            <CheckCheck size={14} aria-hidden="true" />
            Mark all read
          </button>
        </div>

        <div className="notification-list">
          {notificationsQuery.isLoading ? (
            <p className="notification-empty">Loading notifications…</p>
          ) : notificationsQuery.isError ? (
            <p className="notification-empty notification-empty-error">
              Notifications are temporarily unavailable.
            </p>
          ) : items.length === 0 ? (
            <p className="notification-empty">You&apos;re all caught up.</p>
          ) : (
            items.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`notification-item${item.is_read ? "" : " is-unread"}`}
                onClick={() => handleOpenItem(item)}
              >
                <span className="notification-item-dot" aria-hidden="true" />
                <span className="notification-item-copy">
                  <strong>{item.title}</strong>
                  {item.body ? <span>{item.body}</span> : null}
                  <time dateTime={item.updated_at}>
                    {formatRelativeTime(item.updated_at)}
                  </time>
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </details>
  );
}
