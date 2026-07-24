export type NotificationMode = "per_candidate" | "milestone" | "one_per_test";

export type NotificationType =
  | "submission_per_candidate"
  | "submission_milestone"
  | "submission_grouped"
  | "evaluation_per_candidate"
  | "evaluation_milestone"
  | "evaluation_grouped"
  | "evaluation_completed"
  | "report_ready";

export interface NotificationSettings {
  setting_id: string;
  recruiter_id: string;
  submission_notification_mode: NotificationMode;
  evaluation_notification_mode: NotificationMode;
  milestone_percentages: number[];
  enable_submission_notifications: boolean;
  enable_evaluation_notifications: boolean;
  enable_report_ready_notification: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationSettingsUpdatePayload {
  submission_notification_mode?: NotificationMode;
  evaluation_notification_mode?: NotificationMode;
  milestone_percentages?: number[];
  enable_submission_notifications?: boolean;
  enable_evaluation_notifications?: boolean;
  enable_report_ready_notification?: boolean;
}

export interface NotificationItem {
  id: string;
  type: NotificationType;
  title: string;
  body: string;
  assessment_id: string | null;
  slot_id: string | null;
  candidate_assessment_id: string | null;
  group_key: string | null;
  data: Record<string, unknown>;
  is_read: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
  unread_count: number;
}

export interface UnreadCountResponse {
  unread_count: number;
}

export interface MarkReadResponse {
  updated_count: number;
  unread_count: number;
}
