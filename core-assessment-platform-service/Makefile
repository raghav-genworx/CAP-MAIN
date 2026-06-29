.PHONY: install run migrate migration-check format lint typecheck pre-commit

install:
	uv sync

run:
	uv run uvicorn main:app --app-dir src --reload

migrate:
	uv run alembic -c alembic.ini upgrade head

migration-check:
	uv run alembic -c alembic.ini check

format:
	uv run ruff format .

lint:
	uv run ruff check . --fix

typecheck:
	uv run mypy src

pre-commit:
	uv run pre-commit run --all-files
