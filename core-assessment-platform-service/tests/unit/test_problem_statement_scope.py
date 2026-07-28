"""Regression coverage for statement-only question generation."""

from typing import Any
from unittest import TestCase

import pytest

from control.agents.question_agent.nodes.problem_statement_node import (
    ProblemStatementNodeMixin,
)
from control.agents.question_agent.states.question_state import (
    ProblemStatementOnlyOutput,
    QuestionGenerationState,
)

pytestmark = pytest.mark.unit


class _ProblemStatementNodeHarness(ProblemStatementNodeMixin):
    def __init__(self) -> None:
        self.schema_names: list[str] = []

    def _structured_completion(self, **kwargs: Any) -> ProblemStatementOnlyOutput:
        self.schema_names.append(kwargs["schema_name"])
        return ProblemStatementOnlyOutput(
            problem_statement=(
                "Given an integer, print its square using standard input and output."
            ),
            notes=[],
        )


class ProblemStatementScopeTests(TestCase):
    def test_problem_scope_changes_only_the_statement(self) -> None:
        harness = _ProblemStatementNodeHarness()
        state: QuestionGenerationState = {
            "generation_scope": "problem",
            "prompt": '{"task": "Generate only the problem statement."}',
            "title_hint": "Square an Integer",
            "title": "Square an Integer",
            "input_format": "One integer n.",
            "output_format": "The value n squared.",
            "constraints": "-1000 <= n <= 1000",
            "notes": [],
            "execution_history": [],
        }

        patch = harness._problem_statement_node(state)

        self.assertEqual(harness.schema_names, ["problem_statement_only"])
        self.assertEqual(
            set(patch),
            {"problem_statement", "notes", "execution_history"},
        )
        self.assertEqual(patch["notes"], [])
        self.assertIn(
            "generated only the problem statement",
            patch["execution_history"][0],
        )
