"""Repository for assessment and candidate portal persistence."""

from sqlalchemy import or_, select

from data.models.postgres.assessment_question import AssessmentQuestionModel
from data.models.postgres.assessment_slot import AssessmentSlotModel
from data.models.postgres.assessment_template import AssessmentTemplateModel
from data.models.postgres.candidate import CandidateModel
from data.models.postgres.candidate_assessment import CandidateAssessmentModel
from data.models.postgres.candidate_proctor_event import CandidateProctorEventModel
from data.models.postgres.question_bank_question import QuestionBankQuestionModel
from data.models.postgres.submission import SubmissionModel
from data.repositories.base import BaseRepository
from schemas.question_bank import QuestionVisibility


class AssessmentRepository(BaseRepository):
    """Read and persist assessment, slot, candidate, and submission data."""

    def list_assessments(self, recruiter_uid: str) -> list[AssessmentTemplateModel]:
        """Return recruiter-owned assessment templates."""

        stmt = (
            select(AssessmentTemplateModel)
            .where(AssessmentTemplateModel.recruiter_uid == recruiter_uid)
            .order_by(AssessmentTemplateModel.updated_at.desc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_assessment(
        self,
        *,
        recruiter_uid: str,
        assessment_id: str,
    ) -> AssessmentTemplateModel | None:
        """Return one recruiter-owned assessment."""

        stmt = select(AssessmentTemplateModel).where(
            AssessmentTemplateModel.id == assessment_id,
            AssessmentTemplateModel.recruiter_uid == recruiter_uid,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_slot(
        self,
        *,
        recruiter_uid: str,
        slot_id: str,
    ) -> AssessmentSlotModel | None:
        """Return one recruiter-owned assessment slot."""

        stmt = select(AssessmentSlotModel).where(
            AssessmentSlotModel.id == slot_id,
            AssessmentSlotModel.recruiter_uid == recruiter_uid,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_slots_for_assessment(
        self,
        *,
        recruiter_uid: str,
        assessment_id: str,
        descending: bool = False,
    ) -> list[AssessmentSlotModel]:
        """Return slots for a recruiter-owned assessment."""

        ordering = (
            AssessmentSlotModel.start_at.desc()
            if descending
            else AssessmentSlotModel.start_at.asc()
        )
        stmt = (
            select(AssessmentSlotModel)
            .where(
                AssessmentSlotModel.assessment_id == assessment_id,
                AssessmentSlotModel.recruiter_uid == recruiter_uid,
            )
            .order_by(ordering)
        )
        return list(self._session.execute(stmt).scalars().all())

    def list_assessment_questions(
        self,
        assessment_id: str,
    ) -> list[AssessmentQuestionModel]:
        """Return ordered assessment question mappings."""

        stmt = (
            select(AssessmentQuestionModel)
            .where(AssessmentQuestionModel.assessment_id == assessment_id)
            .order_by(AssessmentQuestionModel.question_order.asc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def replace_assessment_questions(
        self,
        *,
        assessment_id: str,
        questions: list[AssessmentQuestionModel],
    ) -> None:
        """Replace all question mappings for an assessment."""

        existing = list(
            self._session.execute(
                select(AssessmentQuestionModel).where(
                    AssessmentQuestionModel.assessment_id == assessment_id,
                )
            )
            .scalars()
            .all()
        )
        for existing_item in existing:
            self.delete(existing_item)
        for question in questions:
            self.add(question)

    def load_question_bank_records(
        self,
        *,
        recruiter_uid: str,
        question_ids: list[str],
    ) -> list[QuestionBankQuestionModel]:
        """Load recruiter-owned question-bank records by IDs."""

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

    def list_slot_assignments(
        self,
        *,
        recruiter_uid: str,
        slot_id: str,
    ) -> list[CandidateAssessmentModel]:
        """Return ordered candidate assignments for a slot."""

        stmt = (
            select(CandidateAssessmentModel)
            .where(
                CandidateAssessmentModel.recruiter_uid == recruiter_uid,
                CandidateAssessmentModel.slot_id == slot_id,
            )
            .order_by(CandidateAssessmentModel.created_at.asc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def list_invite_targets(
        self,
        *,
        recruiter_uid: str,
        slot_id: str,
        candidate_assessment_id: str | None = None,
        candidate_assessment_ids: list[str] | None = None,
    ) -> list[CandidateAssessmentModel]:
        """Return candidate assignments targeted for invite dispatch."""

        stmt = select(CandidateAssessmentModel).where(
            CandidateAssessmentModel.recruiter_uid == recruiter_uid,
            CandidateAssessmentModel.slot_id == slot_id,
        )
        if candidate_assessment_id:
            stmt = stmt.where(CandidateAssessmentModel.id == candidate_assessment_id)
        if candidate_assessment_ids:
            stmt = stmt.where(CandidateAssessmentModel.id.in_(candidate_assessment_ids))
        return list(self._session.execute(stmt).scalars().all())

    def get_candidate_assignment(
        self,
        *,
        recruiter_uid: str,
        candidate_assessment_id: str,
    ) -> CandidateAssessmentModel | None:
        """Return one recruiter-owned candidate assignment."""

        stmt = select(CandidateAssessmentModel).where(
            CandidateAssessmentModel.id == candidate_assessment_id,
            CandidateAssessmentModel.recruiter_uid == recruiter_uid,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def candidates_by_ids(self, candidate_ids: list[str]) -> dict[str, CandidateModel]:
        """Return candidates keyed by candidate ID."""

        if not candidate_ids:
            return {}

        stmt = select(CandidateModel).where(CandidateModel.id.in_(candidate_ids))
        return {item.id: item for item in self._session.execute(stmt).scalars().all()}

    def get_candidate_by_email(
        self,
        *,
        recruiter_uid: str,
        email: str,
    ) -> CandidateModel | None:
        """Return one recruiter-owned candidate by email."""

        stmt = select(CandidateModel).where(
            CandidateModel.recruiter_uid == recruiter_uid,
            CandidateModel.email == email,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def candidate_assignments_for_slot_ids(
        self,
        slot_ids: list[str],
    ) -> dict[str, list[CandidateAssessmentModel]]:
        """Return candidate assignments grouped by slot ID."""

        if not slot_ids:
            return {}

        stmt = select(CandidateAssessmentModel).where(
            CandidateAssessmentModel.slot_id.in_(slot_ids),
        )
        items = list(self._session.execute(stmt).scalars().all())
        grouped: dict[str, list[CandidateAssessmentModel]] = {
            slot_id: [] for slot_id in slot_ids
        }
        for item in items:
            grouped.setdefault(item.slot_id, []).append(item)
        return grouped

    def list_submitted_assignments_for_assessment(
        self,
        *,
        recruiter_uid: str,
        assessment_id: str,
        candidate_assessment_ids: list[str] | None = None,
    ) -> list[CandidateAssessmentModel]:
        """Return submitted candidate assignments for a recruiter assessment."""

        stmt = (
            select(CandidateAssessmentModel)
            .where(
                CandidateAssessmentModel.recruiter_uid == recruiter_uid,
                CandidateAssessmentModel.assessment_id == assessment_id,
                CandidateAssessmentModel.status.in_(("submitted", "auto_submitted")),
            )
            .order_by(CandidateAssessmentModel.submitted_at.asc())
        )
        if candidate_assessment_ids:
            stmt = stmt.where(CandidateAssessmentModel.id.in_(candidate_assessment_ids))
        return list(self._session.execute(stmt).scalars().all())

    def get_assignment_by_invite_hash(
        self,
        invite_token_hash: str,
    ) -> CandidateAssessmentModel | None:
        """Return a candidate assignment by invite token hash."""

        stmt = select(CandidateAssessmentModel).where(
            CandidateAssessmentModel.invite_token_hash == invite_token_hash,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_assignment_by_id(
        self,
        candidate_assessment_id: str,
    ) -> CandidateAssessmentModel | None:
        """Return a candidate assignment by ID."""

        return self._session.get(CandidateAssessmentModel, candidate_assessment_id)

    def get_proctor_event(
        self,
        *,
        candidate_assessment_id: str,
        client_event_id: str,
    ) -> CandidateProctorEventModel | None:
        """Return an already accepted browser event for idempotent retries."""

        stmt = select(CandidateProctorEventModel).where(
            CandidateProctorEventModel.candidate_assessment_id
            == candidate_assessment_id,
            CandidateProctorEventModel.client_event_id == client_event_id,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_candidate_context_models(
        self,
        *,
        assessment_id: str,
        slot_id: str,
        candidate_id: str,
    ) -> tuple[
        AssessmentTemplateModel | None,
        AssessmentSlotModel | None,
        CandidateModel | None,
    ]:
        """Return the assessment, slot, and candidate for a candidate assignment."""

        assessment = self._session.get(AssessmentTemplateModel, assessment_id)
        slot = self._session.get(AssessmentSlotModel, slot_id)
        candidate = self._session.get(CandidateModel, candidate_id)
        return assessment, slot, candidate

    def submissions_for_candidate_assessment(
        self,
        candidate_assessment_id: str,
    ) -> dict[str, SubmissionModel]:
        """Return submissions keyed by question ID for a candidate assessment."""

        stmt = select(SubmissionModel).where(
            SubmissionModel.candidate_assessment_id == candidate_assessment_id,
        )
        items = list(self._session.execute(stmt).scalars().all())
        return {item.question_id: item for item in items}

    def submission_counts_by_candidate_assessment(
        self,
        candidate_assessment_ids: list[str],
    ) -> dict[str, int]:
        """Return non-empty submission counts keyed by candidate assessment ID."""

        if not candidate_assessment_ids:
            return {}

        stmt = select(SubmissionModel).where(
            SubmissionModel.candidate_assessment_id.in_(candidate_assessment_ids),
        )
        items = list(self._session.execute(stmt).scalars().all())
        counts: dict[str, int] = dict.fromkeys(candidate_assessment_ids, 0)
        for item in items:
            if item.draft_code.strip() or item.final_code.strip():
                counts[item.candidate_assessment_id] = (
                    counts.get(item.candidate_assessment_id, 0) + 1
                )
        return counts
