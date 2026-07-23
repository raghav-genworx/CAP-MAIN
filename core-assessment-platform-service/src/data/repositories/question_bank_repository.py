"""Repositories for question-bank persistence."""

from sqlalchemy import and_, case, desc, or_, select
from sqlalchemy.sql.elements import ColumnElement

from data.models.postgres.question_bank_question import QuestionBankQuestionModel
from data.models.postgres.question_group import QuestionGroupModel
from data.repositories.base import BaseRepository
from schemas.question_bank import (
    DifficultyLevel,
    QuestionGroupStatus,
    QuestionStatus,
    QuestionVisibility,
)


class QuestionBankRepository(BaseRepository):
    """Read and persist recruiter question-bank data."""

    def list_questions(
        self,
        *,
        recruiter_uid: str,
        search: str | None,
        difficulty: DifficultyLevel | None,
        status: QuestionStatus | None,
        tag: str | None,
        sort_by: str,
    ) -> list[QuestionBankQuestionModel]:
        """Return recruiter-owned questions using optional filters and sorting."""

        stmt = select(QuestionBankQuestionModel).where(
            or_(
                QuestionBankQuestionModel.recruiter_uid == recruiter_uid,
                QuestionBankQuestionModel.visibility == QuestionVisibility.PUBLIC.value,
            ),
        )

        conditions: list[ColumnElement[bool]] = []
        if search:
            search_term = f"%{search.strip()}%"
            conditions.append(
                or_(
                    QuestionBankQuestionModel.title.ilike(search_term),
                    QuestionBankQuestionModel.problem_statement.ilike(search_term),
                ),
            )

        if difficulty:
            conditions.append(QuestionBankQuestionModel.difficulty == difficulty.value)

        if status:
            conditions.append(QuestionBankQuestionModel.status == status.value)

        if tag:
            conditions.append(
                QuestionBankQuestionModel.tags.contains([tag.strip().lower()]),
            )

        if conditions:
            stmt = stmt.where(and_(*conditions))

        if sort_by == "title-asc":
            stmt = stmt.order_by(QuestionBankQuestionModel.title.asc())
        elif sort_by == "title-desc":
            stmt = stmt.order_by(QuestionBankQuestionModel.title.desc())
        elif sort_by == "difficulty-asc":
            stmt = stmt.order_by(self._difficulty_order())
        elif sort_by == "difficulty-desc":
            stmt = stmt.order_by(desc(self._difficulty_order()))
        elif sort_by == "status-asc":
            stmt = stmt.order_by(QuestionBankQuestionModel.status.asc())
        elif sort_by == "status-desc":
            stmt = stmt.order_by(QuestionBankQuestionModel.status.desc())
        elif sort_by == "date-asc":
            stmt = stmt.order_by(QuestionBankQuestionModel.updated_at.asc())
        else:
            stmt = stmt.order_by(desc(QuestionBankQuestionModel.updated_at))

        return list(self._session.execute(stmt).scalars().all())

    def list_groups(
        self,
        *,
        recruiter_uid: str,
        search: str | None,
        status: QuestionGroupStatus | None,
    ) -> list[QuestionGroupModel]:
        """Return recruiter-owned question groups using optional filters."""

        stmt = select(QuestionGroupModel).where(
            QuestionGroupModel.recruiter_uid == recruiter_uid,
        )

        conditions: list[ColumnElement[bool]] = []
        if search:
            search_term = f"%{search.strip()}%"
            conditions.append(
                or_(
                    QuestionGroupModel.name.ilike(search_term),
                    QuestionGroupModel.description.ilike(search_term),
                ),
            )

        if status:
            conditions.append(QuestionGroupModel.status == status.value)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.order_by(desc(QuestionGroupModel.updated_at))
        return list(self._session.execute(stmt).scalars().all())

    def get_owned_question(
        self,
        *,
        recruiter_uid: str,
        question_id: str,
    ) -> QuestionBankQuestionModel | None:
        """Return one recruiter-owned question."""

        stmt = select(QuestionBankQuestionModel).where(
            QuestionBankQuestionModel.id == question_id,
            QuestionBankQuestionModel.recruiter_uid == recruiter_uid,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_owned_group(
        self,
        *,
        recruiter_uid: str,
        group_id: str,
    ) -> QuestionGroupModel | None:
        """Return one recruiter-owned question group."""

        stmt = select(QuestionGroupModel).where(
            QuestionGroupModel.id == group_id,
            QuestionGroupModel.recruiter_uid == recruiter_uid,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def existing_question_ids(
        self,
        *,
        recruiter_uid: str,
        question_ids: list[str],
    ) -> set[str]:
        """Return selected question IDs that exist for a recruiter."""

        stmt = select(QuestionBankQuestionModel.id).where(
            or_(
                QuestionBankQuestionModel.recruiter_uid == recruiter_uid,
                QuestionBankQuestionModel.visibility == QuestionVisibility.PUBLIC.value,
            ),
            QuestionBankQuestionModel.id.in_(question_ids),
        )
        return {row[0] for row in self._session.execute(stmt).all()}

    def load_questions_by_ids(
        self,
        *,
        recruiter_uid: str,
        question_ids: list[str],
    ) -> list[QuestionBankQuestionModel]:
        """Load recruiter-owned questions by IDs."""

        if not question_ids:
            return []

        stmt = select(QuestionBankQuestionModel).where(
            or_(
                QuestionBankQuestionModel.recruiter_uid == recruiter_uid,
                QuestionBankQuestionModel.visibility == QuestionVisibility.PUBLIC.value,
            ),
            QuestionBankQuestionModel.id.in_(question_ids),
        )
        return list(self._session.execute(stmt).scalars().all())

    @staticmethod
    def _difficulty_order() -> ColumnElement[int]:
        return case(
            (QuestionBankQuestionModel.difficulty == "easy", 1),
            (QuestionBankQuestionModel.difficulty == "medium", 2),
            (QuestionBankQuestionModel.difficulty == "hard", 3),
            else_=4,
        )
