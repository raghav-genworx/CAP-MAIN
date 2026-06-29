"""LangGraph-powered question generation workflow using Groq."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from config.settings import Settings
from core.services.ai_gateway_service import AIGatewayService
from core.services.execution_adapter_service import ExecutionAdapterService
from schemas.question_bank import (
    DifficultyLevel,
    DifficultySource,
    MetadataStatus,
    QuestionAIDraftRequest,
    QuestionAIDraftResponse,
    QuestionCreateRequest,
    QuestionCreationMode,
    QuestionRecord,
    QuestionStatus,
    ValidationStatus,
)

from ..nodes.question_nodes import QuestionAgentNodesMixin
from ..prompts.question_prompts import SCOPE_NODE_SEQUENCE, SCOPE_SUMMARIES
from ..states.question_state import QuestionGenerationState

LOGGER = logging.getLogger(__name__)

FULL_NODE_SEQUENCE = [
    "orchestrator",
    "problem_statement",
    "constraints",
    "examples",
    "hidden_tests",
    "solution",
    "validation",
    "multi_language_solutions",
    "metadata",
    "duplicate_detection",
    "quality_review",
]

NODE_LABELS = {
    "orchestrator": "Preparing request",
    "problem_statement": "Writing problem statement",
    "constraints": "Building constraints and formats",
    "examples": "Creating sample tests",
    "hidden_tests": "Creating hidden and edge tests",
    "solution": "Generating primary solution",
    "validation": "Running validation",
    "multi_language_solutions": "Generating language solutions",
    "metadata": "Classifying metadata",
    "duplicate_detection": "Checking duplicates",
    "quality_review": "Reviewing quality",
}


class QuestionGenerationWorkflow(QuestionAgentNodesMixin):
    """LangGraph workflow that coordinates question-generation agents."""

    def __init__(
        self,
        settings: Settings,
        ai_gateway: AIGatewayService,
        execution_adapter: ExecutionAdapterService,
    ) -> None:
        self._settings = settings
        self._ai_gateway = ai_gateway
        self._execution_adapter = execution_adapter
        self._current_recruiter_uid = ""
        self._current_workflow_mode = "interactive"
        self._graph = self._build_graph().compile()

    def generate(
        self,
        recruiter_uid: str,
        request: QuestionAIDraftRequest,
        existing_questions: list[QuestionRecord],
    ) -> QuestionAIDraftResponse:
        """Run scoped or full generation and return a recruiter-ready draft."""

        try:
            self._current_recruiter_uid = recruiter_uid
            self._current_workflow_mode = (
                "publish_review"
                if request.generation_scope == "full"
                else "interactive"
            )
            state = self._build_initial_state(request, existing_questions)
            if request.generation_scope == "full":
                result = cast(QuestionGenerationState, self._graph.invoke(state))
            else:
                result = self._run_scoped_generation(state, request.generation_scope)
            result = self._normalize_final_test_counts(result, request)

            return self._response_from_result(result, request)
        except Exception as exc:  # pragma: no cover
            LOGGER.error("Question generation failed: %s", exc)
            error_message = f"AI generation failed: {str(exc)}"
            return QuestionAIDraftResponse(
                draft=None,
                summary="Generation Failed",
                notes=[],
                solution_validation=None,
                error=error_message,
            )

    def generate_events(
        self,
        recruiter_uid: str,
        request: QuestionAIDraftRequest,
        existing_questions: list[QuestionRecord],
    ) -> Iterator[dict[str, Any]]:
        """Run generation and yield graph movement progress events."""

        try:
            self._current_recruiter_uid = recruiter_uid
            self._current_workflow_mode = (
                "publish_review"
                if request.generation_scope == "full"
                else "interactive"
            )
            state = self._build_initial_state(request, existing_questions)
            node_sequence = (
                FULL_NODE_SEQUENCE
                if request.generation_scope == "full"
                else [
                    "orchestrator",
                    *SCOPE_NODE_SEQUENCE.get(request.generation_scope, []),
                ]
            )
            result = state
            total = max(len(node_sequence), 1)
            yield {
                "type": "start",
                "scope": request.generation_scope,
                "message": "Question agent started.",
                "current_node": None,
                "next_node": node_sequence[0] if node_sequence else None,
                "progress": 0,
            }
            for index, node_name in enumerate(node_sequence, start=1):
                previous_node = node_sequence[index - 2] if index > 1 else "START"
                yield {
                    "type": "edge",
                    "scope": request.generation_scope,
                    "message": f"{previous_node} -> {node_name}",
                    "current_node": previous_node,
                    "next_node": node_name,
                    "progress": round(((index - 1) / total) * 100),
                }
                yield {
                    "type": "node_start",
                    "scope": request.generation_scope,
                    "message": NODE_LABELS.get(
                        node_name,
                        node_name.replace("_", " ").title(),
                    ),
                    "current_node": node_name,
                    "next_node": None,
                    "progress": round(((index - 1) / total) * 100),
                }
                result = self._merge_state(result, self._node_runner(node_name)(result))
                yield {
                    "type": "node_complete",
                    "scope": request.generation_scope,
                    "message": f"{NODE_LABELS.get(node_name, node_name)} complete.",
                    "current_node": node_name,
                    "next_node": node_sequence[index] if index < total else "END",
                    "progress": round((index / total) * 100),
                }

            result["summary"] = SCOPE_SUMMARIES.get(
                request.generation_scope,
                "Generated content from your description.",
            )
            result = self._normalize_final_test_counts(result, request)
            yield {
                "type": "complete",
                "scope": request.generation_scope,
                "message": "Question agent completed.",
                "current_node": node_sequence[-1] if node_sequence else None,
                "next_node": "END",
                "progress": 100,
                "response": self._response_from_result(result, request).model_dump(
                    mode="json",
                ),
            }
        except Exception as exc:  # pragma: no cover
            LOGGER.error("Question generation stream failed: %s", exc)
            yield {
                "type": "error",
                "scope": request.generation_scope,
                "message": f"AI generation failed: {str(exc)}",
                "progress": 100,
            }

    def _build_initial_state(
        self,
        request: QuestionAIDraftRequest,
        existing_questions: list[QuestionRecord],
    ) -> QuestionGenerationState:
        """Normalize request context for one generation run."""

        current_draft = request.current_draft
        title_hint = (
            request.title_hint.strip()
            if request.title_hint
            else (current_draft.title.strip() if current_draft else "")
        )
        focus_tags = self._normalize_tokens(
            request.focus_tags or (current_draft.tags if current_draft else [])
        )
        settings = request.generation_settings
        state: QuestionGenerationState = {
            "prompt": request.prompt.strip(),
            "generation_scope": request.generation_scope,
            "difficulty_hint": "",
            "title_hint": title_hint,
            "focus_tags": focus_tags,
            "reference_language": (
                request.reference_language.strip()
                or (current_draft.reference_language if current_draft else "")
                or "python"
            ),
            "generation_settings": settings,
            "existing_question_titles": [
                question.title.strip()
                for question in existing_questions
                if question.title
            ],
            "existing_question_tags": [
                tag
                for question in existing_questions
                for tag in self._normalize_tokens(question.tags)
            ],
            "question_count": settings.question_count,
            "candidate_solve_time_minutes": settings.candidate_solve_time_minutes
            or settings.time_limit_minutes,
            "execution_time_limit_seconds": settings.execution_time_limit_seconds,
            "memory_limit_mb": settings.memory_limit_mb,
            "metadata_status": MetadataStatus.PENDING.value,
            "difficulty_source": DifficultySource.LEGACY.value,
            "notes": [
                "Question orchestrator received the recruiter description.",
                (
                    "Single-question mode is active; generation settings asking for "
                    f"{settings.question_count} question(s) will be "
                    "collapsed into one draft."
                    if settings.question_count > 1
                    else "Single-question mode confirmed."
                ),
            ],
            "execution_history": ["Orchestrator: request normalized"],
        }
        if title_hint:
            state["title"] = title_hint
        if current_draft:
            if current_draft.problem_statement.strip():
                state["problem_statement"] = current_draft.problem_statement.strip()
            if current_draft.constraints.strip():
                state["constraints"] = current_draft.constraints.strip()
            if current_draft.input_format.strip():
                state["input_format"] = current_draft.input_format.strip()
            if current_draft.input_explanation.strip():
                state["input_explanation"] = current_draft.input_explanation.strip()
            if current_draft.output_format.strip():
                state["output_format"] = current_draft.output_format.strip()
            if current_draft.output_explanation.strip():
                state["output_explanation"] = current_draft.output_explanation.strip()
            if current_draft.topics:
                state["topics"] = self._normalize_tokens(current_draft.topics)
            if current_draft.tags:
                state["tags"] = self._normalize_tokens(current_draft.tags)
            if current_draft.category.strip():
                state["category"] = current_draft.category.strip().lower()
            if current_draft.sample_test_cases:
                state["sample_test_cases"] = current_draft.sample_test_cases
            if current_draft.hidden_test_cases:
                state["hidden_test_cases"] = current_draft.hidden_test_cases
            if current_draft.reference_solution.strip():
                state["reference_solution"] = current_draft.reference_solution.strip()
            if current_draft.reference_solutions:
                state["reference_solutions"] = current_draft.reference_solutions
            if current_draft.solution_approach.strip():
                state["solution_approach"] = current_draft.solution_approach.strip()
            if current_draft.time_complexity.strip():
                state["time_complexity"] = current_draft.time_complexity.strip()
            if current_draft.space_complexity.strip():
                state["space_complexity"] = current_draft.space_complexity.strip()
            state["candidate_solve_time_minutes"] = (
                current_draft.candidate_solve_time_minutes
            )
            state["execution_time_limit_seconds"] = (
                current_draft.execution_time_limit_seconds
            )
            state["memory_limit_mb"] = current_draft.memory_limit_mb
            state["metadata_status"] = current_draft.metadata_status.value
            state["difficulty_source"] = current_draft.difficulty_source.value
            state["validation_status"] = current_draft.validation_status.value
            if current_draft.validation_report:
                state["solution_validation"] = current_draft.validation_report
            if current_draft.supported_languages:
                state["supported_languages"] = self._normalize_languages(
                    current_draft.supported_languages,
                    current_draft.reference_language,
                    request.generation_settings.supported_languages,
                )
        return state

    def _run_scoped_generation(
        self,
        state: QuestionGenerationState,
        scope: str,
    ) -> QuestionGenerationState:
        """Run only the agents needed for one builder section."""

        result = self._merge_state(state, self._orchestrator_node(state))
        for node_name in SCOPE_NODE_SEQUENCE.get(scope, []):
            runner = self._node_runner(node_name)
            result = self._merge_state(result, runner(result))

        result["summary"] = SCOPE_SUMMARIES.get(
            scope,
            "Generated content from your description.",
        )
        return result

    def _node_runner(
        self,
        node_name: str,
    ) -> Callable[[QuestionGenerationState], QuestionGenerationState]:
        node_runners = {
            "orchestrator": self._orchestrator_node,
            "problem_statement": self._problem_statement_node,
            "metadata": self._metadata_node,
            "constraints": self._constraint_node,
            "examples": self._example_node,
            "hidden_tests": self._hidden_test_node,
            "solution": self._solution_node,
            "validation": self._validation_node,
            "multi_language_solutions": self._multi_language_solution_node,
            "duplicate_detection": self._duplicate_detection_node,
            "quality_review": self._quality_review_node,
        }
        return node_runners[node_name]

    def _response_from_result(
        self,
        result: QuestionGenerationState,
        request: QuestionAIDraftRequest,
    ) -> QuestionAIDraftResponse:
        draft = self._build_draft_from_state(result, request)
        notes = self._append_notes(
            result.get("notes", []),
            result.get("summary", ""),
        )
        execution_history = result.get("execution_history", [])
        notes.extend(
            [
                "AI-drafted content is ready for recruiter review.",
                "Please verify sample and hidden test cases before publishing.",
                f"Generation scope: {request.generation_scope}.",
            ],
        )
        notes.extend(execution_history[:2])

        return QuestionAIDraftResponse(
            draft=draft,
            summary=result.get(
                "summary",
                SCOPE_SUMMARIES.get(
                    request.generation_scope,
                    "Generated content from your description.",
                ),
            ),
            notes=notes,
            solution_validation=result.get("solution_validation"),
        )

    def _normalize_final_test_counts(
        self,
        result: QuestionGenerationState,
        request: QuestionAIDraftRequest,
    ) -> QuestionGenerationState:
        """Keep generated testcase counts aligned with recruiter settings."""

        count_scopes = {
            "full",
            "examples",
            "tests",
            "tests_solution",
            "solution",
        }
        if request.generation_scope not in count_scopes:
            return result

        settings = request.generation_settings
        current_draft = request.current_draft
        sample_cases = [
            case.model_copy(update={"is_sample": True})
            for case in self._complete_test_cases(result.get("sample_test_cases", []))
        ]
        hidden_cases = [
            case.model_copy(update={"is_sample": False})
            for case in self._complete_test_cases(result.get("hidden_test_cases", []))
        ]
        if current_draft:
            sample_cases = self._merge_unique_test_cases(
                sample_cases,
                [
                    case.model_copy(update={"is_sample": True})
                    for case in self._complete_test_cases(
                        current_draft.sample_test_cases,
                    )
                ],
            )
            hidden_cases = self._merge_unique_test_cases(
                hidden_cases,
                [
                    case.model_copy(update={"is_sample": False})
                    for case in self._complete_test_cases(
                        current_draft.hidden_test_cases,
                    )
                ],
            )

        target_sample_count = max(1, settings.sample_test_case_count)
        target_hidden_count = max(1, settings.hidden_test_case_count)
        sample_cases = sample_cases[:target_sample_count]
        hidden_cases = hidden_cases[:target_hidden_count]

        notes = list(result.get("notes", []))
        if (
            len(sample_cases) == target_sample_count
            and len(hidden_cases) == target_hidden_count
        ):
            notes.append(
                (
                    "Exact testcase count verified: "
                    f"{target_sample_count} sample and {target_hidden_count} hidden."
                ),
            )
        else:
            notes.append(
                (
                    "Testcase count needs recruiter review: generated "
                    f"{len(sample_cases)}/{target_sample_count} sample and "
                    f"{len(hidden_cases)}/{target_hidden_count} hidden after "
                    "constraint filtering."
                ),
            )

        normalized = dict(result)
        normalized["sample_test_cases"] = sample_cases
        normalized["hidden_test_cases"] = hidden_cases
        normalized["notes"] = notes
        return cast(QuestionGenerationState, normalized)

    def _build_draft_from_state(
        self,
        result: QuestionGenerationState,
        request: QuestionAIDraftRequest,
    ) -> QuestionCreateRequest:
        """Map graph state into a draft payload with safe defaults."""

        settings = request.generation_settings
        difficulty_value = result.get("difficulty") or (
            request.difficulty.value
            if request.difficulty
            else DifficultyLevel.MEDIUM.value
        )
        supported_languages = (
            result.get("supported_languages") or settings.supported_languages
        )
        return QuestionCreateRequest(
            title=result.get("title") or request.title_hint or "Untitled Question",
            problem_statement=result.get("problem_statement", ""),
            difficulty=DifficultyLevel(difficulty_value),
            topics=result.get("topics", []),
            tags=result.get("tags", []),
            category=result.get("category", ""),
            constraints=result.get("constraints", ""),
            input_format=result.get("input_format", ""),
            input_explanation=result.get("input_explanation", ""),
            output_format=result.get("output_format", ""),
            output_explanation=result.get("output_explanation", ""),
            sample_test_cases=[
                case.model_copy(update={"is_sample": True})
                for case in result.get("sample_test_cases", [])
            ],
            hidden_test_cases=[
                case.model_copy(update={"is_sample": False})
                for case in result.get("hidden_test_cases", [])
            ],
            reference_solution=result.get("reference_solution", ""),
            reference_language=request.reference_language.strip() or "python",
            supported_languages=supported_languages,
            candidate_solve_time_minutes=result.get(
                "candidate_solve_time_minutes",
                settings.candidate_solve_time_minutes or settings.time_limit_minutes,
            ),
            execution_time_limit_seconds=result.get(
                "execution_time_limit_seconds",
                settings.execution_time_limit_seconds,
            ),
            memory_limit_mb=result.get("memory_limit_mb", settings.memory_limit_mb),
            metadata_status=MetadataStatus(
                result.get("metadata_status", MetadataStatus.PENDING.value),
            ),
            difficulty_source=DifficultySource(
                result.get("difficulty_source", DifficultySource.LEGACY.value),
            ),
            validation_report=result.get("solution_validation"),
            validation_status=ValidationStatus(
                result.get("validation_status", ValidationStatus.NOT_RUN.value),
            ),
            reference_solutions=result.get("reference_solutions", {}),
            solution_approach=result.get("solution_approach", ""),
            time_complexity=result.get("time_complexity", ""),
            space_complexity=result.get("space_complexity", ""),
            status=QuestionStatus.DRAFT,
            creation_mode=QuestionCreationMode.AI_ASSISTED,
        )

    @staticmethod
    def _merge_state(
        state: QuestionGenerationState,
        patch: QuestionGenerationState,
    ) -> QuestionGenerationState:
        merged = dict(state)
        merged.update(patch)
        return cast(QuestionGenerationState, merged)

    def _build_graph(self) -> StateGraph[QuestionGenerationState]:
        graph: StateGraph[QuestionGenerationState] = StateGraph(QuestionGenerationState)
        graph.add_node("orchestrator", self._orchestrator_node)
        graph.add_node("problem_statement", self._problem_statement_node)
        graph.add_node("metadata", self._metadata_node)
        graph.add_node("constraints", self._constraint_node)
        graph.add_node("examples", self._example_node)
        graph.add_node("hidden_tests", self._hidden_test_node)
        graph.add_node("solution", self._solution_node)
        graph.add_node("validation", self._validation_node)
        graph.add_node("multi_language_solutions", self._multi_language_solution_node)
        graph.add_node("duplicate_detection", self._duplicate_detection_node)
        graph.add_node("quality_review", self._quality_review_node)

        graph.add_edge(START, "orchestrator")
        graph.add_edge("orchestrator", "problem_statement")
        graph.add_edge("problem_statement", "constraints")
        graph.add_edge("constraints", "examples")
        graph.add_edge("examples", "hidden_tests")
        graph.add_edge("hidden_tests", "solution")
        graph.add_edge("solution", "validation")
        graph.add_edge("validation", "multi_language_solutions")
        graph.add_edge("multi_language_solutions", "metadata")
        graph.add_edge("metadata", "duplicate_detection")
        graph.add_edge("duplicate_detection", "quality_review")
        graph.add_edge("quality_review", END)
        return graph


__all__ = ["QuestionGenerationWorkflow"]
