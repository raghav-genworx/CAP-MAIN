"""Schemas for recruiter in-app notification preferences and inbox."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

DEFAULT_MILESTONE_PERCENTAGES: list[int] = [25, 50, 75, 100]


class NotificationMode(StrEnum):
    """How dashboard notifications are generated for an event category."""

    PER_CANDIDATE = "per_candidate"
    MILESTONE = "milestone"
    ONE_PER_TEST = "one_per_test"


class NotificationType(StrEnum):
    """Concrete notification variants stored in the recruiter inbox."""

    SUBMISSION_PER_CANDIDATE = "submission_per_candidate"
    SUBMISSION_MILESTONE = "submission_milestone"
    SUBMISSION_GROUPED = "submission_grouped"
    EVALUATION_PER_CANDIDATE = "evaluation_per_candidate"
    EVALUATION_MILESTONE = "evaluation_milestone"
    EVALUATION_GROUPED = "evaluation_grouped"
    EVALUATION_COMPLETED = "evaluation_completed"
    REPORT_READY = "report_ready"


def _normalize_milestones(values: list[int]) -> list[int]:
    """Return sorted, de-duplicated milestone percentages within 1-100."""

    cleaned = sorted({int(value) for value in values})
    if not cleaned:
        raise ValueError("At least one milestone percentage is required")
    if any(value < 1 or value > 100 for value in cleaned):
        raise ValueError("Milestone percentages must be between 1 and 100")
    if len(cleaned) > 10:
        raise ValueError("A maximum of 10 milestone percentages is supported")
    return cleaned


class NotificationSettingsRecord(BaseModel):
    """Recruiter notification preferences returned to the dashboard."""

    setting_id: str
    recruiter_id: str
    submission_notification_mode: NotificationMode
    evaluation_notification_mode: NotificationMode
    milestone_percentages: list[int]
    enable_submission_notifications: bool
    enable_evaluation_notifications: bool
    enable_report_ready_notification: bool
    created_at: datetime
    updated_at: datetime


class NotificationSettingsUpdateRequest(BaseModel):
    """Partial update payload for recruiter notification preferences."""

    submission_notification_mode: NotificationMode | None = None
    evaluation_notification_mode: NotificationMode | None = None
    milestone_percentages: list[int] | None = Field(default=None)
    enable_submission_notifications: bool | None = None
    enable_evaluation_notifications: bool | None = None
    enable_report_ready_notification: bool | None = None

    @field_validator("milestone_percentages")
    @classmethod
    def _validate_milestones(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        return _normalize_milestones(value)


class NotificationRecord(BaseModel):
    """A single recruiter inbox notification."""

    id: str
    type: NotificationType
    title: str
    body: str
    assessment_id: str | None = None
    slot_id: str | None = None
    candidate_assessment_id: str | None = None
    group_key: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    is_read: bool
    created_at: datetime
    updated_at: datetime


class NotificationListResponse(BaseModel):
    """Paginated recruiter inbox listing with unread summary."""

    items: list[NotificationRecord]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    """Lightweight unread badge payload for polling."""

    unread_count: int


class MarkReadResponse(BaseModel):
    """Result of marking notifications read."""

    updated_count: int
    unread_count: int
