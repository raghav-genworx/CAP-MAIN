"""LangGraph node mixin aggregation for the question agent.

Each graph node lives in its own file as a small "mixin" class (e.g.
`SolutionNodeMixin` defines `_solution_node`). This file bundles all of them
into one `QuestionAgentNodesMixin`, which `QuestionGenerationWorkflow` inherits.

Why mixins? So the workflow class can call `self._solution_node(...)` etc.
directly (that is how `_build_graph` registers them with LangGraph and how the
scoped/streaming drivers look them up by name), while each node's code stays in
its own focused file. The order the mixins are listed here does NOT affect the
execution order — that is defined entirely by the edges in `_build_graph`.
"""

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
