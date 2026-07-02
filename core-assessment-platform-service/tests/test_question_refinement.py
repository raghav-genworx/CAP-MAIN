"""Focused contracts for existing-draft testcase and solution refinement."""

from unittest.mock import MagicMock

from control.agents.question_agent.graph.question_graph import (
    QuestionGenerationWorkflow,
)
from control.agents.question_agent.tools.question_tools import (
    QuestionAgentToolsMixin,
    validation_progress_events,
)
from schemas.assessments import ExecutionCaseResult
from schemas.question_bank import (
    QuestionAIDraftContext,
    QuestionAIDraftRequest,
    QuestionGenerationSettings,
    ReferenceSolutionArtifact,
    SolutionValidationCaseResult,
    SolutionValidationReport,
)
from schemas.question_bank import (
    TestCase as QuestionTestCase,
)

VALID_SOURCE = "import sys\nprint(sum(map(int, sys.stdin.read().split())))\n"


def _draft() -> QuestionAIDraftContext:
    return QuestionAIDraftContext(
        title="Add two values",
        problem_statement=(
            "Read two integers and print their arithmetic sum as one integer."
        ),
        constraints="-1000 <= a <= 1000; -1000 <= b <= 1000",
        input_format="Two space-separated integers.",
        output_format="One integer containing a + b.",
        sample_test_cases=[
            QuestionTestCase(
                input="20 40\n",
                expected_output="59\n",
                is_sample=True,
            ),
        ],
        hidden_test_cases=[
            QuestionTestCase(input="-2 5\n", expected_output="3\n"),
        ],
        reference_solution=("a, b = map(int, input().split())\nprint(a + b)\n"),
        reference_language="python",
    )


def _report(*, passed: bool, expected: str, actual: str) -> SolutionValidationReport:
    return SolutionValidationReport(
        status="passed" if passed else "failed",
        summary="validation result",
        passed_count=1 if passed else 0,
        failed_count=0 if passed else 1,
        sample_count=1,
        hidden_count=1,
        results=[
            SolutionValidationCaseResult(
                bucket="sample",
                index=1,
                passed=passed,
                status="Accepted" if passed else "Wrong Answer",
                stdin="20 40\n",
                expected_output=expected,
                actual_output=actual,
            )
        ],
    )


def test_streamed_validation_emits_each_test_case_result() -> None:
    workflow = object.__new__(QuestionGenerationWorkflow)
    workflow._execution_adapter = MagicMock()
    workflow._execution_adapter.execute_batch.side_effect = [
        (
            [
                ExecutionCaseResult(
                    index=1,
                    input="1 2\n",
                    expected_output="3\n",
                    actual_output="3\n",
                    status="Accepted",
                    passed=True,
                )
            ],
            1,
            1,
        ),
        (
            [
                ExecutionCaseResult(
                    index=1,
                    input="2 2\n",
                    expected_output="4\n",
                    actual_output="5\n",
                    status="Wrong Answer",
                    passed=False,
                )
            ],
            0,
            1,
        ),
    ]
    events: list[dict[str, object]] = []

    with validation_progress_events(events.append):
        report = workflow._validate_source_against_tests(
            language="python",
            source_code=VALID_SOURCE,
            sample_tests=[
                QuestionTestCase(
                    input="1 2\n",
                    expected_output="3\n",
                    is_sample=True,
                )
            ],
            hidden_tests=[
                QuestionTestCase(input="2 2\n", expected_output="4\n")
            ],
            rounds=[],
        )

    assert report.status == "failed"
    assert [event["type"] for event in events] == [
        "validation_case_start",
        "validation_case_result",
        "validation_case_start",
        "validation_case_result",
    ]
    assert [event["test_outcome"] for event in events[1::2]] == [
        "passed",
        "wrong",
    ]
    assert all(
        len(call.kwargs["test_cases"]) == 1
        for call in workflow._execution_adapter.execute_batch.call_args_list
    )


def test_non_streamed_validation_keeps_batch_execution() -> None:
    workflow = object.__new__(QuestionGenerationWorkflow)
    workflow._execution_adapter = MagicMock()
    workflow._execution_adapter.execute_batch.return_value = (
        [
            ExecutionCaseResult(
                index=1,
                input="1 2\n",
                expected_output="3\n",
                actual_output="3\n",
                status="Accepted",
                passed=True,
            ),
            ExecutionCaseResult(
                index=2,
                input="2 3\n",
                expected_output="5\n",
                actual_output="5\n",
                status="Accepted",
                passed=True,
            ),
        ],
        2,
        2,
    )

    report = workflow._validate_source_against_tests(
        language="python",
        source_code=VALID_SOURCE,
        sample_tests=[
            QuestionTestCase(input="1 2\n", expected_output="3\n", is_sample=True),
            QuestionTestCase(input="2 3\n", expected_output="5\n", is_sample=True),
        ],
        hidden_tests=[],
        rounds=[],
    )

    assert report.status == "passed"
    assert workflow._execution_adapter.execute_batch.call_count == 1
    assert len(
        workflow._execution_adapter.execute_batch.call_args.kwargs["test_cases"]
    ) == 2


def test_validation_node_forwards_case_events_to_stream() -> None:
    workflow = object.__new__(QuestionGenerationWorkflow)
    workflow._execution_adapter = MagicMock()
    workflow._execution_adapter.execute_batch.return_value = (
        [
            ExecutionCaseResult(
                index=1,
                input="1 2\n",
                expected_output="3\n",
                actual_output="3\n",
                status="Accepted",
                passed=True,
            )
        ],
        1,
        1,
    )

    def run_node(*_args: object) -> dict[str, object]:
        report = workflow._validate_source_against_tests(
            language="python",
            source_code=VALID_SOURCE,
            sample_tests=[
                QuestionTestCase(
                    input="1 2\n",
                    expected_output="3\n",
                    is_sample=True,
                )
            ],
            hidden_tests=[],
            rounds=[],
        )
        return {"solution_validation": report}

    workflow._run_traced_node = MagicMock(side_effect=run_node)
    event_stream = workflow._run_node_with_test_events(
        "validation",
        {},
        None,
        scope="recruiter_validation",
        start_progress=50,
        end_progress=100,
    )
    streamed_events: list[dict[str, object]] = []
    while True:
        try:
            streamed_events.append(next(event_stream))
        except StopIteration as completed:
            patch = completed.value
            break

    assert [event["type"] for event in streamed_events] == [
        "validation_case_start",
        "validation_case_result",
    ]
    assert all(event["current_node"] == "validation" for event in streamed_events)
    assert all(50 < int(event["progress"]) < 100 for event in streamed_events)
    assert patch["solution_validation"].status == "passed"


def test_testcase_repair_preserves_existing_input() -> None:
    original = [
        QuestionTestCase(input="20 40\n", expected_output="59\n", is_sample=True),
    ]
    model_replacement = [
        QuestionTestCase(
            input="999 999\n",
            expected_output="60\n",
            is_sample=True,
        ),
    ]

    repaired = QuestionAgentToolsMixin._preserve_repaired_testcase_inputs(
        original,
        {1},
        model_replacement,
        is_sample=True,
    )

    assert repaired[0].input == "20 40\n"
    assert repaired[0].expected_output == "60\n"


def test_refine_test_cases_repairs_outputs_then_revalidates() -> None:
    workflow = object.__new__(QuestionGenerationWorkflow)
    workflow._build_refinement_state = MagicMock(return_value={})
    workflow._generate_bruteforce_solution = MagicMock(return_value="oracle source")
    workflow._validate_reference_solution = MagicMock(
        side_effect=[
            _report(passed=False, expected="59\n", actual="60"),
            _report(passed=True, expected="60\n", actual="60"),
            _report(passed=True, expected="60\n", actual="60"),
        ]
    )
    workflow._validate_oracle_solution = MagicMock(
        side_effect=[
            _report(passed=False, expected="59\n", actual="60"),
            _report(passed=True, expected="60\n", actual="60"),
        ]
    )

    response = workflow.refine_test_cases("recruiter-1", _draft())

    assert response.repaired_test_case_count == 1
    assert response.draft.sample_test_cases[0].input == "20 40\n"
    assert response.draft.sample_test_cases[0].expected_output == "60"
    assert response.draft.hidden_test_cases == _draft().hidden_test_cases
    assert response.validation_report.status == "passed"
    assert workflow._validate_reference_solution.call_count == 3


def test_refine_test_cases_repairs_solution_when_expected_matches_oracle() -> None:
    workflow = object.__new__(QuestionGenerationWorkflow)
    workflow._build_refinement_state = MagicMock(return_value={})
    workflow._generate_bruteforce_solution = MagicMock(return_value="oracle source")
    workflow._validate_reference_solution = MagicMock(
        side_effect=[
            _report(passed=False, expected="60\n", actual="59"),
            _report(passed=True, expected="60\n", actual="60"),
            _report(passed=True, expected="60\n", actual="60"),
        ]
    )
    workflow._validate_oracle_solution = MagicMock(
        side_effect=[
            _report(passed=True, expected="60\n", actual="60"),
            _report(passed=True, expected="60\n", actual="60"),
        ]
    )
    workflow._repair_reference_solution = MagicMock(
        return_value="a, b = map(int, input().split())\nprint(a + b)\n",
    )
    draft = _draft().model_copy(
        update={
            "sample_test_cases": [
                QuestionTestCase(
                    input="20 40\n",
                    expected_output="60\n",
                    is_sample=True,
                )
            ],
            "reference_solution": "print(59)\n",
        }
    )

    response = workflow.refine_test_cases("recruiter-1", draft)

    assert response.repaired_test_case_count == 0
    assert response.solution_changed is True
    assert response.draft.sample_test_cases == draft.sample_test_cases
    assert response.draft.reference_solution.endswith("print(a + b)\n")
    assert response.validation_report.status == "passed"


def test_refine_solution_uses_failures_without_changing_tests() -> None:
    workflow = object.__new__(QuestionGenerationWorkflow)
    workflow._build_refinement_state = MagicMock(return_value={})
    workflow._validate_reference_solution = MagicMock(
        side_effect=[
            _report(passed=False, expected="60\n", actual="59"),
            _report(passed=True, expected="60\n", actual="60"),
        ]
    )
    workflow._repair_reference_solution = MagicMock(
        return_value="a, b = map(int, input().split())\nprint(a + b)\n",
    )
    draft = _draft().model_copy(
        update={
            "sample_test_cases": [
                QuestionTestCase(
                    input="20 40\n",
                    expected_output="60\n",
                    is_sample=True,
                )
            ],
            "reference_solution": "print(59)\n",
        }
    )

    response = workflow.refine_solution("recruiter-1", draft)

    assert response.solution_changed is True
    assert response.draft.reference_solution.endswith("print(a + b)\n")
    assert response.draft.sample_test_cases == draft.sample_test_cases
    assert response.draft.hidden_test_cases == draft.hidden_test_cases
    assert response.validation_report.status == "passed"
    repair_call = workflow._repair_reference_solution.call_args.kwargs
    assert repair_call["sample_tests"] == draft.sample_test_cases
    assert repair_call["hidden_tests"] == []


def test_language_normalizer_keeps_requested_languages_only() -> None:
    languages = QuestionAgentToolsMixin._normalize_languages(
        ["python"],
        "python",
        ["java", "c++"],
    )

    assert languages == ["python", "java", "cpp"]


def test_language_normalizer_drops_stale_draft_languages() -> None:
    languages = QuestionAgentToolsMixin._normalize_languages(
        ["python", "java", "cpp", "c"],
        "python",
        ["python", "java"],
    )

    assert languages == ["python", "java"]


def test_metadata_scope_uses_latest_language_selection() -> None:
    workflow = object.__new__(QuestionGenerationWorkflow)
    draft = _draft().model_copy(
        update={
            "supported_languages": ["python", "java", "cpp", "c"],
            "reference_solutions": {
                language: ReferenceSolutionArtifact(
                    language=language,
                    source_code=f"{language} source",
                )
                for language in ["python", "java", "cpp", "c"]
            },
        },
    )
    request = QuestionAIDraftRequest(
        prompt="Classify metadata after removing unused languages.",
        generation_scope="metadata",
        reference_language="python",
        current_draft=draft,
        generation_settings=QuestionGenerationSettings(
            supported_languages=["python", "java"],
        ),
    )

    state = workflow._build_initial_state(request, [])
    response_draft = workflow._build_draft_from_state(state, request)

    assert state["supported_languages"] == ["python", "java"]
    assert response_draft.supported_languages == ["python", "java"]
    assert set(response_draft.reference_solutions) == {"python", "java"}


def test_other_language_generation_revalidates_missing_report() -> None:
    workflow = object.__new__(QuestionGenerationWorkflow)
    passed_report = SolutionValidationReport(
        status="passed",
        summary="Reference solution passed 2/2 execution checks.",
        passed_count=2,
        failed_count=0,
        sample_count=1,
        hidden_count=1,
    )
    workflow._validate_reference_solution = MagicMock(return_value=passed_report)
    workflow._generate_single_language_solution = MagicMock(return_value="source code")
    workflow._reference_solution_contract_error = MagicMock(return_value="")
    workflow._validate_source_against_tests = MagicMock(return_value=passed_report)

    result = workflow._multi_language_solution_node(
        {
            "reference_language": "python",
            "supported_languages": ["python", "java", "java", "cpp"],
            "validation_status": "passed",
            "sample_test_cases": [
                QuestionTestCase(
                    input="1 2\n",
                    expected_output="3\n",
                    is_sample=True,
                ),
            ],
            "hidden_test_cases": [
                QuestionTestCase(
                    input="4 5\n",
                    expected_output="9\n",
                    is_sample=False,
                ),
            ],
            "reference_solution": VALID_SOURCE,
            "reference_solutions": {
                "python": ReferenceSolutionArtifact(
                    language="python",
                    source_code=VALID_SOURCE,
                ),
            },
            "execution_time_limit_seconds": 2,
            "memory_limit_mb": 256,
            "notes": [],
            "execution_history": [],
        }
    )

    target_languages = [
        call.kwargs["target_language"]
        for call in workflow._generate_single_language_solution.call_args_list
    ]
    assert target_languages == ["java", "cpp"]
    assert set(result["reference_solutions"]) == {"python", "java", "cpp"}
    assert result["validation_status"] == "passed"
    workflow._validate_reference_solution.assert_called_once()


def test_other_language_generation_honors_single_target_language() -> None:
    workflow = object.__new__(QuestionGenerationWorkflow)
    passed_report = SolutionValidationReport(
        status="passed",
        summary="Primary solution passed.",
        passed_count=1,
        failed_count=0,
        sample_count=1,
        hidden_count=0,
    )
    workflow._generate_single_language_solution = MagicMock(return_value="source code")
    workflow._reference_solution_contract_error = MagicMock(return_value="")
    workflow._validate_source_against_tests = MagicMock(return_value=passed_report)

    workflow._multi_language_solution_node(
        {
            "reference_language": "python",
            "target_language": "c++",
            "supported_languages": ["python", "java", "cpp", "c"],
            "solution_validation": passed_report,
            "validation_status": "passed",
            "sample_test_cases": [
                QuestionTestCase(
                    input="1 2\n",
                    expected_output="3\n",
                    is_sample=True,
                )
            ],
            "hidden_test_cases": [],
            "reference_solution": VALID_SOURCE,
            "reference_solutions": {},
            "execution_time_limit_seconds": 2,
            "memory_limit_mb": 256,
            "notes": [],
            "execution_history": [],
        }
    )

    workflow._generate_single_language_solution.assert_called_once()
    assert (
        workflow._generate_single_language_solution.call_args.kwargs["target_language"]
        == "cpp"
    )


def test_other_language_generation_repairs_source_against_hidden_failures() -> None:
    workflow = object.__new__(QuestionGenerationWorkflow)
    primary_passed_report = SolutionValidationReport(
        status="passed",
        summary="Primary solution passed.",
        passed_count=2,
        failed_count=0,
        sample_count=1,
        hidden_count=1,
    )
    failed_translation_report = SolutionValidationReport(
        status="failed",
        summary="Reference solution failed 1 of 2 execution checks.",
        passed_count=1,
        failed_count=1,
        sample_count=1,
        hidden_count=1,
        results=[
            SolutionValidationCaseResult(
                bucket="hidden",
                index=1,
                passed=False,
                status="Wrong Answer",
                stdin="4 5\n",
                expected_output="9\n",
                actual_output="0\n",
            ),
        ],
    )
    repaired_translation_report = SolutionValidationReport(
        status="passed",
        summary="Reference solution passed 2/2 execution checks.",
        passed_count=2,
        failed_count=0,
        sample_count=1,
        hidden_count=1,
    )
    hidden_case = QuestionTestCase(
        input="4 5\n",
        expected_output="9\n",
        is_sample=False,
    )
    workflow._generate_single_language_solution = MagicMock(return_value="bad source")
    workflow._reference_solution_contract_error = MagicMock(return_value="")
    workflow._validate_source_against_tests = MagicMock(
        side_effect=[failed_translation_report, repaired_translation_report],
    )
    workflow._repair_reference_solution = MagicMock(return_value="fixed source")

    result = workflow._multi_language_solution_node(
        {
            "reference_language": "python",
            "target_language": "java",
            "supported_languages": ["python", "java"],
            "solution_validation": primary_passed_report,
            "validation_status": "passed",
            "sample_test_cases": [
                QuestionTestCase(
                    input="1 2\n",
                    expected_output="3\n",
                    is_sample=True,
                )
            ],
            "hidden_test_cases": [hidden_case],
            "reference_solution": VALID_SOURCE,
            "reference_solutions": {},
            "execution_time_limit_seconds": 2,
            "memory_limit_mb": 256,
            "notes": [],
            "execution_history": [],
        }
    )

    artifact = result["reference_solutions"]["java"]
    assert artifact.source_code == "fixed source"
    assert artifact.validation_status == "passed"
    assert "Repair round 1 updated the java source." in artifact.notes
    workflow._repair_reference_solution.assert_called_once()
    assert workflow._repair_reference_solution.call_args.kwargs["hidden_tests"] == [
        hidden_case,
    ]
