"""Opt-in PostgreSQL integration tests for core ownership boundaries."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data.models.postgres import (
    AssessmentSlotModel,
    AssessmentTemplateModel,
    CandidateAssessmentModel,
    CandidateModel,
    SubmissionModel,
)
from data.repositories.assessment_repository import AssessmentRepository

TEST_DATABASE_URL = os.getenv("CORE_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL.startswith("postgresql"),
    reason="CORE_TEST_DATABASE_URL is required for PostgreSQL integration",
)


def test_recruiter_ownership_and_candidate_context_round_trip() -> None:
    suffix = uuid4().hex
    owner_uid = f"owner-{suffix}"
    other_uid = f"other-{suffix}"
    assessment_id = str(uuid4())
    slot_id = str(uuid4())
    candidate_id = str(uuid4())
    assignment_id = str(uuid4())
    invite_hash = f"invite-{suffix}"
    now = datetime.now(UTC)
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, expire_on_commit=False)
        try:
            session.add_all(
                [
                    AssessmentTemplateModel(
                        id=assessment_id,
                        recruiter_uid=owner_uid,
                        title="Integration Assessment",
                        description="Ownership integration fixture",
                        instructions="Complete every question.",
                        supported_languages=["python"],
                    ),
                    CandidateModel(
                        id=candidate_id,
                        recruiter_uid=owner_uid,
                        full_name="Integration Candidate",
                        email=f"candidate-{suffix}@example.com",
                    ),
                ]
            )
            session.flush()
            session.add(
                AssessmentSlotModel(
                    id=slot_id,
                    assessment_id=assessment_id,
                    recruiter_uid=owner_uid,
                    title="Integration Batch",
                    start_at=now - timedelta(minutes=5),
                    end_at=now + timedelta(minutes=55),
                )
            )
            session.flush()
            session.add(
                CandidateAssessmentModel(
                    id=assignment_id,
                    assessment_id=assessment_id,
                    slot_id=slot_id,
                    candidate_id=candidate_id,
                    recruiter_uid=owner_uid,
                    invite_token_hash=invite_hash,
                    status="submitted",
                    submitted_at=now,
                )
            )
            session.flush()
            session.add(
                SubmissionModel(
                    candidate_assessment_id=assignment_id,
                    assessment_id=assessment_id,
                    question_id=str(uuid4()),
                    source_language="python",
                    draft_code="print('checkpoint')",
                    final_code="print('submitted')",
                    status="submitted",
                    final_hidden_result={
                        "passed_count": 1,
                        "total_count": 1,
                    },
                    submitted_at=now,
                )
            )
            session.flush()

            repository = AssessmentRepository(session)

            assert (
                repository.get_assessment(
                    recruiter_uid=owner_uid,
                    assessment_id=assessment_id,
                )
                is not None
            )
            assert (
                repository.get_assessment(
                    recruiter_uid=other_uid,
                    assessment_id=assessment_id,
                )
                is None
            )
            assert (
                repository.get_slot(
                    recruiter_uid=owner_uid,
                    slot_id=slot_id,
                )
                is not None
            )
            assert (
                repository.get_slot(
                    recruiter_uid=other_uid,
                    slot_id=slot_id,
                )
                is None
            )
            assert (
                repository.get_candidate_assignment(
                    recruiter_uid=owner_uid,
                    candidate_assessment_id=assignment_id,
                )
                is not None
            )
            assert (
                repository.get_candidate_assignment(
                    recruiter_uid=other_uid,
                    candidate_assessment_id=assignment_id,
                )
                is None
            )

            assignment = repository.get_assignment_by_invite_hash(invite_hash)
            assert assignment is not None
            assert assignment.id == assignment_id
            assessment, slot, candidate = repository.get_candidate_context_models(
                assessment_id=assessment_id,
                slot_id=slot_id,
                candidate_id=candidate_id,
            )
            assert assessment is not None and assessment.id == assessment_id
            assert slot is not None and slot.id == slot_id
            assert candidate is not None and candidate.id == candidate_id
            submissions = repository.submissions_for_candidate_assessment(assignment_id)
            assert len(submissions) == 1
            assert next(iter(submissions.values())).final_code == "print('submitted')"
            assert (
                len(
                    repository.list_submitted_assignments_for_assessment(
                        recruiter_uid=owner_uid,
                        assessment_id=assessment_id,
                    )
                )
                == 1
            )
            assert (
                repository.list_submitted_assignments_for_assessment(
                    recruiter_uid=other_uid,
                    assessment_id=assessment_id,
                )
                == []
            )
        finally:
            transaction.rollback()
            session.close()

    engine.dispose()
