"""Recruiter notification preferences and inbox generation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from config.settings import Settings, get_settings
from data.models.postgres.recruiter_notification import RecruiterNotificationModel
from data.models.postgres.recruiter_notification_setting import (
    RecruiterNotificationSettingModel,
)
from data.repositories.notification_repository import NotificationRepository
from handlers.clients.redis_broker import NotificationBroker
from schemas.notifications import (
    DEFAULT_MILESTONE_PERCENTAGES,
    MarkReadResponse,
    NotificationListResponse,
    NotificationMode,
    NotificationRecord,
    NotificationSettingsRecord,
    NotificationSettingsUpdateRequest,
    NotificationType,
    UnreadCountResponse,
)


@dataclass(frozen=True)
class EffectiveNotificationSettings:
    """Resolved recruiter preferences used when generating notifications."""

    submission_notification_mode: NotificationMode
    evaluation_notification_mode: NotificationMode
    milestone_percentages: list[int]
    enable_submission_notifications: bool
    enable_evaluation_notifications: bool
    enable_report_ready_notification: bool


class NotificationService:
    """Manage recruiter notification settings and produce inbox entries."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._repository = NotificationRepository(session)
        self._broker = NotificationBroker(self._settings)
        self._pending_recruiter_uids: set[str] = set()

    # ------------------------------------------------------------------
    # Recruiter-facing settings and inbox operations (own the transaction)
    # ------------------------------------------------------------------

    def get_settings(self, recruiter_uid: str) -> NotificationSettingsRecord:
        """Return recruiter preferences, creating defaults on first access."""

        model = self._repository.get_settings(recruiter_uid)
        if model is None:
            model = RecruiterNotificationSettingModel(recruiter_uid=recruiter_uid)
            self._repository.add(model)
            self._repository.commit()
            self._repository.refresh(model)
        return self._settings_record(model)

    def update_settings(
        self,
        recruiter_uid: str,
        payload: NotificationSettingsUpdateRequest,
    ) -> NotificationSettingsRecord:
        """Apply a partial update to recruiter preferences."""

        model = self._repository.get_settings(recruiter_uid)
        if model is None:
            model = RecruiterNotificationSettingModel(recruiter_uid=recruiter_uid)
            self._repository.add(model)

        if payload.submission_notification_mode is not None:
            model.submission_notification_mode = (
                payload.submission_notification_mode.value
            )
        if payload.evaluation_notification_mode is not None:
            model.evaluation_notification_mode = (
                payload.evaluation_notification_mode.value
            )
        if payload.milestone_percentages is not None:
            model.milestone_percentages = payload.milestone_percentages
        if payload.enable_submission_notifications is not None:
            model.enable_submission_notifications = (
                payload.enable_submission_notifications
            )
        if payload.enable_evaluation_notifications is not None:
            model.enable_evaluation_notifications = (
                payload.enable_evaluation_notifications
            )
        if payload.enable_report_ready_notification is not None:
            model.enable_report_ready_notification = (
                payload.enable_report_ready_notification
            )

        self._repository.commit()
        self._repository.refresh(model)
        return self._settings_record(model)

    def list_notifications(
        self,
        recruiter_uid: str,
        *,
        limit: int = 50,
        unread_only: bool = False,
    ) -> NotificationListResponse:
        """Return the recruiter inbox with the unread summary."""

        items = self._repository.list_notifications(
            recruiter_uid=recruiter_uid,
            limit=limit,
            unread_only=unread_only,
        )
        unread = self._repository.count_unread(recruiter_uid)
        return NotificationListResponse(
            items=[self._notification_record(item) for item in items],
            total=len(items),
            unread_count=unread,
        )

    def unread_count(self, recruiter_uid: str) -> UnreadCountResponse:
        """Return the unread notification count for the badge."""

        return UnreadCountResponse(
            unread_count=self._repository.count_unread(recruiter_uid)
        )

    def stream_snapshot(
        self,
        recruiter_uid: str,
        *,
        limit: int = 30,
    ) -> NotificationListResponse:
        """Return a fresh inbox snapshot for the SSE stream.

        Drops any idle transaction snapshot first so each poll observes the
        latest rows committed by the candidate submission/evaluation flow.
        """

        self._session.rollback()
        return self.list_notifications(recruiter_uid, limit=limit)

    def mark_read(self, recruiter_uid: str, notification_id: str) -> MarkReadResponse:
        """Mark one notification as read."""

        model = self._repository.get_notification(
            recruiter_uid=recruiter_uid,
            notification_id=notification_id,
        )
        updated = 0
        if model is not None and not model.is_read:
            model.is_read = True
            updated = 1
            self._repository.commit()
            self._broker.publish(recruiter_uid)
        return MarkReadResponse(
            updated_count=updated,
            unread_count=self._repository.count_unread(recruiter_uid),
        )

    def mark_all_read(self, recruiter_uid: str) -> MarkReadResponse:
        """Mark every unread notification as read."""

        updated = self._repository.mark_all_read(recruiter_uid)
        if updated:
            self._repository.commit()
            self._broker.publish(recruiter_uid)
        return MarkReadResponse(
            updated_count=updated,
            unread_count=self._repository.count_unread(recruiter_uid),
        )

    def flush_events(self) -> None:
        """Publish refresh pings for recruiters touched since the last flush.

        Call this only after the surrounding database transaction has committed
        so subscribers observe the newly persisted notifications.
        """

        pending = self._pending_recruiter_uids
        self._pending_recruiter_uids = set()
        for recruiter_uid in pending:
            self._broker.publish(recruiter_uid)

    # ------------------------------------------------------------------
    # Event hooks (called inside another service's transaction; no commit)
    # ------------------------------------------------------------------

    def record_submission(
        self,
        *,
        recruiter_uid: str,
        assessment_id: str,
        assessment_title: str,
        slot_id: str,
        slot_title: str,
        candidate_name: str,
    ) -> None:
        """Create dashboard notifications for a candidate submission."""

        settings = self._effective_settings(recruiter_uid)
        if not settings.enable_submission_notifications:
            return

        self._session.flush()
        total = self._repository.count_slot_assignments(slot_id)
        submitted = self._repository.count_slot_submitted(slot_id)
        label = self._slot_label(assessment_title, slot_title)
        base = {
            "assessment_id": assessment_id,
            "slot_id": slot_id,
        }
        data = {
            **base,
            "submitted_count": submitted,
            "total_count": total,
        }

        mode = settings.submission_notification_mode
        if mode == NotificationMode.PER_CANDIDATE:
            self._add_notification(
                recruiter_uid=recruiter_uid,
                type=NotificationType.SUBMISSION_PER_CANDIDATE,
                title=f"{candidate_name} submitted {label}",
                body=f"{submitted} of {total} candidates have submitted.",
                data=data,
                **base,
            )
        elif mode == NotificationMode.MILESTONE:
            reached = self._milestone_reached(
                submitted, total, settings.milestone_percentages
            )
            if reached is not None:
                self._add_notification(
                    recruiter_uid=recruiter_uid,
                    type=NotificationType.SUBMISSION_MILESTONE,
                    title=f"{reached}% candidates submitted {label}",
                    body=f"{submitted} of {total} candidates have submitted.",
                    data={**data, "milestone": reached},
                    **base,
                )
        elif mode == NotificationMode.ONE_PER_TEST:
            self._upsert_grouped(
                recruiter_uid=recruiter_uid,
                group_key=f"submission:{slot_id}",
                type=NotificationType.SUBMISSION_GROUPED,
                title=f"{submitted} / {total} candidates submitted",
                body=f"{label} submission progress.",
                data=data,
                **base,
            )

    def record_evaluation(
        self,
        *,
        recruiter_uid: str,
        assessment_id: str,
        assessment_title: str,
        slot_id: str,
        slot_title: str,
        candidate_name: str,
    ) -> None:
        """Create dashboard notifications for a completed candidate evaluation."""

        settings = self._effective_settings(recruiter_uid)
        if not (
            settings.enable_evaluation_notifications
            or settings.enable_report_ready_notification
        ):
            return

        self._session.flush()
        submitted = self._repository.count_slot_submitted(slot_id)
        evaluated = self._repository.count_slot_evaluated(slot_id)
        label = self._slot_label(assessment_title, slot_title)
        base = {
            "assessment_id": assessment_id,
            "slot_id": slot_id,
        }
        data = {
            **base,
            "evaluated_count": evaluated,
            "submitted_count": submitted,
        }
        all_evaluated = submitted > 0 and evaluated >= submitted

        if settings.enable_evaluation_notifications:
            mode = settings.evaluation_notification_mode
            if mode == NotificationMode.PER_CANDIDATE:
                self._add_notification(
                    recruiter_uid=recruiter_uid,
                    type=NotificationType.EVALUATION_PER_CANDIDATE,
                    title=f"{candidate_name}'s submission was evaluated",
                    body=(
                        f"{evaluated} of {submitted} submissions evaluated for {label}."
                    ),
                    data=data,
                    **base,
                )
            elif mode == NotificationMode.MILESTONE:
                reached = self._milestone_reached(
                    evaluated, submitted, settings.milestone_percentages
                )
                if reached is not None:
                    self._add_notification(
                        recruiter_uid=recruiter_uid,
                        type=NotificationType.EVALUATION_MILESTONE,
                        title=f"{reached}% submissions evaluated for {label}",
                        body=f"{evaluated} of {submitted} submissions evaluated.",
                        data={**data, "milestone": reached},
                        **base,
                    )
            elif mode == NotificationMode.ONE_PER_TEST:
                self._upsert_grouped(
                    recruiter_uid=recruiter_uid,
                    group_key=f"evaluation:{slot_id}",
                    type=NotificationType.EVALUATION_GROUPED,
                    title=f"{evaluated} / {submitted} submissions evaluated",
                    body=f"{label} evaluation progress.",
                    data=data,
                    **base,
                )

            if all_evaluated:
                self._upsert_grouped(
                    recruiter_uid=recruiter_uid,
                    group_key=f"evaluation_completed:{slot_id}",
                    type=NotificationType.EVALUATION_COMPLETED,
                    title=f"All submissions evaluated for {label}",
                    body=f"{evaluated} of {submitted} submissions have been evaluated.",
                    data=data,
                    **base,
                )

        if settings.enable_report_ready_notification and all_evaluated:
            self._upsert_grouped(
                recruiter_uid=recruiter_uid,
                group_key=f"report_ready:{slot_id}",
                type=NotificationType.REPORT_READY,
                title=f"Report ready for {label}",
                body="The evaluation report is ready to review.",
                data=data,
                **base,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _effective_settings(self, recruiter_uid: str) -> EffectiveNotificationSettings:
        model = self._repository.get_settings(recruiter_uid)
        if model is None:
            return EffectiveNotificationSettings(
                submission_notification_mode=NotificationMode.MILESTONE,
                evaluation_notification_mode=NotificationMode.MILESTONE,
                milestone_percentages=list(DEFAULT_MILESTONE_PERCENTAGES),
                enable_submission_notifications=True,
                enable_evaluation_notifications=True,
                enable_report_ready_notification=True,
            )
        return EffectiveNotificationSettings(
            submission_notification_mode=NotificationMode(
                model.submission_notification_mode
            ),
            evaluation_notification_mode=NotificationMode(
                model.evaluation_notification_mode
            ),
            milestone_percentages=list(model.milestone_percentages or []),
            enable_submission_notifications=model.enable_submission_notifications,
            enable_evaluation_notifications=model.enable_evaluation_notifications,
            enable_report_ready_notification=model.enable_report_ready_notification,
        )

    @staticmethod
    def _milestone_reached(
        count: int,
        total: int,
        percentages: list[int],
    ) -> int | None:
        """Return the milestone percentage newly reached by this count."""

        if total <= 0 or count <= 0 or not percentages:
            return None
        matched = [
            percentage
            for percentage in percentages
            if max(1, math.ceil(percentage / 100 * total)) == count
        ]
        return max(matched) if matched else None

    @staticmethod
    def _slot_label(assessment_title: str, slot_title: str) -> str:
        assessment_title = (assessment_title or "").strip() or "Assessment"
        slot_title = (slot_title or "").strip()
        if slot_title and slot_title.lower() != assessment_title.lower():
            return f"{assessment_title} - {slot_title}"
        return assessment_title

    def _add_notification(
        self,
        *,
        recruiter_uid: str,
        type: NotificationType,
        title: str,
        body: str,
        data: dict[str, Any],
        assessment_id: str | None = None,
        slot_id: str | None = None,
        candidate_assessment_id: str | None = None,
        group_key: str | None = None,
    ) -> None:
        self._pending_recruiter_uids.add(recruiter_uid)
        self._repository.add(
            RecruiterNotificationModel(
                recruiter_uid=recruiter_uid,
                type=type.value,
                title=title,
                body=body,
                data=data,
                assessment_id=assessment_id,
                slot_id=slot_id,
                candidate_assessment_id=candidate_assessment_id,
                group_key=group_key,
            )
        )

    def _upsert_grouped(
        self,
        *,
        recruiter_uid: str,
        group_key: str,
        type: NotificationType,
        title: str,
        body: str,
        data: dict[str, Any],
        assessment_id: str | None = None,
        slot_id: str | None = None,
    ) -> None:
        existing = self._repository.get_notification_by_group_key(
            recruiter_uid=recruiter_uid,
            group_key=group_key,
        )
        if existing is None:
            self._add_notification(
                recruiter_uid=recruiter_uid,
                type=type,
                title=title,
                body=body,
                data=data,
                assessment_id=assessment_id,
                slot_id=slot_id,
                group_key=group_key,
            )
            return
        existing.title = title
        existing.body = body
        existing.data = data
        existing.type = type.value
        existing.is_read = False
        self._pending_recruiter_uids.add(recruiter_uid)

    @staticmethod
    def _settings_record(
        model: RecruiterNotificationSettingModel,
    ) -> NotificationSettingsRecord:
        return NotificationSettingsRecord(
            setting_id=model.setting_id,
            recruiter_id=model.recruiter_uid,
            submission_notification_mode=NotificationMode(
                model.submission_notification_mode
            ),
            evaluation_notification_mode=NotificationMode(
                model.evaluation_notification_mode
            ),
            milestone_percentages=list(model.milestone_percentages or []),
            enable_submission_notifications=model.enable_submission_notifications,
            enable_evaluation_notifications=model.enable_evaluation_notifications,
            enable_report_ready_notification=model.enable_report_ready_notification,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _notification_record(
        model: RecruiterNotificationModel,
    ) -> NotificationRecord:
        return NotificationRecord(
            id=model.id,
            type=NotificationType(model.type),
            title=model.title,
            body=model.body,
            assessment_id=model.assessment_id,
            slot_id=model.slot_id,
            candidate_assessment_id=model.candidate_assessment_id,
            group_key=model.group_key,
            data=dict(model.data or {}),
            is_read=model.is_read,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
