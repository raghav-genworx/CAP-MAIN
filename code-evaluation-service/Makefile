.PHONY: install run format lint typecheck migrate migration-check pre-commit

install:
	uv sync

run:
	uv run uvicorn main:app --app-dir src --reload

format:
	uv run ruff format .

lint:
	uv run ruff check . --fix

typecheck:
	uv run mypy src

migrate:
	uv run alembic -c alembic.ini upgrade head

migration-check:
	uv run alembic -c alembic.ini check

pre-commit:
	uv run pre-commit run --all-files
