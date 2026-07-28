"""Canonical coding-question tag taxonomy and normalization helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_TAXONOMY_PATH = Path(__file__).with_name("question_tag_taxonomy.json")
_IDENTIFIER_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")


def _load_categories() -> dict[str, tuple[str, ...]]:
    payload: dict[str, Any] = json.loads(_TAXONOMY_PATH.read_text(encoding="utf-8"))
    categories = payload.get("categories", {})
    if not isinstance(categories, dict):
        raise ValueError("Question tag taxonomy must define a categories object.")
    return {
        str(category): tuple(str(tag) for tag in tags)
        for category, tags in categories.items()
        if isinstance(tags, list)
    }


QUESTION_TAG_CATEGORIES = _load_categories()
ALLOWED_QUESTION_TAGS = frozenset(
    tag for tags in QUESTION_TAG_CATEGORIES.values() for tag in tags
)


def normalize_question_tag(value: str) -> str:
    """Convert a human label to its canonical taxonomy identifier."""

    normalized = _IDENTIFIER_SEPARATOR_RE.sub("_", value.strip().lower()).strip("_")
    return normalized if normalized in ALLOWED_QUESTION_TAGS else ""


def normalize_question_tags(
    values: list[str],
    *,
    limit: int | None = None,
) -> list[str]:
    """Return unique taxonomy-approved tags while preserving input order."""

    tags: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = normalize_question_tag(value)
        if not tag or tag in seen:
            continue
        tags.append(tag)
        seen.add(tag)
        if limit is not None and len(tags) >= limit:
            break
    return tags


def normalize_question_category(value: str, tags: list[str]) -> str:
    """Return a taxonomy category consistent with at least one selected tag."""

    category = _IDENTIFIER_SEPARATOR_RE.sub("_", value.strip().lower()).strip("_")
    if category in QUESTION_TAG_CATEGORIES and any(
        tag in QUESTION_TAG_CATEGORIES[category] for tag in tags
    ):
        return category

    selected = set(tags)
    if not selected:
        return ""
    return max(
        QUESTION_TAG_CATEGORIES,
        key=lambda candidate: len(
            selected.intersection(QUESTION_TAG_CATEGORIES[candidate])
        ),
        default="",
    )


__all__ = [
    "ALLOWED_QUESTION_TAGS",
    "QUESTION_TAG_CATEGORIES",
    "normalize_question_category",
    "normalize_question_tag",
    "normalize_question_tags",
]
