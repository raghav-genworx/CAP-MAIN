"""Business-layer contract for source-code quality evaluation."""

from typing import Protocol

from handlers.http_clients.groq_code_quality import GroqCodeQualityEvaluator
from schemas.evaluation import AICodeQualitySignal


class CodeQualityEvaluator(Protocol):
    """Contract used by the evaluation service for AI code review."""

    def evaluate(self, *, language: str, source_code: str) -> AICodeQualitySignal:
        """Return a structured code-quality score for one submission."""

        ...


__all__ = ["CodeQualityEvaluator", "GroqCodeQualityEvaluator"]
