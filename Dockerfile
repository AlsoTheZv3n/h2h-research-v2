# syntax=docker/dockerfile:1

# ---------- builder: resolve dependencies into a venv ----------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer first: this only busts when the manifests change, so app-code
# edits reuse the resolved venv. --no-install-project keeps our own code out of it.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# App code last.
COPY backend/ ./backend/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------- runtime ----------
FROM python:3.12-slim AS runtime

# UID 1000 so bind-mounted files stay writable by the usual host user.
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --create-home appuser

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser alembic.ini ./

USER appuser

EXPOSE 8000

# urllib, not curl: slim images have no curl, and installing one just to probe is
# a package more than the runtime needs. --start-period covers boot without the
# failures during it counting toward the retry budget.
# Only compose consumes this: `restart` and `depends_on: condition: service_healthy`.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
