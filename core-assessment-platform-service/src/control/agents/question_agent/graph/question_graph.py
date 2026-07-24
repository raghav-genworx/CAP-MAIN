"""LangGraph-powered question generation workflow using Groq.

=============================================================================
BIG PICTURE: How the question-creation LangGraph works
=============================================================================
A "question" here is a full competitive-programming problem: title, problem
statement, input/output formats, constraints, sample tests, hidden tests, a
reference solution, metadata (difficulty/tags), etc.

We build ONE LangGraph `StateGraph` (see `_build_graph` at the bottom of this
file). A LangGraph is just a directed graph of "nodes". Each node is a plain
Python function that:
    1. receives the shared state (a dict called `QuestionGenerationState`),
    2. does some work (usually one or more LLM calls + validation),
    3. returns a *partial* dict ("patch") that LangGraph merges back into the
       shared state before handing it to the next node.

The graph in this file is LINEAR (no branching). The nodes run in this order:

    START
      -> orchestrator            (plan / annotate the run)
      -> problem_statement       (title, statement, I/O formats, checker)
      -> constraints             (constraints, time/memory limits)
      -> examples                (sample test cases)
      -> hidden_tests            (hidden / edge / stress test cases)
      -> constraint_script       (auto-check every testcase input is legal)
      -> solution                (primary reference solution code)
      -> validation              (RUN the solution against the tests + repair)
      -> multi_language_solutions(translate solution to other languages)
      -> metadata                (classify difficulty, tags, category)
      -> duplicate_detection     (compare against existing question library)
      -> quality_review          (final publish-readiness score + summary)
    END

-----------------------------------------------------------------------------
THREE WAYS THIS WORKFLOW IS DRIVEN
-----------------------------------------------------------------------------
1. FULL generation (`generation_scope == "full"`):
   We call `self._graph.invoke(state)` -> the compiled LangGraph actually runs
   all 12 nodes end to end. This is the only path that uses LangGraph's own
   execution engine.

2. SCOPED generation (any other scope, e.g. "problem", "tests", "solution"):
   The UI wizard lets a recruiter regenerate just one section. Instead of
   running the whole graph, `_run_scoped_generation` runs only the handful of
   nodes needed for that section (looked up in `SCOPE_NODE_SEQUENCE`). It calls
   the SAME node functions directly, just not through the compiled graph.

3. STREAMED generation (`generate_events`):
   Same node sequence as (1) or (2), but run manually so we can `yield`
   Server-Sent-Events (progress bars, "node started/finished", per-test
   results) to the frontend as each node completes.

So: the node functions are the single source of truth, and they are reused by
all three drivers. `_build_graph` wires them for the "full" path; the scoped
and streamed paths replay the same nodes by hand.
=============================================================================
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Generator, Iterator
from datetime import UTC, datetime
from queue import Queue
from threading import Thread
from typing import Any, Literal, cast

# `StateGraph` is the LangGraph builder. `START`/`END` are the two special
# sentinel nodes every graph has: an edge from START marks the entry point and
# an edge to END marks a terminal node.
from langgraph.graph import END, START, StateGraph
from langsmith.run_trees import RunTree

from config.settings import Settings
from core.question_tag_taxonomy import (
    normalize_question_category,
    normalize_question_tags,
)
from core.services.output_validation import (
    default_checker_explanation,
    normalize_answer_validation_mode,
)
from handlers.http_clients.ai_gateway import AIGatewayService
from handlers.http_clients.execution import ExecutionAdapterService
from observability.tracing.langsmith import langsmith_run
from schemas.question_bank import (
    AnswerValidationMode,
    DifficultyLevel,
    DifficultySource,
    MetadataStatus,
    QuestionAIDraftContext,
    QuestionAIDraftRequest,
    QuestionAIDraftResponse,
    QuestionCreateRequest,
    QuestionCreationMode,
    QuestionDraftRefinementResponse,
    QuestionGenerationSettings,
    QuestionRecord,
    QuestionStatus,
    ReferenceSolutionArtifact,
    SolutionValidationCaseResult,
    SolutionValidationReport,
    TestCase,
    ValidationStatus,
)

from ..nodes.question_nodes import QuestionAgentNodesMixin
from ..prompts.bruteforce_solution_prompt import build_bruteforce_solution_prompt
from ..prompts.prompt_contract import build_task_system_prompt, build_task_user_prompt
from ..prompts.question_prompts import SCOPE_NODE_SEQUENCE, SCOPE_SUMMARIES
from ..states.question_state import (
    QuestionGenerationState,
    SolutionOutput,
    ValidationOutput,
)
from ..tools.question_tools import validation_progress_events

LOGGER = logging.getLogger(__name__)

# The exact node order for a "full" run. NOTE: this mirrors the edges wired in
# `_build_graph`, but it is kept as a plain list because the *streaming* driver
# (`generate_events`) walks nodes by hand instead of calling the compiled graph.
# If you change the graph edges below, keep this list in sync.
FULL_NODE_SEQUENCE = [
    "orchestrator",
    "problem_statement",
    "constraints",
    "examples",
    "hidden_tests",
    "constraint_script",
    "solution",
    "validation",
    "multi_language_solutions",
    "metadata",
    "duplicate_detection",
    "quality_review",
]

# Retry budgets for the imperative "repair loops" that live outside the graph.
# LangGraph edges are linear here, so correction is done by re-running work a
# bounded number of times rather than by looping edges in the graph itself.
QC_REFINEMENT_ROUNDS = 3  # brute-force-oracle QC passes in refine_test_cases
FINAL_TEST_COUNT_REPAIR_ROUNDS = 3  # attempts to hit the exact requested test count
ORACLE_EXPECTED_OUTPUT_REPAIR_ROUNDS = 2  # attempts to fix oracle-derived outputs
ORACLE_RUNTIME_LIMIT_SECONDS = 30  # brute-force oracle gets a generous time budget

# Human-friendly label per node, shown in SSE progress events and LangSmith spans.
NODE_LABELS = {
    "orchestrator": "Preparing request",
    "problem_statement": "Writing problem statement",
    "constraints": "Building constraints and formats",
    "examples": "Creating sample tests",
    "hidden_tests": "Creating hidden and edge tests",
    "constraint_script": "Checking testcase constraints",
    "solution": "Generating primary solution",
    "validation": "Running validation",
    "multi_language_solutions": "Generating language solutions",
    "metadata": "Classifying metadata",
    "duplicate_detection": "Checking duplicates",
    "quality_review": "Reviewing quality",
}


class QuestionGenerationWorkflow(QuestionAgentNodesMixin):
    """LangGraph workflow that coordinates question-generation agents.

    This class IS the workflow. It inherits every node implementation from
    `QuestionAgentNodesMixin` (which composes one mixin per node, e.g.
    `_problem_statement_node`, `_solution_node`, ...). So `self._problem_statement_node`
    below is defined in a sibling `nodes/*.py` file and mixed in here.
    """

    def __init__(
        self,
        settings: Settings,
        ai_gateway: AIGatewayService,
        execution_adapter: ExecutionAdapterService,
    ) -> None:
        self._settings = settings
        # Every node calls the model through this LLM gateway.
        self._ai_gateway = ai_gateway
        # Code runner (Judge0-style): used to actually EXECUTE reference solutions
        # against test cases during the validation node and QC repair loops.
        self._execution_adapter = execution_adapter
        self._current_recruiter_uid = ""
        self._current_workflow_mode = "interactive"
        # Build the graph once and compile it. `compile()` freezes the node/edge
        # wiring into an executable object; `self._graph.invoke(state)` runs it.
        self._graph = self._build_graph().compile()

    @property
    def current_ai_target(self) -> tuple[str, str]:
        """Return the provider/model selected for the current generation request."""

        return self._ai_gateway.current_target_metadata

    def generate(
        self,
        recruiter_uid: str,
        request: QuestionAIDraftRequest,
        existing_questions: list[QuestionRecord],
    ) -> QuestionAIDraftResponse:
        """Run scoped or full generation and return a recruiter-ready draft.

        This is the NON-streaming entry point. It picks one of two execution
        paths based on `request.generation_scope`:
          - "full"  -> invoke the compiled LangGraph (runs all 12 nodes).
          - anything else -> `_run_scoped_generation` runs just the nodes for
            that section.
        Everything is wrapped in a LangSmith run so the whole thing is traced.
        """

        try:
            self._current_recruiter_uid = recruiter_uid
            self._current_workflow_mode = (
                "publish_review"
                if request.generation_scope == "full"
                else "interactive"
            )
            # Turn the API request into the initial shared state dict (the seed
            # that flows through every node).
            state = self._build_initial_state(request, existing_questions)
            with langsmith_run(
                self._settings,
                self._langsmith_run_name(request),
                inputs=self._langsmith_run_inputs(request, state),
                tags=self._langsmith_tags(request),
                metadata=self._langsmith_metadata(recruiter_uid, request),
            ) as parent_run:
                if request.generation_scope == "full":
                    # ── PATH 1: real LangGraph execution ──
                    # `invoke` walks START -> ... -> END, running each node and
                    # merging its returned patch into the state automatically.
                    result = cast(
                        QuestionGenerationState,
                        self._graph.invoke(
                            state,
                            config=cast(
                                Any,
                                self._langsmith_graph_config(
                                    recruiter_uid,
                                    request,
                                ),
                            ),
                        ),
                    )
                else:
                    # ── PATH 2: scoped run ── only the nodes for this section.
                    result = self._run_scoped_generation(
                        state,
                        request.generation_scope,
                    )
                # Deterministic guardrail: force the final testcase counts to
                # exactly match what the recruiter asked for (the LLM can drift).
                result = self._normalize_final_test_counts(result, request)
                if parent_run is not None:
                    parent_run.end(
                        outputs=self._langsmith_result_outputs(result, request),
                    )

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

    # =========================================================================
    # REFINEMENT / QC HELPERS (run OUTSIDE the LangGraph)
    # -------------------------------------------------------------------------
    # `refine_test_cases` and `refine_solution` are separate entry points the
    # UI calls on an already-existing draft (the "fix my tests / fix my
    # solution" buttons). They do NOT run the graph. Instead they reuse the
    # node functions and the execution adapter inside imperative repair loops.
    # The core idea: generate an independent "brute-force oracle" solution and
    # trust its output to decide whether a failing test has a wrong expected
    # output (fix the test) or the reference solution is buggy (fix the code).
    # =========================================================================

    def refine_test_cases(
        self,
        recruiter_uid: str,
        draft: QuestionAIDraftContext,
        generation_settings: QuestionGenerationSettings | None = None,
    ) -> QuestionDraftRefinementResponse:
        """QC existing tests with a brute-force oracle and repair tests or source."""

        self._current_recruiter_uid = recruiter_uid
        self._current_workflow_mode = "interactive"
        state = self._build_refinement_state(draft, "tests", generation_settings)
        sample_tests = [
            case.model_copy(update={"is_sample": True})
            for case in self._complete_test_cases(draft.sample_test_cases)
        ]
        hidden_tests = [
            case.model_copy(update={"is_sample": False})
            for case in self._complete_test_cases(draft.hidden_test_cases)
        ]
        source_code = self._sanitize_reference_solution(draft.reference_solution)
        repaired_count = 0
        solution_changed = False
        qc_notes: list[str] = []

        sample_tests, hidden_tests, added_count, count_notes = (
            self._ensure_refinement_test_counts(
                state=state,
                sample_tests=sample_tests,
                hidden_tests=hidden_tests,
            )
        )
        repaired_count += added_count
        qc_notes.extend(count_notes)
        state = cast(
            QuestionGenerationState,
            {
                **state,
                "sample_test_cases": sample_tests,
                "hidden_test_cases": hidden_tests,
                "reference_solution": source_code,
            },
        )

        initial_report = self._validate_reference_solution(state)
        targets_met = self._refinement_targets_met(state, sample_tests, hidden_tests)
        if initial_report.status == "passed" and targets_met:
            summary = (
                "All requested test cases passed the first validation pass; no "
                "oracle repair was required."
            )
            if added_count:
                summary = (
                    f"Added {added_count} missing testcase"
                    f"{'' if added_count == 1 else 's'}, constraint-checked the "
                    "suite, and all requested cases passed validation."
                )
            return QuestionDraftRefinementResponse(
                draft=self._refined_draft(
                    draft,
                    sample_tests=sample_tests,
                    hidden_tests=hidden_tests,
                    reference_solution=source_code,
                    report=initial_report,
                ),
                validation_report=initial_report,
                summary=summary,
                repaired_test_case_count=repaired_count,
                solution_changed=False,
            )

        brute_force_source = self._generate_bruteforce_solution(state)
        current_report = initial_report

        for round_number in range(1, QC_REFINEMENT_ROUNDS + 1):
            failing_results = [
                result for result in current_report.results if not result.passed
            ]
            if not failing_results:
                break

            failing_sample_indexes = {
                result.index for result in failing_results if result.bucket == "sample"
            }
            failing_hidden_indexes = {
                result.index for result in failing_results if result.bucket == "hidden"
            }
            focused_sample_tests, focused_hidden_tests = self._tests_for_results(
                sample_tests,
                hidden_tests,
                failing_results,
            )
            focused_state = cast(
                QuestionGenerationState,
                {
                    **state,
                    "sample_test_cases": focused_sample_tests,
                    "hidden_test_cases": focused_hidden_tests,
                    "reference_solution": source_code,
                },
            )
            primary_report = self._validate_reference_solution(focused_state)
            oracle_report = self._validate_oracle_solution(
                focused_state,
                brute_force_source,
            )
            answer_mode = self._answer_validation_kwargs(state)[
                "answer_validation_mode"
            ]
            if answer_mode in {
                AnswerValidationMode.MULTIPLE_VALID.value,
                AnswerValidationMode.CONSTRUCTIVE.value,
            }:
                repaired_focused_sample_tests = focused_sample_tests
                repaired_focused_hidden_tests = focused_hidden_tests
                expected_output_changes = 0
            else:
                (
                    repaired_focused_sample_tests,
                    repaired_focused_hidden_tests,
                    expected_output_changes,
                ) = self._repair_expected_outputs_from_oracle(
                    focused_sample_tests,
                    focused_hidden_tests,
                    oracle_report,
                )
            if expected_output_changes:
                sample_tests = self._replace_failed_test_cases(
                    sample_tests,
                    failing_sample_indexes,
                    repaired_focused_sample_tests,
                )
                hidden_tests = self._replace_failed_test_cases(
                    hidden_tests,
                    failing_hidden_indexes,
                    repaired_focused_hidden_tests,
                )
                repaired_count += expected_output_changes
                qc_notes.append(
                    (
                        f"Round {round_number}: brute-force oracle corrected "
                        f"{expected_output_changes} expected output"
                        f"{'' if expected_output_changes == 1 else 's'}."
                    ),
                )
                focused_repair_report = self._validate_reference_solution(
                    cast(
                        QuestionGenerationState,
                        {
                            **state,
                            "sample_test_cases": repaired_focused_sample_tests,
                            "hidden_test_cases": repaired_focused_hidden_tests,
                            "reference_solution": source_code,
                        },
                    )
                )
                current_report = self._merge_focused_validation_report(
                    current_report,
                    focused_repair_report,
                    sample_indexes=failing_sample_indexes,
                    hidden_indexes=failing_hidden_indexes,
                )
                if current_report.status == "passed":
                    break
                continue

            solution_repair_results = self._solution_repair_results_from_oracle(
                primary_report,
                oracle_report,
            )
            if solution_repair_results:
                repair_report = self._report_for_results(
                    primary_report,
                    solution_repair_results,
                )
                repair_sample_tests, repair_hidden_tests = self._tests_for_results(
                    focused_sample_tests,
                    focused_hidden_tests,
                    solution_repair_results,
                )
                repaired_source = self._repair_reference_solution(
                    state=focused_state,
                    source_code=source_code,
                    validation_report=repair_report,
                    sample_tests=repair_sample_tests,
                    hidden_tests=repair_hidden_tests,
                    round_number=round_number,
                )
                if repaired_source.strip() != source_code.strip():
                    source_code = repaired_source
                    solution_changed = True
                    qc_notes.append(
                        (
                            f"Round {round_number}: expected output matched the "
                            "brute-force oracle, so the solution was repaired."
                        ),
                    )
                    current_report = self._validate_reference_solution(
                        cast(
                            QuestionGenerationState,
                            {
                                **state,
                                "sample_test_cases": sample_tests,
                                "hidden_test_cases": hidden_tests,
                                "reference_solution": source_code,
                            },
                        )
                    )
                    if current_report.status == "passed":
                        break
                    continue

            qc_notes.append(
                f"Round {round_number}: QC found no further automatic repairs.",
            )
            break

        final_report = current_report
        targets_met = self._refinement_targets_met(state, sample_tests, hidden_tests)
        if final_report.status == "passed" and repaired_count and solution_changed:
            summary = (
                f"QC repaired {repaired_count} testcase"
                f"{'' if repaired_count == 1 else 's'}, repaired the solution, "
                "and re-ran all tests successfully."
            )
        elif final_report.status == "passed" and repaired_count:
            summary = (
                f"QC repaired {repaired_count} testcase"
                f"{'' if repaired_count == 1 else 's'} with constraint checks "
                "and the brute-force oracle, then re-ran validation successfully."
            )
        elif final_report.status == "passed" and solution_changed:
            summary = (
                "QC kept expected outputs unchanged, repaired the solution using "
                "the brute-force oracle evidence, and re-ran all tests successfully."
            )
        elif not targets_met:
            settings = state["generation_settings"]
            summary = (
                "QC completed but could not reach the requested testcase count. "
                f"Current suite: {len(sample_tests)}/{settings.sample_test_case_count} "
                f"sample and {len(hidden_tests)}/{settings.hidden_test_case_count} "
                "hidden after constraint filtering. " + " ".join(qc_notes[-2:])
            )
        else:
            summary = (
                "QC completed but remaining failures need recruiter review. "
                + " ".join(qc_notes[-2:])
            )
        return QuestionDraftRefinementResponse(
            draft=self._refined_draft(
                draft,
                sample_tests=sample_tests,
                hidden_tests=hidden_tests,
                reference_solution=source_code,
                report=final_report,
            ),
            validation_report=final_report,
            summary=summary,
            repaired_test_case_count=repaired_count,
            solution_changed=solution_changed,
        )

    def refine_solution(
        self,
        recruiter_uid: str,
        draft: QuestionAIDraftContext,
        generation_settings: QuestionGenerationSettings | None = None,
    ) -> QuestionDraftRefinementResponse:
        """Repair source from the problem contract, using failures as evidence."""

        self._current_recruiter_uid = recruiter_uid
        self._current_workflow_mode = "interactive"
        state = self._build_refinement_state(draft, "solution", generation_settings)
        initial_report = self._validate_reference_solution(state)
        sample_tests = list(draft.sample_test_cases)
        hidden_tests = list(draft.hidden_test_cases)
        source_code = self._sanitize_reference_solution(draft.reference_solution)
        repaired_source = source_code
        if initial_report.status != "passed":
            failing_sample_indexes = {
                result.index
                for result in initial_report.results
                if result.bucket == "sample" and not result.passed
            }
            failing_hidden_indexes = {
                result.index
                for result in initial_report.results
                if result.bucket == "hidden" and not result.passed
            }
            repaired_source = self._repair_reference_solution(
                state=state,
                source_code=source_code,
                validation_report=initial_report,
                sample_tests=[
                    test_case
                    for index, test_case in enumerate(sample_tests, start=1)
                    if index in failing_sample_indexes
                ],
                hidden_tests=[
                    test_case
                    for index, test_case in enumerate(hidden_tests, start=1)
                    if index in failing_hidden_indexes
                ],
                round_number=1,
            )

        solution_changed = repaired_source.strip() != source_code.strip()
        refined_state = cast(
            QuestionGenerationState,
            {**state, "reference_solution": repaired_source},
        )
        final_report = self._validate_reference_solution(refined_state)
        if initial_report.status == "passed":
            summary = "The current solution already passes all existing tests."
        elif solution_changed:
            summary = (
                "Repaired the solution from the problem statement and constraints, "
                "then re-ran all tests."
            )
        else:
            summary = "The solution could not be changed; review remaining failures."
        return QuestionDraftRefinementResponse(
            draft=self._refined_draft(
                draft,
                sample_tests=sample_tests,
                hidden_tests=hidden_tests,
                reference_solution=repaired_source,
                report=final_report,
            ),
            validation_report=final_report,
            summary=summary,
            solution_changed=solution_changed,
        )

    def _generate_bruteforce_solution(
        self,
        state: QuestionGenerationState,
    ) -> str:
        """Generate an independent correctness-first oracle for testcase QC."""

        language = self._normalize_solution_language(
            state.get("reference_language", "python"),
        )
        system_prompt, user_prompt = build_bruteforce_solution_prompt(
            state,
            language=language,
            sample_cases=[
                {"input": case.input, "is_sample": case.is_sample}
                for case in state.get("sample_test_cases", [])
            ],
            hidden_cases=[
                {"input": case.input, "is_sample": case.is_sample}
                for case in state.get("hidden_test_cases", [])
            ],
            strict_contract_guidance=self._strict_solution_contract_guidance(language),
            language_contract_guidance=self._solution_contract_guidance(language),
        )
        model = self._structured_completion(
            schema_name="bruteforce_solution",
            schema_model=SolutionOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return self._ensure_runnable_reference_solution(
            state=state,
            candidate=model.reference_solution,
            language=language,
            schema_name="bruteforce_solution_contract_retry",
            rejection_context=(
                "Brute-force oracle generation did not satisfy the runnable-code "
                "contract."
            ),
        )

    def _validate_oracle_solution(
        self,
        state: QuestionGenerationState,
        brute_force_source: str,
    ) -> SolutionValidationReport:
        """Run the brute-force oracle against the current expected outputs."""

        language = self._normalize_solution_language(
            state.get("reference_language", "python"),
        )
        return self._validate_source_against_tests(
            language=language,
            source_code=brute_force_source,
            sample_tests=self._complete_test_cases(
                state.get("sample_test_cases", []),
            ),
            hidden_tests=self._complete_test_cases(
                state.get("hidden_test_cases", []),
            ),
            rounds=[],
            time_limit_seconds=ORACLE_RUNTIME_LIMIT_SECONDS,
            memory_limit_kb=(state.get("memory_limit_mb", 256) * 1024),
            **self._answer_validation_kwargs(state),
        )

    def _normalize_expected_outputs_with_oracle(
        self,
        state: QuestionGenerationState,
    ) -> QuestionGenerationState:
        """Replace testcase expected outputs with brute-force oracle stdout."""

        sample_tests = [
            case.model_copy(update={"is_sample": True})
            for case in self._complete_test_cases(state.get("sample_test_cases", []))
        ]
        hidden_tests = [
            case.model_copy(update={"is_sample": False})
            for case in self._complete_test_cases(state.get("hidden_test_cases", []))
        ]
        if not sample_tests and not hidden_tests:
            return {
                "sample_test_cases": sample_tests,
                "hidden_test_cases": hidden_tests,
            }

        notes: list[str] = []
        working_state = cast(
            QuestionGenerationState,
            {
                **state,
                "sample_test_cases": sample_tests,
                "hidden_test_cases": hidden_tests,
            },
        )
        oracle_source = self._generate_bruteforce_solution(working_state)
        last_sample_tests = sample_tests
        last_hidden_tests = hidden_tests

        for attempt in range(1, ORACLE_EXPECTED_OUTPUT_REPAIR_ROUNDS + 1):
            oracle_state = cast(
                QuestionGenerationState,
                {
                    **working_state,
                    "sample_test_cases": last_sample_tests,
                    "hidden_test_cases": last_hidden_tests,
                },
            )
            oracle_report = self._validate_oracle_solution(oracle_state, oracle_source)
            if not self._oracle_report_has_complete_outputs(oracle_report):
                notes.append(
                    (
                        f"Oracle attempt {attempt}: execution did not produce "
                        "usable output for every testcase; refining oracle."
                    ),
                )
                oracle_source = self._refine_oracle_solution_from_review(
                    state=oracle_state,
                    oracle_source=oracle_source,
                    review_notes=[
                        oracle_report.summary,
                        *oracle_report.runner_notes,
                        *[
                            result.message or result.status
                            for result in oracle_report.results
                            if not result.passed
                        ],
                    ],
                    attempt=attempt,
                )
                continue

            last_sample_tests, last_hidden_tests, changed_count = (
                self._replace_expected_outputs_from_oracle_actuals(
                    last_sample_tests,
                    last_hidden_tests,
                    oracle_report,
                )
            )
            review = self._review_oracle_backed_test_cases(
                state=oracle_state,
                oracle_source=oracle_source,
                sample_tests=last_sample_tests,
                hidden_tests=last_hidden_tests,
            )
            if review.warnings:
                notes.extend(
                    f"Oracle testcase review: {warning}" for warning in review.warnings
                )
                oracle_source = self._refine_oracle_solution_from_review(
                    state=oracle_state,
                    oracle_source=oracle_source,
                    review_notes=review.warnings,
                    attempt=attempt,
                )
                continue

            notes.append(
                (
                    "Oracle normalized expected outputs for "
                    f"{changed_count} testcase"
                    f"{'' if changed_count == 1 else 's'} using a "
                    f"{ORACLE_RUNTIME_LIMIT_SECONDS}s brute-force run."
                ),
            )
            return {
                "sample_test_cases": last_sample_tests,
                "hidden_test_cases": last_hidden_tests,
                "notes": self._append_notes(state.get("notes", []), *notes),
                "execution_history": self._append_notes(
                    state.get("execution_history", []),
                    "Oracle: normalized testcase expected outputs",
                ),
            }

        notes.append(
            (
                "Oracle review still reported issues after refinement; using the "
                "latest oracle-backed expected outputs for validation."
            ),
        )
        return {
            "sample_test_cases": last_sample_tests,
            "hidden_test_cases": last_hidden_tests,
            "notes": self._append_notes(state.get("notes", []), *notes),
            "execution_history": self._append_notes(
                state.get("execution_history", []),
                "Oracle: normalized testcase expected outputs with warnings",
            ),
        }

    @staticmethod
    def _oracle_report_has_complete_outputs(
        oracle_report: SolutionValidationReport,
    ) -> bool:
        if not oracle_report.results:
            return False
        return all(
            result.passed
            or QuestionGenerationWorkflow._is_expected_output_repair_candidate(
                result,
            )
            for result in oracle_report.results
        )

    @staticmethod
    def _replace_expected_outputs_from_oracle_actuals(
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        oracle_report: SolutionValidationReport,
    ) -> tuple[list[TestCase], list[TestCase], int]:
        repaired_sample_tests = list(sample_tests)
        repaired_hidden_tests = list(hidden_tests)
        changed_count = 0
        for result in oracle_report.results:
            if not (
                result.passed
                or QuestionGenerationWorkflow._is_expected_output_repair_candidate(
                    result,
                )
            ):
                continue
            target_tests = (
                repaired_sample_tests
                if result.bucket == "sample"
                else repaired_hidden_tests
            )
            target_index = result.index - 1
            if target_index < 0 or target_index >= len(target_tests):
                continue
            original = target_tests[target_index]
            if original.expected_output == result.actual_output:
                continue
            target_tests[target_index] = original.model_copy(
                update={"expected_output": result.actual_output},
            )
            changed_count += 1
        return repaired_sample_tests, repaired_hidden_tests, changed_count

    def _review_oracle_backed_test_cases(
        self,
        *,
        state: QuestionGenerationState,
        oracle_source: str,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
    ) -> ValidationOutput:
        system_prompt = build_task_system_prompt(
            role="oracle-backed testcase correctness auditor",
            objective=(
                "Verify whether oracle-produced expected outputs follow the "
                "problem contract for every testcase input."
            ),
            rules=(
                "Treat testcase inputs as fixed.",
                "Warn only about concrete incorrect, ambiguous, or impossible cases.",
                "Do not ask for optimized-solution behavior.",
            ),
        )
        user_prompt = build_task_user_prompt(
            task="Review the oracle-backed expected outputs for correctness.",
            context={
                "problem_contract": {
                    "title": state.get("title", ""),
                    "problem_statement": state.get("problem_statement", ""),
                    "input_format": state.get("input_format", ""),
                    "output_format": state.get("output_format", ""),
                    "constraints": state.get("constraints", ""),
                },
                "answer_validation": {
                    "mode": state.get("answer_validation_mode", "exact"),
                    "explanation": state.get("output_checker_explanation", ""),
                },
                "oracle_source": oracle_source,
                "oracle_runtime_seconds": ORACLE_RUNTIME_LIMIT_SECONDS,
                "testcases": {
                    "sample": self._prompt_cases(sample_tests),
                    "hidden": self._prompt_cases(hidden_tests),
                },
            },
            requirements=(
                (
                    "If every expected_output is correct, put a concise success "
                    "statement in checks and leave warnings empty."
                ),
                (
                    "If any expected_output appears wrong, ambiguous, or produced "
                    "by flawed oracle logic, name the exact testcase bucket and "
                    "index in warnings."
                ),
                (
                    "For non-exact answer validation, verify that expected_output "
                    "is at least one valid exemplar accepted by the problem rules."
                ),
            ),
        )
        return cast(
            ValidationOutput,
            self._structured_completion(
                schema_name="oracle_testcase_review",
                schema_model=ValidationOutput,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            ),
        )

    def _refine_oracle_solution_from_review(
        self,
        *,
        state: QuestionGenerationState,
        oracle_source: str,
        review_notes: list[str],
        attempt: int,
    ) -> str:
        language = self._normalize_solution_language(
            state.get("reference_language", "python"),
        )
        system_prompt = build_task_system_prompt(
            role="brute-force oracle repair engineer",
            objective=(
                "Repair the correctness-first oracle so it computes testcase "
                "outputs from the problem contract."
            ),
            rules=(
                "Do not hard-code testcase outputs.",
                "Prefer simple exhaustive or direct simulation logic.",
                "Keep complete STDIN/STDOUT source code only in reference_solution.",
            ),
        )
        user_prompt = build_task_user_prompt(
            task="Repair the oracle source using the review notes.",
            context={
                "problem_contract": {
                    "title": state.get("title", ""),
                    "problem_statement": state.get("problem_statement", ""),
                    "input_format": state.get("input_format", ""),
                    "output_format": state.get("output_format", ""),
                    "constraints": state.get("constraints", ""),
                },
                "oracle_language": language,
                "current_oracle_source": oracle_source,
                "review_notes": review_notes,
                "testcase_inputs": {
                    "sample": [
                        case.input for case in state.get("sample_test_cases", [])
                    ],
                    "hidden": [
                        case.input for case in state.get("hidden_test_cases", [])
                    ],
                },
            },
            requirements=(
                self._strict_solution_contract_guidance(language),
                self._solution_contract_guidance(language),
                "Set reference_solution to repaired complete source code only.",
                "Set supported_languages to only oracle_language.",
                "Set reference_solutions to an empty object.",
            ),
        )
        model = self._structured_completion(
            schema_name=f"oracle_solution_repair_{attempt}",
            schema_model=SolutionOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return self._ensure_runnable_reference_solution(
            state=state,
            candidate=model.reference_solution,
            language=language,
            schema_name=f"oracle_solution_repair_contract_{attempt}",
            rejection_context=(
                "Oracle repair did not satisfy the runnable-code contract."
            ),
        )

    def _repair_expected_outputs_from_oracle(
        self,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        oracle_report: SolutionValidationReport,
    ) -> tuple[list[TestCase], list[TestCase], int]:
        """Use brute-force actual output as the repaired expected output."""

        repaired_sample_tests = list(sample_tests)
        repaired_hidden_tests = list(hidden_tests)
        repaired_count = 0
        for result in oracle_report.results:
            if result.passed or not self._is_expected_output_repair_candidate(result):
                continue
            target_tests = (
                repaired_sample_tests
                if result.bucket == "sample"
                else repaired_hidden_tests
            )
            target_index = result.index - 1
            if target_index < 0 or target_index >= len(target_tests):
                continue
            original = target_tests[target_index]
            if original.expected_output == result.actual_output:
                continue
            target_tests[target_index] = original.model_copy(
                update={"expected_output": result.actual_output},
            )
            repaired_count += 1
        return repaired_sample_tests, repaired_hidden_tests, repaired_count

    @staticmethod
    def _solution_repair_results_from_oracle(
        primary_report: SolutionValidationReport,
        oracle_report: SolutionValidationReport,
    ) -> list[SolutionValidationCaseResult]:
        """Return primary failures where the brute-force oracle validates expected."""

        oracle_results = {
            (result.bucket, result.index): result for result in oracle_report.results
        }
        return [
            result
            for result in primary_report.results
            if not result.passed
            and oracle_results.get((result.bucket, result.index))
            and oracle_results[(result.bucket, result.index)].passed
        ]

    @staticmethod
    def _report_for_results(
        report: SolutionValidationReport,
        results: list[SolutionValidationCaseResult],
    ) -> SolutionValidationReport:
        """Create a focused validation report for solution repair prompts."""

        return report.model_copy(
            update={
                "results": results,
                "passed_count": 0,
                "failed_count": len(results),
                "summary": (
                    f"Reference solution failed {len(results)} oracle-confirmed "
                    "execution check"
                    f"{'' if len(results) == 1 else 's'}."
                ),
            },
        )

    @staticmethod
    def _tests_for_results(
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        results: list[SolutionValidationCaseResult],
    ) -> tuple[list[TestCase], list[TestCase]]:
        """Return testcase rows that correspond to the supplied result list."""

        sample_indexes = {
            result.index for result in results if result.bucket == "sample"
        }
        hidden_indexes = {
            result.index for result in results if result.bucket == "hidden"
        }
        return (
            [
                test_case
                for index, test_case in enumerate(sample_tests, start=1)
                if index in sample_indexes
            ],
            [
                test_case
                for index, test_case in enumerate(hidden_tests, start=1)
                if index in hidden_indexes
            ],
        )

    def _build_refinement_state(
        self,
        draft: QuestionAIDraftContext,
        scope: Literal["tests", "solution"],
        generation_settings: QuestionGenerationSettings | None = None,
    ) -> QuestionGenerationState:
        """Build normal agent state while preserving the complete current draft."""

        settings = generation_settings or QuestionGenerationSettings()
        request = QuestionAIDraftRequest(
            prompt=(
                "Refine the existing draft using execution evidence while preserving "
                "the authoritative problem contract."
            ),
            generation_scope=scope,
            reference_language=draft.reference_language,
            title_hint=draft.title or None,
            focus_tags=draft.tags,
            current_draft=draft,
            generation_settings=QuestionGenerationSettings(
                topics=settings.topics or draft.topics,
                supported_languages=settings.supported_languages
                or draft.supported_languages,
                candidate_solve_time_minutes=(
                    settings.candidate_solve_time_minutes
                    or draft.candidate_solve_time_minutes
                ),
                time_limit_minutes=(
                    settings.time_limit_minutes or draft.candidate_solve_time_minutes
                ),
                execution_time_limit_seconds=(
                    settings.execution_time_limit_seconds
                    or draft.execution_time_limit_seconds
                ),
                memory_limit_mb=settings.memory_limit_mb or draft.memory_limit_mb,
                sample_test_case_count=max(1, settings.sample_test_case_count),
                hidden_test_case_count=max(1, settings.hidden_test_case_count),
                edge_case_count=settings.edge_case_count,
                stress_test_count=settings.stress_test_count,
                interview_style=settings.interview_style,
                company_style=settings.company_style,
                question_count=settings.question_count,
                easy_count=settings.easy_count,
                medium_count=settings.medium_count,
                hard_count=settings.hard_count,
            ),
        )
        return self._build_initial_state(request, [])

    def _refinement_targets_met(
        self,
        state: QuestionGenerationState,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
    ) -> bool:
        settings = state["generation_settings"]
        return len(self._complete_test_cases(sample_tests)) >= max(
            1, settings.sample_test_case_count
        ) and len(self._complete_test_cases(hidden_tests)) >= max(
            1, settings.hidden_test_case_count
        )

    def _ensure_refinement_test_counts(
        self,
        *,
        state: QuestionGenerationState,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
    ) -> tuple[list[TestCase], list[TestCase], int, list[str]]:
        """Generate missing tests, constraint-check them, and preserve exact targets."""

        settings = state["generation_settings"]
        target_sample_count = max(1, settings.sample_test_case_count)
        target_hidden_count = max(1, settings.hidden_test_case_count)
        sample_tests = self._complete_test_cases(sample_tests)
        hidden_tests = self._complete_test_cases(hidden_tests)
        original_total = len(sample_tests) + len(hidden_tests)
        notes: list[str] = []

        for attempt in range(1, 3):
            working_state = cast(
                QuestionGenerationState,
                {
                    **state,
                    "sample_test_cases": sample_tests,
                    "hidden_test_cases": hidden_tests,
                    "generation_settings": settings,
                },
            )

            if len(sample_tests) < target_sample_count:
                generated = self._example_node(working_state)
                sample_tests = self._merge_unique_test_cases(
                    sample_tests,
                    [
                        case.model_copy(update={"is_sample": True})
                        for case in self._complete_test_cases(
                            generated.get("sample_test_cases", []),
                        )
                    ],
                )
                notes.append(
                    (
                        f"Attempt {attempt}: generated sample cases "
                        f"({len(sample_tests)}/{target_sample_count})."
                    ),
                )

            working_state = cast(
                QuestionGenerationState,
                {
                    **working_state,
                    "sample_test_cases": sample_tests,
                    "hidden_test_cases": hidden_tests,
                },
            )
            if len(hidden_tests) < target_hidden_count:
                generated = self._hidden_test_node(working_state)
                hidden_tests = self._merge_unique_test_cases(
                    hidden_tests,
                    [
                        case.model_copy(update={"is_sample": False})
                        for case in self._complete_test_cases(
                            generated.get("hidden_test_cases", []),
                        )
                    ],
                )
                notes.append(
                    (
                        f"Attempt {attempt}: generated hidden cases "
                        f"({len(hidden_tests)}/{target_hidden_count})."
                    ),
                )

            checked = self._constraint_script_node(
                cast(
                    QuestionGenerationState,
                    {
                        **working_state,
                        "sample_test_cases": sample_tests,
                        "hidden_test_cases": hidden_tests,
                    },
                ),
            )
            sample_tests = [
                case.model_copy(update={"is_sample": True})
                for case in self._complete_test_cases(
                    checked.get("sample_test_cases", sample_tests),
                )
            ]
            hidden_tests = [
                case.model_copy(update={"is_sample": False})
                for case in self._complete_test_cases(
                    checked.get("hidden_test_cases", hidden_tests),
                )
            ]
            notes.extend(checked.get("constraint_validation_warnings", []))
            if (
                len(sample_tests) >= target_sample_count
                and len(hidden_tests) >= target_hidden_count
            ):
                break

        sample_tests = sample_tests[:target_sample_count]
        hidden_tests = hidden_tests[:target_hidden_count]
        added_count = max(0, len(sample_tests) + len(hidden_tests) - original_total)
        if not self._refinement_targets_met(state, sample_tests, hidden_tests):
            notes.append(
                (
                    "Could not reach requested testcase count after constraint "
                    f"checks: {len(sample_tests)}/{target_sample_count} sample, "
                    f"{len(hidden_tests)}/{target_hidden_count} hidden."
                ),
            )
        return sample_tests, hidden_tests, added_count, notes

    @staticmethod
    def _count_expected_output_changes(
        before: list[TestCase],
        after: list[TestCase],
    ) -> int:
        return sum(
            1
            for old, new in zip(before, after, strict=False)
            if old.expected_output != new.expected_output
        )

    @staticmethod
    def _refined_draft(
        draft: QuestionAIDraftContext,
        *,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        reference_solution: str,
        report: SolutionValidationReport,
    ) -> QuestionCreateRequest:
        payload = draft.model_dump()
        tags = normalize_question_tags([*draft.tags, *draft.topics], limit=6)
        primary_language = QuestionGenerationWorkflow._normalize_solution_language(
            draft.reference_language,
        )
        reference_solutions = dict(draft.reference_solutions)
        if reference_solution.strip():
            reference_solutions[primary_language] = ReferenceSolutionArtifact(
                language=primary_language,
                source_code=reference_solution,
                validation_status=ValidationStatus(report.status),
                time_complexity=draft.time_complexity,
                space_complexity=draft.space_complexity,
            )
        payload.update(
            {
                "sample_test_cases": sample_tests,
                "hidden_test_cases": hidden_tests,
                "reference_solution": reference_solution,
                "reference_solutions": reference_solutions,
                "topics": [],
                "tags": tags,
                "category": normalize_question_category(draft.category, tags),
                "validation_report": report,
                "validation_status": report.status,
                "validation_updated_at": datetime.now(UTC),
                "creation_mode": QuestionCreationMode.AI_ASSISTED,
            }
        )
        return QuestionCreateRequest.model_validate(payload)

    def generate_events(
        self,
        recruiter_uid: str,
        request: QuestionAIDraftRequest,
        existing_questions: list[QuestionRecord],
    ) -> Iterator[dict[str, Any]]:
        """Run generation and yield graph-movement progress events (SSE).

        This is PATH 3 (streaming). We do NOT call `self._graph.invoke` here,
        because LangGraph's invoke is blocking and we want to push live UI
        updates. So we replicate the graph traversal by hand:

          1. Decide the node sequence (full order, or the scoped subset).
          2. For each node, yield an "edge" event (moving A -> B), a
             "node_start" event, run the node, merge its patch into `result`,
             then yield "node_complete".
          3. Execution-heavy nodes (validation / multi-language) additionally
             stream per-test-case events via `_run_node_with_test_events`.

        The yielded dicts become Server-Sent Events the frontend renders as a
        live progress graph.
        """

        try:
            self._current_recruiter_uid = recruiter_uid
            self._current_workflow_mode = (
                "publish_review"
                if request.generation_scope == "full"
                else "interactive"
            )
            state = self._build_initial_state(request, existing_questions)
            run_inputs = self._langsmith_run_inputs(request, state)
            run_tags = self._langsmith_tags(request)
            run_metadata = self._langsmith_metadata(recruiter_uid, request)
            # Full run walks every node; a scoped run always starts with the
            # orchestrator and then only the nodes registered for that scope.
            node_sequence = (
                FULL_NODE_SEQUENCE
                if request.generation_scope == "full"
                else [
                    "orchestrator",
                    *SCOPE_NODE_SEQUENCE.get(request.generation_scope, []),
                ]
            )
            # `result` is the running state; each node's patch is merged into it.
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
            with langsmith_run(
                self._settings,
                self._langsmith_run_name(request, streamed=True),
                inputs=run_inputs,
                tags=run_tags,
                metadata=run_metadata,
            ) as parent_run:
                # Manual traversal of the (virtual) graph, one node at a time.
                for index, node_name in enumerate(node_sequence, start=1):
                    previous_node = node_sequence[index - 2] if index > 1 else "START"
                    # "edge" event = we are transitioning previous_node -> node_name.
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
                    if node_name in {"validation", "multi_language_solutions"}:
                        # These nodes execute code against many tests; stream a
                        # sub-event per test so the UI shows granular progress.
                        patch = yield from self._run_node_with_test_events(
                            node_name,
                            result,
                            parent_run,
                            scope=request.generation_scope,
                            start_progress=round(((index - 1) / total) * 100),
                            end_progress=round((index / total) * 100),
                        )
                    else:
                        # Ordinary node: run it and get back its state patch.
                        patch = self._run_traced_node(node_name, result, parent_run)
                    # Merge the patch into the running state (this is exactly what
                    # LangGraph does for us automatically on the "full" path).
                    result = self._merge_state(result, patch)
                    yield {
                        "type": "node_complete",
                        "scope": request.generation_scope,
                        "message": (
                            f"{NODE_LABELS.get(node_name, node_name)} complete."
                        ),
                        "current_node": node_name,
                        "next_node": node_sequence[index] if index < total else "END",
                        "progress": round((index / total) * 100),
                    }

                result["summary"] = SCOPE_SUMMARIES.get(
                    request.generation_scope,
                    "Generated content from your description.",
                )
                result = self._normalize_final_test_counts(result, request)
                if parent_run is not None:
                    parent_run.end(
                        outputs=self._langsmith_result_outputs(result, request),
                    )
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

    def _run_node_with_test_events(
        self,
        node_name: str,
        state: QuestionGenerationState,
        parent_run: RunTree | None,
        *,
        scope: str,
        start_progress: int,
        end_progress: int,
    ) -> Generator[dict[str, Any], None, QuestionGenerationState]:
        """Run an execution-capable node while SSE publishes each test result.

        The node itself is blocking, so we run it on a background thread and use
        a queue as a bridge: the node pushes per-test "event"s onto the queue
        (via the `validation_progress_events` context manager), and this
        generator drains the queue, `yield`ing each event to the SSE stream
        until the thread reports its final "result" (the node's state patch).
        """

        event_queue: Queue[tuple[str, Any]] = Queue()

        def run_node() -> None:
            try:
                with validation_progress_events(
                    lambda event: event_queue.put(("event", event)),
                ):
                    patch = self._run_traced_node(node_name, state, parent_run)
                event_queue.put(("result", patch))
            except BaseException as exc:
                event_queue.put(("error", exc))

        worker = Thread(
            target=run_node,
            name=f"question-{node_name}-progress",
            daemon=True,
        )
        worker.start()
        event_number = 0
        span = max(end_progress - start_progress, 1)

        while True:
            event_type, payload = event_queue.get()
            if event_type == "event":
                event_number += 1
                fraction = min(0.92, event_number / (event_number + 4))
                progress = min(
                    max(start_progress, end_progress - 1),
                    round(start_progress + (span * fraction)),
                )
                yield {
                    **cast(dict[str, Any], payload),
                    "scope": scope,
                    "current_node": node_name,
                    "next_node": None,
                    "progress": progress,
                }
                continue
            worker.join(timeout=0.1)
            if event_type == "error":
                raise cast(BaseException, payload)
            return cast(QuestionGenerationState, payload)

    def _build_initial_state(
        self,
        request: QuestionAIDraftRequest,
        existing_questions: list[QuestionRecord],
    ) -> QuestionGenerationState:
        """Normalize request context into the initial LangGraph state dict.

        This produces the "seed" `QuestionGenerationState` that enters the graph
        at the orchestrator node. It copies request settings (language, limits,
        counts) into the state, and — crucially for scoped regeneration — if the
        recruiter already has a partial draft (`request.current_draft`), it
        pre-fills the state with that existing content so a node can refine
        instead of starting from scratch.
        """

        current_draft = request.current_draft
        title_hint = (
            request.title_hint.strip()
            if request.title_hint
            else (current_draft.title.strip() if current_draft else "")
        )
        focus_tags = normalize_question_tags(
            request.focus_tags
            or ([*current_draft.tags, *current_draft.topics] if current_draft else []),
            limit=6,
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
            "target_language": (request.target_language or "").strip(),
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
            "answer_validation_mode": AnswerValidationMode.EXACT.value,
            "output_checker": "",
            "output_checker_explanation": default_checker_explanation(
                AnswerValidationMode.EXACT,
            ),
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
            answer_mode = normalize_answer_validation_mode(
                current_draft.answer_validation_mode,
            )
            state["answer_validation_mode"] = answer_mode
            state["output_checker"] = current_draft.output_checker.strip()
            state["output_checker_explanation"] = (
                current_draft.output_checker_explanation.strip()
                or default_checker_explanation(answer_mode)
            )
            current_tags = normalize_question_tags(
                [*current_draft.tags, *current_draft.topics],
                limit=6,
            )
            state["topics"] = []
            state["tags"] = current_tags
            state["category"] = normalize_question_category(
                current_draft.category,
                current_tags,
            )
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
        """Run only the nodes needed for one builder section (non-streaming).

        This is the manual mini-graph for PATH 2. It always runs the
        orchestrator first, then each node listed for this scope in
        `SCOPE_NODE_SEQUENCE`, merging every patch into `result` just like
        LangGraph would. Example: scope "tests" runs
        orchestrator -> examples -> hidden_tests -> constraint_script.
        """

        result = self._merge_state(
            state,
            self._run_traced_node("orchestrator", state),
        )
        for node_name in SCOPE_NODE_SEQUENCE.get(scope, []):
            result = self._merge_state(
                result,
                self._run_traced_node(node_name, result),
            )

        result["summary"] = SCOPE_SUMMARIES.get(
            scope,
            "Generated content from your description.",
        )
        return result

    def _node_runner(
        self,
        node_name: str,
    ) -> Callable[[QuestionGenerationState], QuestionGenerationState]:
        # Maps a node's string name to its actual method (all inherited from the
        # node mixins). This dispatch table is what lets the scoped/streaming
        # drivers run nodes by name without going through the compiled graph.
        node_runners = {
            "orchestrator": self._orchestrator_node,
            "problem_statement": self._problem_statement_node,
            "metadata": self._metadata_node,
            "constraints": self._constraint_node,
            "examples": self._example_node,
            "hidden_tests": self._hidden_test_node,
            "constraint_script": self._constraint_script_node,
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
        self._assert_final_test_counts(result, request)
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
        """Deterministically enforce final testcase counts for testcase scopes."""

        normalized = cast(QuestionGenerationState, dict(result))
        if not self._scope_returns_test_cases(request.generation_scope):
            return normalized

        settings = request.generation_settings
        target_sample_count = max(1, settings.sample_test_case_count)
        target_hidden_count = max(1, settings.hidden_test_case_count)
        require_sample, require_hidden = self._test_count_requirements(
            request.generation_scope,
        )
        sample_cases = self._dedupe_test_cases_by_input(
            [
                case.model_copy(update={"is_sample": True})
                for case in self._complete_test_cases(
                    normalized.get("sample_test_cases", []),
                )
            ],
        )
        hidden_cases = self._dedupe_test_cases_by_input(
            [
                case.model_copy(update={"is_sample": False})
                for case in self._complete_test_cases(
                    normalized.get("hidden_test_cases", []),
                )
            ],
        )
        current_draft = request.current_draft
        if current_draft is not None and "constraint_validation_script" not in result:
            sample_cases = self._dedupe_test_cases_by_input(
                self._merge_unique_test_cases(
                    sample_cases,
                    [
                        case.model_copy(update={"is_sample": True})
                        for case in self._complete_test_cases(
                            current_draft.sample_test_cases,
                        )
                    ],
                ),
            )
            hidden_cases = self._dedupe_test_cases_by_input(
                self._merge_unique_test_cases(
                    hidden_cases,
                    [
                        case.model_copy(update={"is_sample": False})
                        for case in self._complete_test_cases(
                            current_draft.hidden_test_cases,
                        )
                    ],
                ),
            )

        notes: list[str] = list(normalized.get("notes", []))
        sample_cases, hidden_cases, repair_notes = self._repair_final_test_counts(
            result=normalized,
            settings=settings,
            sample_cases=sample_cases,
            hidden_cases=hidden_cases,
            require_sample=require_sample,
            require_hidden=require_hidden,
            target_sample_count=target_sample_count,
            target_hidden_count=target_hidden_count,
        )
        notes.extend(repair_notes)

        if require_sample:
            sample_cases = sample_cases[:target_sample_count]
        if require_hidden:
            hidden_cases = hidden_cases[:target_hidden_count]

        normalized["sample_test_cases"] = sample_cases
        normalized["hidden_test_cases"] = hidden_cases
        normalized["notes"] = notes
        normalized_state = normalized
        self._assert_final_test_counts(normalized_state, request)

        notes = list(normalized_state.get("notes", []))
        notes.append(
            self._final_count_note(
                sample_cases=sample_cases,
                hidden_cases=hidden_cases,
                require_sample=require_sample,
                require_hidden=require_hidden,
                target_sample_count=target_sample_count,
                target_hidden_count=target_hidden_count,
            ),
        )
        normalized_state["notes"] = notes
        return normalized_state

    @staticmethod
    def _scope_returns_test_cases(scope: str) -> bool:
        return scope in {
            "full",
            "examples",
            "tests",
            "tests_solution",
            "solution",
        }

    @staticmethod
    def _test_count_requirements(scope: str) -> tuple[bool, bool]:
        if scope == "examples":
            return True, False
        if scope in {"full", "tests", "tests_solution"}:
            return True, True
        return False, False

    @staticmethod
    def _dedupe_test_cases_by_input(test_cases: list[TestCase]) -> list[TestCase]:
        unique_cases: list[TestCase] = []
        seen_inputs: set[str] = set()
        for test_case in test_cases:
            normalized_input = test_case.input.strip()
            if not normalized_input or normalized_input in seen_inputs:
                continue
            unique_cases.append(test_case)
            seen_inputs.add(normalized_input)
        return unique_cases

    def _repair_final_test_counts(
        self,
        *,
        result: QuestionGenerationState,
        settings: QuestionGenerationSettings,
        sample_cases: list[TestCase],
        hidden_cases: list[TestCase],
        require_sample: bool,
        require_hidden: bool,
        target_sample_count: int,
        target_hidden_count: int,
    ) -> tuple[list[TestCase], list[TestCase], list[str]]:
        """Generate missing final rows with bounded attempts before hard failure."""

        notes: list[str] = []
        for attempt in range(1, FINAL_TEST_COUNT_REPAIR_ROUNDS + 1):
            sample_missing = require_sample and len(sample_cases) < target_sample_count
            hidden_missing = require_hidden and len(hidden_cases) < target_hidden_count
            if not sample_missing and not hidden_missing:
                break

            working_state = cast(
                QuestionGenerationState,
                {
                    **result,
                    "generation_settings": settings,
                    "sample_test_cases": sample_cases,
                    "hidden_test_cases": hidden_cases,
                },
            )
            if sample_missing:
                generated = self._example_node(working_state)
                sample_cases = self._dedupe_test_cases_by_input(
                    self._merge_unique_test_cases(
                        sample_cases,
                        [
                            case.model_copy(update={"is_sample": True})
                            for case in self._complete_test_cases(
                                generated.get("sample_test_cases", []),
                            )
                        ],
                    ),
                )
                notes.append(
                    (
                        f"Final testcase guardrail repair {attempt}: "
                        f"{len(sample_cases)}/{target_sample_count} sample cases."
                    ),
                )

            if hidden_missing:
                working_state = cast(
                    QuestionGenerationState,
                    {
                        **working_state,
                        "sample_test_cases": sample_cases,
                        "hidden_test_cases": hidden_cases,
                    },
                )
                generated = self._hidden_test_node(working_state)
                hidden_cases = self._dedupe_test_cases_by_input(
                    self._merge_unique_test_cases(
                        hidden_cases,
                        [
                            case.model_copy(update={"is_sample": False})
                            for case in self._complete_test_cases(
                                generated.get("hidden_test_cases", []),
                            )
                        ],
                    ),
                )
                notes.append(
                    (
                        f"Final testcase guardrail repair {attempt}: "
                        f"{len(hidden_cases)}/{target_hidden_count} hidden cases."
                    ),
                )

            checked = self._constraint_script_node(
                cast(
                    QuestionGenerationState,
                    {
                        **working_state,
                        "sample_test_cases": sample_cases,
                        "hidden_test_cases": hidden_cases,
                    },
                ),
            )
            sample_cases = self._dedupe_test_cases_by_input(
                [
                    case.model_copy(update={"is_sample": True})
                    for case in self._complete_test_cases(
                        checked.get("sample_test_cases", sample_cases),
                    )
                ],
            )
            hidden_cases = self._dedupe_test_cases_by_input(
                [
                    case.model_copy(update={"is_sample": False})
                    for case in self._complete_test_cases(
                        checked.get("hidden_test_cases", hidden_cases),
                    )
                ],
            )
            notes.extend(checked.get("constraint_validation_warnings", []))

        return sample_cases, hidden_cases, notes

    def _assert_final_test_counts(
        self,
        result: QuestionGenerationState,
        request: QuestionAIDraftRequest,
    ) -> None:
        """Hard guardrail: never return a testcase response with wrong counts."""

        require_sample, require_hidden = self._test_count_requirements(
            request.generation_scope,
        )
        if not require_sample and not require_hidden:
            return

        settings = request.generation_settings
        target_sample_count = max(1, settings.sample_test_case_count)
        target_hidden_count = max(1, settings.hidden_test_case_count)
        sample_count = len(
            self._complete_test_cases(result.get("sample_test_cases", [])),
        )
        hidden_count = len(
            self._complete_test_cases(result.get("hidden_test_cases", [])),
        )
        sample_ok = not require_sample or sample_count == target_sample_count
        hidden_ok = not require_hidden or hidden_count == target_hidden_count
        if sample_ok and hidden_ok:
            return

        expected_parts: list[str] = []
        actual_parts: list[str] = []
        if require_sample:
            expected_parts.append(f"{target_sample_count} sample")
            actual_parts.append(f"{sample_count} sample")
        if require_hidden:
            expected_parts.append(f"{target_hidden_count} hidden")
            actual_parts.append(f"{hidden_count} hidden")
        raise ValueError(
            (
                "Question generation guardrail failed: expected exactly "
                f"{' and '.join(expected_parts)} testcase"
                f"{'s' if len(expected_parts) > 1 else ''}, but prepared "
                f"{' and '.join(actual_parts)}."
            ),
        )

    @staticmethod
    def _final_count_note(
        *,
        sample_cases: list[TestCase],
        hidden_cases: list[TestCase],
        require_sample: bool,
        require_hidden: bool,
        target_sample_count: int,
        target_hidden_count: int,
    ) -> str:
        if require_sample and require_hidden:
            return (
                "Exact testcase count verified: "
                f"{target_sample_count} sample and {target_hidden_count} hidden."
            )
        if require_sample:
            return (
                f"Exact sample testcase count verified: {target_sample_count} sample."
            )
        if require_hidden:
            return (
                f"Exact hidden testcase count verified: {target_hidden_count} hidden."
            )
        return (
            "Testcase count carried through without generation: "
            f"{len(sample_cases)} sample and {len(hidden_cases)} hidden."
        )

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
        reference_language = self._normalize_solution_language(
            request.reference_language.strip() or result.get("reference_language", "")
        )
        supported_languages = self._normalize_languages(
            result.get("supported_languages") or settings.supported_languages,
            reference_language,
            settings.supported_languages,
        )
        reference_solutions = self._prune_reference_solutions(
            result.get("reference_solutions", {}),
            supported_languages,
            reference_language,
        )
        tags = normalize_question_tags(
            [*result.get("tags", []), *result.get("topics", [])],
            limit=6,
        )
        answer_mode = AnswerValidationMode(
            normalize_answer_validation_mode(
                result.get("answer_validation_mode", AnswerValidationMode.EXACT.value),
            ),
        )
        checker_explanation = result.get(
            "output_checker_explanation", ""
        ).strip() or default_checker_explanation(answer_mode)
        return QuestionCreateRequest(
            title=result.get("title") or request.title_hint or "Untitled Question",
            problem_statement=result.get("problem_statement", ""),
            difficulty=DifficultyLevel(difficulty_value),
            topics=[],
            tags=tags,
            category=normalize_question_category(result.get("category", ""), tags),
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
            reference_language=reference_language,
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
            reference_solutions=reference_solutions,
            answer_validation_mode=answer_mode,
            output_checker=result.get("output_checker", "").strip(),
            output_checker_explanation=checker_explanation,
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

    @staticmethod
    def _prune_reference_solutions(
        reference_solutions: dict[str, ReferenceSolutionArtifact],
        supported_languages: list[str],
        reference_language: str,
    ) -> dict[str, ReferenceSolutionArtifact]:
        allowed_languages = {
            QuestionGenerationWorkflow._normalize_solution_language(language)
            for language in supported_languages
        }
        allowed_languages.add(
            QuestionGenerationWorkflow._normalize_solution_language(reference_language),
        )
        pruned: dict[str, ReferenceSolutionArtifact] = {}
        for language, artifact in reference_solutions.items():
            normalizer = QuestionGenerationWorkflow._normalize_solution_language
            normalized_language = normalizer(
                language or artifact.language,
            )
            if normalized_language not in allowed_languages:
                continue
            pruned[normalized_language] = artifact.model_copy(
                update={"language": normalized_language},
            )
        return pruned

    def _run_traced_node(
        self,
        node_name: str,
        state: QuestionGenerationState,
        parent_run: RunTree | None = None,
    ) -> QuestionGenerationState:
        """Run one node by name, wrapped in a LangSmith child span for tracing.

        Used by the scoped and streaming drivers. It looks the node up in the
        `_node_runner` table, calls it with the current state, and returns the
        node's patch. The LangSmith span makes each node show up as a nested
        step in the trace UI.
        """

        node_label = NODE_LABELS.get(node_name, node_name.replace("_", " ").title())
        with langsmith_run(
            self._settings,
            f"Question Agent Node: {node_label}",
            inputs=self._langsmith_node_inputs(node_name, state),
            tags=[
                *self._langsmith_base_tags(state.get("generation_scope", "unknown")),
                f"node:{node_name}",
            ],
            metadata={
                "node_name": node_name,
                "node_label": node_label,
                "workflow_mode": self._current_workflow_mode,
            },
            parent=parent_run,
        ) as run:
            patch = self._node_runner(node_name)(state)
            if run is not None:
                run.end(outputs=self._langsmith_patch_outputs(patch))
            return patch

    def _langsmith_run_name(
        self,
        request: QuestionAIDraftRequest,
        *,
        streamed: bool = False,
    ) -> str:
        scope = request.generation_scope.replace("_", " ").title()
        suffix = " Stream" if streamed else ""
        return f"CAP Question Generation: {scope}{suffix}"

    def _langsmith_graph_config(
        self,
        recruiter_uid: str,
        request: QuestionAIDraftRequest,
    ) -> dict[str, Any]:
        return {
            "run_name": "CAP Question Generation Graph",
            "tags": self._langsmith_tags(request),
            "metadata": self._langsmith_metadata(recruiter_uid, request),
        }

    def _langsmith_tags(self, request: QuestionAIDraftRequest) -> list[str]:
        return self._langsmith_base_tags(request.generation_scope)

    def _langsmith_base_tags(self, scope: str) -> list[str]:
        return [
            "cap",
            "question-generation",
            f"scope:{scope}",
            f"mode:{self._current_workflow_mode}",
        ]

    def _langsmith_metadata(
        self,
        recruiter_uid: str,
        request: QuestionAIDraftRequest,
    ) -> dict[str, Any]:
        settings = request.generation_settings
        return {
            "recruiter_uid": recruiter_uid,
            "generation_scope": request.generation_scope,
            "workflow_mode": self._current_workflow_mode,
            "reference_language": request.reference_language,
            "target_language": request.target_language or "",
            "supported_languages": settings.supported_languages,
            "sample_test_case_count": settings.sample_test_case_count,
            "hidden_test_case_count": settings.hidden_test_case_count,
            "model_sequence": self._settings.ai_model_sequence_label,
        }

    @staticmethod
    def _langsmith_run_inputs(
        request: QuestionAIDraftRequest,
        state: QuestionGenerationState,
    ) -> dict[str, Any]:
        settings = request.generation_settings
        return {
            "generation_scope": request.generation_scope,
            "reference_language": state.get("reference_language", ""),
            "target_language": state.get("target_language", ""),
            "title_hint": state.get("title_hint", ""),
            "focus_tags": state.get("focus_tags", []),
            "prompt_length": len(request.prompt),
            "has_current_draft": request.current_draft is not None,
            "requested_question_count": settings.question_count,
            "requested_sample_tests": settings.sample_test_case_count,
            "requested_hidden_tests": settings.hidden_test_case_count,
        }

    @staticmethod
    def _langsmith_node_inputs(
        node_name: str,
        state: QuestionGenerationState,
    ) -> dict[str, Any]:
        return {
            "node_name": node_name,
            "generation_scope": state.get("generation_scope", ""),
            "state_keys": sorted(state.keys()),
            "sample_test_case_count": len(state.get("sample_test_cases", [])),
            "hidden_test_case_count": len(state.get("hidden_test_cases", [])),
            "has_problem_statement": bool(state.get("problem_statement", "").strip()),
            "has_reference_solution": bool(state.get("reference_solution", "").strip()),
            "reference_solution_languages": sorted(
                state.get("reference_solutions", {}).keys(),
            ),
        }

    @staticmethod
    def _langsmith_patch_outputs(patch: QuestionGenerationState) -> dict[str, Any]:
        return {
            "updated_keys": sorted(patch.keys()),
            "sample_test_case_count": len(patch.get("sample_test_cases", [])),
            "hidden_test_case_count": len(patch.get("hidden_test_cases", [])),
            "has_reference_solution": bool(patch.get("reference_solution", "").strip()),
            "validation_status": patch.get("validation_status", ""),
            "reference_solution_languages": sorted(
                patch.get("reference_solutions", {}).keys(),
            ),
        }

    @staticmethod
    def _langsmith_result_outputs(
        result: QuestionGenerationState,
        request: QuestionAIDraftRequest,
    ) -> dict[str, Any]:
        return {
            "generation_scope": request.generation_scope,
            "title": result.get("title", ""),
            "summary": result.get("summary", ""),
            "validation_status": result.get("validation_status", ""),
            "sample_test_case_count": len(result.get("sample_test_cases", [])),
            "hidden_test_case_count": len(result.get("hidden_test_cases", [])),
            "reference_solution_languages": sorted(
                result.get("reference_solutions", {}).keys(),
            ),
        }

    def _build_graph(self) -> StateGraph[QuestionGenerationState]:
        """Wire the LangGraph: declare the nodes, then connect them with edges.

        This is the heart of the LangGraph. Two steps:

          STEP A — register nodes: `add_node(name, fn)` tells LangGraph "when we
          reach the node called <name>, call this function with the state". The
          functions here are the node methods inherited from the mixins.

          STEP B — connect edges: `add_edge(a, b)` means "after node `a`
          finishes, go to node `b`". Because every edge is unconditional, this
          graph is a straight line (no branches/loops). `START -> orchestrator`
          sets the entry point; `quality_review -> END` marks the exit.

        The compiled version of this graph is what `generate()` runs for the
        "full" scope. (Registration order does not matter; only the edges
        define the execution order.)
        """

        # `StateGraph(QuestionGenerationState)` tells LangGraph the shape of the
        # shared state every node reads from and writes patches to.
        graph: StateGraph[QuestionGenerationState] = StateGraph(QuestionGenerationState)

        # STEP A: register each node function under a string name.
        graph.add_node("orchestrator", self._orchestrator_node)
        graph.add_node("problem_statement", self._problem_statement_node)
        graph.add_node("metadata", self._metadata_node)
        graph.add_node("constraints", self._constraint_node)
        graph.add_node("examples", self._example_node)
        graph.add_node("hidden_tests", self._hidden_test_node)
        graph.add_node("constraint_script", self._constraint_script_node)
        graph.add_node("solution", self._solution_node)
        graph.add_node("validation", self._validation_node)
        graph.add_node("multi_language_solutions", self._multi_language_solution_node)
        graph.add_node("duplicate_detection", self._duplicate_detection_node)
        graph.add_node("quality_review", self._quality_review_node)

        # STEP B: connect the nodes into a single linear pipeline.
        graph.add_edge(START, "orchestrator")  # entry point
        graph.add_edge("orchestrator", "problem_statement")
        graph.add_edge("problem_statement", "constraints")
        graph.add_edge("constraints", "examples")
        graph.add_edge("examples", "hidden_tests")
        graph.add_edge("hidden_tests", "constraint_script")
        graph.add_edge("constraint_script", "solution")
        graph.add_edge("solution", "validation")
        graph.add_edge("validation", "multi_language_solutions")
        graph.add_edge("multi_language_solutions", "metadata")
        graph.add_edge("metadata", "duplicate_detection")
        graph.add_edge("duplicate_detection", "quality_review")
        graph.add_edge("quality_review", END)  # exit point
        return graph


__all__ = ["QuestionGenerationWorkflow"]
