FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.26 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

FROM python:3.11-slim

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/alembic /app/alembic
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

ENV APP_ENV=production \
    EVALUATION_REPORT_DIR=/app/data/reports \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

USER appuser
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
