import { coreApiClient } from "../../../lib/axios";
import type {
  MarkReadResponse,
  NotificationListResponse,
  NotificationSettings,
  NotificationSettingsUpdatePayload,
  UnreadCountResponse,
} from "../types/Notification";

function authHeader(idToken: string) {
  return {
    Authorization: `Bearer ${idToken}`,
  };
}

export async function fetchNotifications(
  idToken: string,
  options: { unreadOnly?: boolean; limit?: number } = {},
): Promise<NotificationListResponse> {
  const response = await coreApiClient.get<NotificationListResponse>(
    "/notifications",
    {
      headers: authHeader(idToken),
      params: {
        unread_only: options.unreadOnly ?? false,
        limit: options.limit ?? 50,
      },
    },
  );
  return response.data;
}

export async function streamNotifications(
  idToken: string,
  onSnapshot: (payload: NotificationListResponse) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${coreApiClient.defaults.baseURL || ""}/notifications/stream`,
    {
      headers: {
        ...authHeader(idToken),
        Accept: "text/event-stream",
      },
      credentials: "include",
      signal,
    },
  );

  if (!response.ok) {
    throw new Error("Unable to open notification stream.");
  }
  if (!response.body) {
    throw new Error("Notification stream is unavailable in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    const eventBlocks = buffer.split("\n\n");
    buffer = eventBlocks.pop() || "";

    for (const eventBlock of eventBlocks) {
      const lines = eventBlock.split("\n");
      const eventName = lines
        .find((line) => line.startsWith("event:"))
        ?.replace("event:", "")
        .trim();
      const data = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.replace("data:", "").trim())
        .join("\n");

      if (eventName === "notifications" && data) {
        onSnapshot(JSON.parse(data) as NotificationListResponse);
      }
    }
  }
}

export async function fetchUnreadCount(
  idToken: string,
): Promise<UnreadCountResponse> {
  const response = await coreApiClient.get<UnreadCountResponse>(
    "/notifications/unread-count",
    { headers: authHeader(idToken) },
  );
  return response.data;
}

export async function markNotificationRead(
  idToken: string,
  notificationId: string,
): Promise<MarkReadResponse> {
  const response = await coreApiClient.post<MarkReadResponse>(
    `/notifications/${notificationId}/read`,
    null,
    { headers: authHeader(idToken) },
  );
  return response.data;
}

export async function markAllNotificationsRead(
  idToken: string,
): Promise<MarkReadResponse> {
  const response = await coreApiClient.post<MarkReadResponse>(
    "/notifications/read-all",
    null,
    { headers: authHeader(idToken) },
  );
  return response.data;
}

export async function fetchNotificationSettings(
  idToken: string,
): Promise<NotificationSettings> {
  const response = await coreApiClient.get<NotificationSettings>(
    "/notifications/settings",
    { headers: authHeader(idToken) },
  );
  return response.data;
}

export async function updateNotificationSettings(
  idToken: string,
  payload: NotificationSettingsUpdatePayload,
): Promise<NotificationSettings> {
  const response = await coreApiClient.put<NotificationSettings>(
    "/notifications/settings",
    payload,
    { headers: authHeader(idToken) },
  );
  return response.data;
}
