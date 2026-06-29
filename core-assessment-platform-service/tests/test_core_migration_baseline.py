"""Contract tests for safe adoption of the pre-Alembic core schema."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260627_0001_create_core_platform_tables.py"
)


class _Inspector:
    def __init__(self, table_names: set[str]) -> None:
        self._table_names = table_names

    def get_table_names(self) -> list[str]:
        return sorted(self._table_names)


def _load_migration() -> ModuleType:
    spec = spec_from_file_location("core_baseline_migration", MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load core baseline migration")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("table_names", "expected"),
    [
        (set(), False),
        (
            {
                "ai_run_logs",
                "assessment_questions",
                "assessment_slots",
                "assessment_templates",
                "candidate_assessments",
                "candidates",
                "question_bank_questions",
                "question_groups",
                "submissions",
                "user_roles",
            },
            True,
        ),
    ],
)
def test_baseline_adopts_only_empty_or_complete_schema(
    monkeypatch: pytest.MonkeyPatch,
    table_names: set[str],
    expected: bool,
) -> None:
    migration = _load_migration()
    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: _Inspector(table_names))

    assert migration._adopt_complete_legacy_schema() is expected


def test_baseline_rejects_partial_legacy_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(
        migration.sa,
        "inspect",
        lambda _bind: _Inspector({"assessment_templates"}),
    )

    with pytest.raises(RuntimeError, match="partial legacy core schema"):
        migration._adopt_complete_legacy_schema()
