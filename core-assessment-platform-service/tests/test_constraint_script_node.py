"""Constraint-script node contracts for generated test cases."""

from unittest.mock import MagicMock

from control.agents.question_agent.graph.question_graph import (
    FULL_NODE_SEQUENCE,
    QuestionGenerationWorkflow,
)
from control.agents.question_agent.prompts.question_prompts import SCOPE_NODE_SEQUENCE
from control.agents.question_agent.states.question_state import (
    TestCaseRepairOutput as CaseRepairOutput,
)
from schemas.question_bank import (
    QuestionGenerationSettings,
)
from schemas.question_bank import (
    TestCase as QuestionTestCase,
)

VALIDATOR_SCRIPT = """
def validate_testcase(stdin: str, bucket: str):
    parts = stdin.strip().split()
    if len(parts) != 1:
        return False, "expected one integer"
    value = int(parts[0])
    if value < 0 or value > 120:
        return False, "age outside bounds"
    return True, "ok"
"""


def _state() -> dict:
    return {
        "title": "Voting Age",
        "problem_statement": "Read an age and print whether the person can vote.",
        "input_format": "One integer age.",
        "output_format": "Print Yes if age >= 18, else No.",
        "constraints": "0 <= age <= 120",
        "generation_settings": QuestionGenerationSettings(
            sample_test_case_count=1,
            hidden_test_case_count=1,
        ),
        "sample_test_cases": [
            QuestionTestCase(
                input="200\n",
                expected_output="Yes\n",
                is_sample=True,
            ),
        ],
        "hidden_test_cases": [
            QuestionTestCase(
                input="18\n",
                expected_output="Yes\n",
                is_sample=False,
            ),
        ],
        "notes": [],
        "execution_history": [],
    }


def test_constraint_script_node_replaces_only_script_rejected_cases() -> None:
    workflow = object.__new__(QuestionGenerationWorkflow)
    workflow._generate_constraint_validation_script = MagicMock(
        return_value=VALIDATOR_SCRIPT,
    )
    workflow._generate_constraint_replacement_candidates = MagicMock(
        return_value=CaseRepairOutput(
            sample_test_cases=[
                QuestionTestCase(
                    input="17\n",
                    expected_output="No\n",
                    is_sample=True,
                )
            ],
            hidden_test_cases=[],
            notes=[],
        ),
    )

    result = workflow._constraint_script_node(_state())

    assert result["sample_test_cases"][0].input == "17\n"
    assert result["sample_test_cases"][0].expected_output == "No\n"
    assert result["hidden_test_cases"][0].input == "18\n"
    assert result["constraint_validation_script"] == VALIDATOR_SCRIPT
    assert result["constraint_validation_warnings"] == []


def test_constraint_script_contract_rejects_unsafe_source() -> None:
    error = QuestionGenerationWorkflow._constraint_script_contract_error(
        "import os\n\ndef validate_testcase(stdin, bucket):\n    return True, 'ok'\n",
    )

    assert "top-level work" in error or "unsupported Python syntax" in error


def test_constraint_script_node_is_after_test_generation() -> None:
    assert FULL_NODE_SEQUENCE.index("constraint_script") > FULL_NODE_SEQUENCE.index(
        "hidden_tests",
    )
    assert FULL_NODE_SEQUENCE.index("constraint_script") < FULL_NODE_SEQUENCE.index(
        "solution",
    )
    assert SCOPE_NODE_SEQUENCE["tests"] == [
        "examples",
        "hidden_tests",
        "constraint_script",
    ]
    assert SCOPE_NODE_SEQUENCE["tests_solution"][2] == "constraint_script"
