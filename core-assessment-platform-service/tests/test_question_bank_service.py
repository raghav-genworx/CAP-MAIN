"""Question-bank service repository integration tests."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.services.question_bank_service import QuestionBankService
from data.models.postgres.question_bank_question import QuestionBankQuestionModel
from schemas.question_bank import (
    DifficultyLevel,
    QuestionCreateRequest,
    QuestionStatus,
)
from schemas.question_bank import (
    TestCase as QuestionTestCase,
)


def test_create_question_persists_through_repository() -> None:
    """Creating a question should use the repository unit of work."""

    service = QuestionBankService(MagicMock())
    repository = SimpleNamespace(
        add=MagicMock(),
        commit=MagicMock(),
        refresh=MagicMock(),
        rollback=MagicMock(),
    )

    def refresh_model(model: QuestionBankQuestionModel) -> None:
        model.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        model.updated_at = datetime(2026, 1, 1, tzinfo=UTC)

    repository.refresh.side_effect = refresh_model
    service._repository = repository

    record = service.create_question(
        "recruiter-1",
        QuestionCreateRequest(
            title="Two Sum",
            problem_statement="Return indices of two numbers that add to target.",
            difficulty=DifficultyLevel.EASY,
            sample_test_cases=[
                QuestionTestCase(input="4\n2 7 11 15\n9", expected_output="0 1"),
            ],
            hidden_test_cases=[
                QuestionTestCase(input="3\n3 2 4\n6", expected_output="1 2"),
            ],
            reference_solution="def solve(): pass",
            reference_language="python",
            supported_languages=["python"],
            status=QuestionStatus.DRAFT,
        ),
    )

    repository.add.assert_called_once()
    repository.commit.assert_called_once()
    repository.refresh.assert_called_once()
    repository.rollback.assert_not_called()

    persisted_model = repository.add.call_args.args[0]
    assert isinstance(persisted_model, QuestionBankQuestionModel)
    assert persisted_model.recruiter_uid == "recruiter-1"
    assert persisted_model.title == "Two Sum"
    assert record.title == "Two Sum"
    assert record.sample_test_cases[0].is_sample is True
    assert record.hidden_test_cases[0].is_sample is False
