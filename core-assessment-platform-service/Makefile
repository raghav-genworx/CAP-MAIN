.PHONY: install run migrate migration-check test test-unit test-integration \
	test-contract test-contract-live contract-baseline requirements format lint \
	typecheck lint-imports pre-commit

install:
	uv sync --dev

run:
	uv run uvicorn main:app --app-dir src --reload

migrate:
	uv run alembic -c alembic.ini upgrade head

migration-check:
	uv run alembic -c alembic.ini check

# Unmarked tests are pinned to an unreachable database by tests/conftest.py, so
# `make test` never touches a real deployment. Integration tests opt in explicitly
# and need CORE_TEST_DATABASE_URL.
test:
	uv run pytest -q

test-unit:
	uv run pytest -q -m unit

# Exit 5 is pytest's "no tests collected". There are no integration tests yet, so
# tolerate it rather than failing the target; any real failure still exits non-zero.
test-integration:
	uv run pytest -q -m integration || [ $$? -eq 5 ]

# In-process contract gate. The live-stack tests skip unless CAP_GATEWAY_BASE_URL is set.
test-contract:
	uv run pytest -q -m contract

# Full contract gate including the gateway hop. Needs `docker compose up -d
# --build api-gateway-service` from the repository root first.
test-contract-live:
	CAP_GATEWAY_BASE_URL=$${CAP_GATEWAY_BASE_URL:-http://localhost:8001/api/v1} \
		uv run pytest -q -m contract

# Refresh the recorded "before" snapshot each migration phase is compared against.
contract-baseline:
	CAP_GATEWAY_BASE_URL=$${CAP_GATEWAY_BASE_URL:-http://localhost:8001/api/v1} \
		CAP_WRITE_CONTRACT_BASELINE=1 uv run pytest -q -m contract

# Regenerate the COE requirements/ exports after changing dependencies.
requirements:
	uv export --no-dev --no-emit-project --no-hashes -o requirements/base.txt
	uv export --only-group dev --no-emit-project --no-hashes -o requirements/dev.txt
	uv export --only-group test --no-emit-project --no-hashes -o requirements/test.txt

format:
	uv run ruff format .

lint:
	uv run ruff check . --fix

typecheck:
	uv run mypy src

# Enforce the bounded-context boundaries that keep each context extractable.
lint-imports:
	PYTHONPATH=src uv run lint-imports

pre-commit:
	uv run pre-commit run --all-files
