"""Shared builders for concise, structured question-agent prompts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

from pydantic import BaseModel


def _json_value(value: Any) -> Any:
    """Convert prompt context into deterministic JSON-compatible data."""

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    return value


def build_task_system_prompt(
    *,
    role: str,
    objective: str,
    rules: Sequence[str] = (),
) -> str:
    """Build a compact system prompt with one role and one objective."""

    lines = [f"Role: {role}", f"Objective: {objective}"]
    if rules:
        lines.append("Task rules:")
        lines.extend(f"- {rule}" for rule in rules)
    return "\n".join(lines)


def build_task_user_prompt(
    *,
    task: str,
    context: Mapping[str, Any],
    requirements: Sequence[str],
) -> str:
    """Serialize untrusted task data and requirements as one JSON document."""

    payload = {
        "task": task,
        "context": _json_value(context),
        "requirements": list(requirements),
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)


def parse_recruiter_request(value: str) -> dict[str, Any]:
    """Normalize plain or frontend-structured recruiter text into JSON context."""

    stripped = value.strip()
    if not stripped:
        return {"request": "", "recruiter_instruction": None}
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return {"request": stripped, "recruiter_instruction": None}
    if isinstance(parsed, dict):
        return {str(key): _json_value(item) for key, item in parsed.items()}
    return {"request": stripped, "recruiter_instruction": None}


__all__ = [
    "build_task_system_prompt",
    "build_task_user_prompt",
    "parse_recruiter_request",
]
