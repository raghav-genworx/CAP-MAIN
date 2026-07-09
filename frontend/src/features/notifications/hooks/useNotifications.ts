import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { User } from "firebase/auth";
import { useEffect } from "react";

import {
  fetchNotificationSettings,
  fetchNotifications,
  fetchUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
  streamNotifications,
  updateNotificationSettings,
} from "../services/notificationService";
import type { NotificationSettingsUpdatePayload } from "../types/Notification";

async function getRequiredIdToken(user: User | null): Promise<string> {
  if (!user) {
    throw new Error("Recruiter session is required");
  }
  return user.getIdToken();
}

export function useNotifications(user: User | null) {
  return useQuery({
    queryKey: ["notifications", user?.uid],
    queryFn: async () => fetchNotifications(await getRequiredIdToken(user)),
    enabled: Boolean(user),
  });
}

export function useUnreadNotificationCount(user: User | null) {
  return useQuery({
    queryKey: ["notifications-unread", user?.uid],
    queryFn: async () => fetchUnreadCount(await getRequiredIdToken(user)),
    enabled: Boolean(user),
  });
}

/**
 * Keeps the notification caches live over a single SSE connection instead of
 * client-side polling. Reconnects with a short backoff if the stream drops.
 */
export function useNotificationStream(user: User | null) {
  const queryClient = useQueryClient();
  const userId = user?.uid;

  useEffect(() => {
    if (!user) {
      return undefined;
    }

    const controller = new AbortController();
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    async function connect() {
      if (controller.signal.aborted || !user) {
        return;
      }
      try {
        const idToken = await user.getIdToken();
        if (controller.signal.aborted) {
          return;
        }
        await streamNotifications(
          idToken,
          (snapshot) => {
            queryClient.setQueryData(["notifications", user.uid], snapshot);
            queryClient.setQueryData(["notifications-unread", user.uid], {
              unread_count: snapshot.unread_count,
            });
          },
          controller.signal,
        );
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error("Notification stream failed", error);
        }
      }
      if (!controller.signal.aborted) {
        retryTimer = setTimeout(connect, 5000);
      }
    }

    void connect();

    return () => {
      controller.abort();
      if (retryTimer) {
        clearTimeout(retryTimer);
      }
    };
  }, [queryClient, user, userId]);
}

function useInvalidateNotifications() {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["notifications"] }),
      queryClient.invalidateQueries({ queryKey: ["notifications-unread"] }),
    ]);
  };
}

export function useMarkNotificationRead(user: User | null) {
  const invalidate = useInvalidateNotifications();
  return useMutation({
    mutationFn: async (notificationId: string) =>
      markNotificationRead(await getRequiredIdToken(user), notificationId),
    onSuccess: invalidate,
  });
}

export function useMarkAllNotificationsRead(user: User | null) {
  const invalidate = useInvalidateNotifications();
  return useMutation({
    mutationFn: async () => markAllNotificationsRead(await getRequiredIdToken(user)),
    onSuccess: invalidate,
  });
}

export function useNotificationSettings(user: User | null) {
  return useQuery({
    queryKey: ["notification-settings", user?.uid],
    queryFn: async () => fetchNotificationSettings(await getRequiredIdToken(user)),
    enabled: Boolean(user),
  });
}

export function useUpdateNotificationSettings(user: User | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: NotificationSettingsUpdatePayload) =>
      updateNotificationSettings(await getRequiredIdToken(user), payload),
    onSuccess: async (data) => {
      queryClient.setQueryData(["notification-settings", user?.uid], data);
      await queryClient.invalidateQueries({ queryKey: ["notification-settings"] });
    },
  });
}
