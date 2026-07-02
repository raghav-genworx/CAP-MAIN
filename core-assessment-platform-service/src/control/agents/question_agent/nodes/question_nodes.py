"""LangGraph node mixin aggregation for the question agent."""

from __future__ import annotations

from .constraint_node import ConstraintNodeMixin
from .constraint_script_node import ConstraintScriptNodeMixin
from .duplicate_detection_node import DuplicateDetectionNodeMixin
from .example_node import ExampleNodeMixin
from .hidden_test_node import HiddenTestNodeMixin
from .metadata_node import MetadataNodeMixin
from .multi_language_solution_node import MultiLanguageSolutionNodeMixin
from .orchestrator_node import OrchestratorNodeMixin
from .problem_statement_node import ProblemStatementNodeMixin
from .quality_review_node import QualityReviewNodeMixin
from .solution_node import SolutionNodeMixin
from .validation_node import ValidationNodeMixin


class QuestionAgentNodesMixin(
    OrchestratorNodeMixin,
    ProblemStatementNodeMixin,
    ConstraintNodeMixin,
    ExampleNodeMixin,
    HiddenTestNodeMixin,
    ConstraintScriptNodeMixin,
    SolutionNodeMixin,
    ValidationNodeMixin,
    MultiLanguageSolutionNodeMixin,
    MetadataNodeMixin,
    DuplicateDetectionNodeMixin,
    QualityReviewNodeMixin,
):
    """Compose all question-agent node mixins."""


__all__ = ["QuestionAgentNodesMixin"]
