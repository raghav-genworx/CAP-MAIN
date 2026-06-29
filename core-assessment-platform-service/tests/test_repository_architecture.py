"""Architecture tests for the repository-pattern boundary."""

from pathlib import Path


def test_core_services_do_not_query_database_directly() -> None:
    """Core services should delegate SQLAlchemy access to data repositories."""

    services_dir = Path(__file__).resolve().parents[1] / "src" / "core" / "services"
    violations: list[str] = []

    for path in services_dir.glob("*.py"):
        source = path.read_text()
        if "self._session" in source or "select(" in source:
            violations.append(path.name)

    assert violations == []
