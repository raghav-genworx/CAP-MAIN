"""Repository for recruiter notification settings and inbox."""

from sqlalchemy import func, select

from data.models.postgres.core.candidate_assessment import CandidateAssessmentModel
from data.models.postgres.core.recruiter_notification import RecruiterNotificationModel
from data.models.postgres.core.recruiter_notification_setting import (
    RecruiterNotificationSettingModel,
)
from data.repositories.base_postgres_repository import BaseRepository

_SUBMITTED_STATUSES = ("submitted", "auto_submitted")


class NotificationRepository(BaseRepository):
    """Read and persist recruiter notification settings and inbox rows."""

    def get_settings(
        self, recruiter_uid: str
    ) -> RecruiterNotificationSettingModel | None:
        """Return the stored notification preferences for a recruiter."""

        stmt = select(RecruiterNotificationSettingModel).where(
            RecruiterNotificationSettingModel.recruiter_uid == recruiter_uid,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_notifications(
        self,
        *,
        recruiter_uid: str,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[RecruiterNotificationModel]:
        """Return recruiter notifications ordered by most recent activity."""

        stmt = select(RecruiterNotificationModel).where(
            RecruiterNotificationModel.recruiter_uid == recruiter_uid,
        )
        if unread_only:
            stmt = stmt.where(RecruiterNotificationModel.is_read.is_(False))
        stmt = stmt.order_by(RecruiterNotificationModel.updated_at.desc()).limit(limit)
        return list(self._session.execute(stmt).scalars().all())

    def get_notification(
        self,
        *,
        recruiter_uid: str,
        notification_id: str,
    ) -> RecruiterNotificationModel | None:
        """Return one recruiter-owned notification."""

        stmt = select(RecruiterNotificationModel).where(
            RecruiterNotificationModel.id == notification_id,
            RecruiterNotificationModel.recruiter_uid == recruiter_uid,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_notification_by_group_key(
        self,
        *,
        recruiter_uid: str,
        group_key: str,
    ) -> RecruiterNotificationModel | None:
        """Return the grouped notification card for a recruiter test slot."""

        stmt = select(RecruiterNotificationModel).where(
            RecruiterNotificationModel.recruiter_uid == recruiter_uid,
            RecruiterNotificationModel.group_key == group_key,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def count_unread(self, recruiter_uid: str) -> int:
        """Return the number of unread notifications for a recruiter."""

        stmt = (
            select(func.count())
            .select_from(RecruiterNotificationModel)
            .where(
                RecruiterNotificationModel.recruiter_uid == recruiter_uid,
                RecruiterNotificationModel.is_read.is_(False),
            )
        )
        return int(self._session.execute(stmt).scalar_one())

    def mark_all_read(self, recruiter_uid: str) -> int:
        """Mark every unread recruiter notification as read."""

        stmt = select(RecruiterNotificationModel).where(
            RecruiterNotificationModel.recruiter_uid == recruiter_uid,
            RecruiterNotificationModel.is_read.is_(False),
        )
        rows = list(self._session.execute(stmt).scalars().all())
        for row in rows:
            row.is_read = True
        return len(rows)

    def count_slot_assignments(self, slot_id: str) -> int:
        """Return the total candidate assignments in a slot."""

        stmt = (
            select(func.count())
            .select_from(CandidateAssessmentModel)
            .where(CandidateAssessmentModel.slot_id == slot_id)
        )
        return int(self._session.execute(stmt).scalar_one())

    def count_slot_submitted(self, slot_id: str) -> int:
        """Return the number of submitted (or auto-submitted) assignments."""

        stmt = (
            select(func.count())
            .select_from(CandidateAssessmentModel)
            .where(
                CandidateAssessmentModel.slot_id == slot_id,
                CandidateAssessmentModel.status.in_(_SUBMITTED_STATUSES),
            )
        )
        return int(self._session.execute(stmt).scalar_one())

    def count_slot_evaluated(self, slot_id: str) -> int:
        """Return the number of assignments that carry an evaluation rank."""

        stmt = (
            select(func.count())
            .select_from(CandidateAssessmentModel)
            .where(
                CandidateAssessmentModel.slot_id == slot_id,
                CandidateAssessmentModel.rank.is_not(None),
            )
        )
        return int(self._session.execute(stmt).scalar_one())
