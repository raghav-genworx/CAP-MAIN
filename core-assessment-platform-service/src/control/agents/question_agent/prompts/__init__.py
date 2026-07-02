"""Prompt templates and prompt-facing constants for the question agent."""

from .adversarial_test_prompt import build_adversarial_test_prompt
from .bruteforce_solution_prompt import build_bruteforce_solution_prompt
from .constraint_prompt import build_constraint_prompt
from .constraint_replacement_prompt import build_constraint_replacement_prompt
from .constraint_review_prompt import build_constraint_review_prompt
from .constraint_script_prompt import build_constraint_script_prompt
from .duplicate_detection_prompt import build_duplicate_detection_prompt
from .example_prompt import build_example_prompt
from .guardrail_prompt import build_guarded_system_prompt
from .hidden_test_prompt import build_hidden_test_prompt
from .metadata_prompt import build_metadata_prompt
from .multi_language_solution_prompt import (
    build_focused_language_solution_prompt,
    build_multi_language_solution_prompt,
)
from .problem_statement_prompt import build_problem_statement_prompt
from .prompt_contract import (
    build_task_system_prompt,
    build_task_user_prompt,
    parse_recruiter_request,
)
from .quality_review_prompt import build_quality_review_prompt
from .question_prompts import (
    ADVERSARIAL_TESTS_PER_ROUND,
    ADVERSARIAL_VALIDATION_ROUNDS,
    SCOPE_NODE_SEQUENCE,
    SCOPE_SUMMARIES,
)
from .repair_decision_prompt import build_repair_decision_prompt
from .solution_contract_prompt import (
    build_solution_contract_retry_prompt,
    solution_contract_guidance,
    strict_solution_contract_guidance,
)
from .solution_prompt import build_solution_prompt
from .solution_repair_prompt import build_solution_repair_prompt
from .testcase_repair_prompt import build_testcase_repair_prompt
from .validation_prompt import build_validation_prompt

__all__ = [
    "ADVERSARIAL_TESTS_PER_ROUND",
    "ADVERSARIAL_VALIDATION_ROUNDS",
    "SCOPE_NODE_SEQUENCE",
    "SCOPE_SUMMARIES",
    "build_adversarial_test_prompt",
    "build_bruteforce_solution_prompt",
    "build_constraint_prompt",
    "build_constraint_replacement_prompt",
    "build_constraint_review_prompt",
    "build_constraint_script_prompt",
    "build_duplicate_detection_prompt",
    "build_example_prompt",
    "build_focused_language_solution_prompt",
    "build_guarded_system_prompt",
    "build_hidden_test_prompt",
    "build_metadata_prompt",
    "build_multi_language_solution_prompt",
    "build_problem_statement_prompt",
    "build_task_system_prompt",
    "build_task_user_prompt",
    "build_quality_review_prompt",
    "build_repair_decision_prompt",
    "build_solution_contract_retry_prompt",
    "build_solution_prompt",
    "build_solution_repair_prompt",
    "build_testcase_repair_prompt",
    "build_validation_prompt",
    "solution_contract_guidance",
    "strict_solution_contract_guidance",
    "parse_recruiter_request",
]
