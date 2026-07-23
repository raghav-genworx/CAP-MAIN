"""Question output validation modes and sandboxed checker support."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from typing import Any

from schemas.assessments import ExecutionCaseResult
from schemas.question_bank import AnswerValidationMode

CHECKER_TIMEOUT_SECONDS = 2.0

_NON_OUTPUT_FAILURE_MARKERS = (
    "compile",
    "runtime",
    "time limit",
    "memory",
    "internal",
    "execution_failed",
)

_ALLOWED_TOP_LEVEL_NODES = (ast.FunctionDef, ast.Expr)
_ALLOWED_EXPR_NODES = (
    ast.Module,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Return,
    ast.Assign,
    ast.AnnAssign,
    ast.AugAssign,
    ast.Expr,
    ast.If,
    ast.For,
    ast.While,
    ast.Break,
    ast.Continue,
    ast.Pass,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Call,
    ast.keyword,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Dict,
    ast.Subscript,
    ast.Slice,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.comprehension,
    ast.IfExp,
    ast.Attribute,
    ast.JoinedStr,
    ast.FormattedValue,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)
_ALLOWED_CALLS = frozenset(
    {
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "float",
        "int",
        "len",
        "list",
        "map",
        "max",
        "min",
        "range",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    }
)
_ALLOWED_METHODS = frozenset(
    {
        "append",
        "count",
        "endswith",
        "get",
        "isdigit",
        "islower",
        "isupper",
        "items",
        "join",
        "keys",
        "lower",
        "lstrip",
        "replace",
        "rstrip",
        "sort",
        "split",
        "splitlines",
        "startswith",
        "strip",
        "upper",
        "values",
    }
)
_FORBIDDEN_NAMES = frozenset(
    {
        "__builtins__",
        "__import__",
        "breakpoint",
        "compile",
        "eval",
        "exec",
        "globals",
        "help",
        "input",
        "locals",
        "open",
        "print",
        "quit",
        "vars",
    }
)


def normalize_answer_validation_mode(value: str | AnswerValidationMode) -> str:
    """Return a supported output-validation mode string."""

    raw_value = value.value if isinstance(value, AnswerValidationMode) else value
    normalized = str(raw_value or "").strip().lower()
    try:
        return AnswerValidationMode(normalized).value
    except ValueError:
        return AnswerValidationMode.EXACT.value


def default_checker_explanation(mode: str | AnswerValidationMode) -> str:
    """Return recruiter-facing default copy for a validation mode."""

    normalized = normalize_answer_validation_mode(mode)
    if normalized == AnswerValidationMode.UNORDERED.value:
        return (
            "Candidate output is accepted when it contains the same whitespace-"
            "separated tokens as the expected output, regardless of order."
        )
    if normalized == AnswerValidationMode.FLOATING.value:
        return (
            "Candidate output is accepted when each numeric value matches the "
            "expected output within a small floating-point tolerance."
        )
    if normalized == AnswerValidationMode.MULTIPLE_VALID.value:
        return (
            "Candidate output is accepted by a custom checker because more than "
            "one output can satisfy the same testcase input."
        )
    if normalized == AnswerValidationMode.CONSTRUCTIVE.value:
        return (
            "Candidate output is accepted by a custom checker that validates the "
            "constructed answer against the problem rules."
        )
    return (
        "Candidate output must match the expected output exactly after safe "
        "whitespace normalization."
    )


def validate_output_checker_source(source: str) -> str:
    """Return a validation error for unsafe or invalid checker source."""

    stripped = source.strip()
    if not stripped:
        return ""
    try:
        tree = ast.parse(stripped)
    except SyntaxError as exc:
        return f"Output checker has invalid Python syntax: {exc.msg}."

    function_names = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    if "check_output" not in function_names:
        return (
            "Output checker must define check_output(stdin, expected_output, "
            "actual_output)."
        )

    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node, _ALLOWED_TOP_LEVEL_NODES):
            return "Output checker may only define functions and an optional docstring."

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_EXPR_NODES):
            return (
                "Output checker contains unsupported Python syntax: "
                f"{type(node).__name__}."
            )
        if isinstance(node, ast.FunctionDef) and node.name.startswith("__"):
            return "Output checker uses a forbidden function name."
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            return f"Output checker uses a forbidden name: {node.id}."
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("__") or node.attr not in _ALLOWED_METHODS
        ):
            return f"Output checker uses an unsupported attribute: {node.attr}."
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if (
                    node.func.id not in _ALLOWED_CALLS
                    and node.func.id not in function_names
                ):
                    return f"Output checker calls unsupported function: {node.func.id}."
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr not in _ALLOWED_METHODS:
                    return f"Output checker calls unsupported method: {node.func.attr}."
            else:
                return "Output checker has an unsafe call."
    return ""


def apply_answer_validation(
    result: ExecutionCaseResult,
    *,
    mode: str | AnswerValidationMode,
    checker_source: str = "",
) -> ExecutionCaseResult:
    """Re-score a case result using the configured question answer checker."""

    normalized_mode = normalize_answer_validation_mode(mode)
    if normalized_mode == AnswerValidationMode.EXACT.value:
        return result
    if _looks_like_non_output_failure(result):
        return result.model_copy(
            update={"checker_message": "Checker skipped because execution failed."}
        )

    if normalized_mode == AnswerValidationMode.UNORDERED.value:
        passed = _tokens(result.actual_output) == _tokens(result.expected_output)
        return _with_checker_result(
            result,
            passed=passed,
            message=(
                "Accepted by unordered-token checker."
                if passed
                else "Rejected by unordered-token checker."
            ),
        )

    if normalized_mode == AnswerValidationMode.FLOATING.value:
        passed = _floating_outputs_match(result.actual_output, result.expected_output)
        return _with_checker_result(
            result,
            passed=passed,
            message=(
                "Accepted by floating-point tolerance checker."
                if passed
                else "Rejected by floating-point tolerance checker."
            ),
        )

    if not checker_source.strip():
        return _with_checker_result(
            result,
            passed=False,
            message=(
                "No custom output checker is configured for this multi-answer "
                "validation mode."
            ),
        )

    checker_error = validate_output_checker_source(checker_source)
    if checker_error:
        return _with_checker_result(result, passed=False, message=checker_error)

    passed, message = _run_checker_subprocess(
        checker_source,
        stdin=result.input,
        expected_output=result.expected_output,
        actual_output=result.actual_output,
    )
    return _with_checker_result(
        result,
        passed=passed,
        message=message
        or (
            "Accepted by custom output checker."
            if passed
            else "Rejected by custom output checker."
        ),
    )


def _looks_like_non_output_failure(result: ExecutionCaseResult) -> bool:
    diagnostic = " ".join(
        [result.status, result.stderr, result.compile_output, result.message]
    ).lower()
    return any(marker in diagnostic for marker in _NON_OUTPUT_FAILURE_MARKERS)


def _tokens(value: str) -> list[str]:
    return sorted(value.split())


def _floating_outputs_match(actual_output: str, expected_output: str) -> bool:
    try:
        actual = [float(item) for item in actual_output.split()]
        expected = [float(item) for item in expected_output.split()]
    except ValueError:
        return False
    if len(actual) != len(expected):
        return False
    for left, right in zip(actual, expected, strict=True):
        tolerance = max(1e-6, abs(right) * 1e-6)
        if abs(left - right) > tolerance:
            return False
    return True


def _with_checker_result(
    result: ExecutionCaseResult,
    *,
    passed: bool,
    message: str,
) -> ExecutionCaseResult:
    return result.model_copy(
        update={
            "passed": passed,
            "status": "Accepted by checker" if passed else "Wrong Answer",
            "checker_message": message,
            "message": result.message or message,
        }
    )


def _run_checker_subprocess(
    checker_source: str,
    *,
    stdin: str,
    expected_output: str,
    actual_output: str,
) -> tuple[bool, str]:
    wrapper = """
import json
import sys

payload = json.loads(sys.stdin.read())
safe_builtins = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}
namespace = {"__builtins__": safe_builtins}
exec(payload["source"], namespace, namespace)
result = namespace["check_output"](
    payload["stdin"],
    payload["expected_output"],
    payload["actual_output"],
)
if isinstance(result, (list, tuple)):
    passed = bool(result[0]) if result else False
    message = str(result[1]) if len(result) > 1 else ""
else:
    passed = bool(result)
    message = ""
print(json.dumps({"passed": passed, "message": message}))
"""
    payload: dict[str, Any] = {
        "source": checker_source,
        "stdin": stdin,
        "expected_output": expected_output,
        "actual_output": actual_output,
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", wrapper],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=CHECKER_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "Output checker timed out."
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout).strip()
        return False, diagnostic[:300] or "Output checker failed."
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return False, "Output checker returned invalid data."
    return bool(result.get("passed")), str(result.get("message") or "")
