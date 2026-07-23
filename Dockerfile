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

# RDKit's drawing module links against shared libs that python:*-slim omits, so
# `import rdMolDraw2D` dies at import with an ImportError. Only ever surfaces in the
# image: a local venv on a desktop OS already has all of these.
#   libxrender1, libxext6  X11, for the 2D drawer
#   libexpat1              XML, pulled in by the SVG writer
#   libgomp1               OpenMP, RDKit's threading runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libxrender1 libxext6 libexpat1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# UID 1000 so bind-mounted files stay writable by the usual host user.
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --create-home appuser

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Bake the embedding model into the image rather than fetching it at first use.
#
# fastembed downloads bge-small from HuggingFace the first time something calls it.
# Left alone, that turns the first question anyone asks into a ~130 MB download --
# slow, and a hard failure on any host that cannot reach huggingface.co, in a
# container that had otherwise started perfectly. `docker compose up` promises a
# working system; a working system does not depend on a CDN nobody was told about.
#
# In its OWN layer, keyed only on embeddings.py, and BEFORE the full backend COPY --
# so editing any other Python file reuses this layer instead of re-downloading the
# ~130 MB model (the inner-loop cost) or failing an offline rebuild. embeddings.py is
# self-contained (fastembed + stdlib, no backend imports), so the package __init__
# and it alone are enough to run the real check here.
#
# Run as appuser, after the USER switch: the cache lands in /home/appuser, which is
# where the process will look for it. Doing this as root would put it in /root and
# the download would silently happen again at runtime -- the image would be bigger
# AND still fetch, which is the worst of both.
#
# verify_dimension() rather than a bare load, because it does the download AND
# checks the model still emits the 384-wide vectors the schema declares. Swapping
# the model without migrating the column now fails the build, which is the cheapest
# place to find it -- the alternative is an INSERT blowing up mid-ingest.
ENV FASTEMBED_CACHE_PATH=/home/appuser/.cache/fastembed
USER appuser
COPY --chown=appuser:appuser backend/__init__.py backend/embeddings.py ./backend/
RUN python -c "from backend.embeddings import verify_dimension; verify_dimension()"

# App code last: a change here reuses the resolved venv and the baked model above.
COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser alembic.ini ./
RUN chmod +x backend/entrypoint.sh

EXPOSE 8000

# urllib, not curl: slim images have no curl, and installing one just to probe is
# a package more than the runtime needs. --start-period covers boot without the
# failures during it counting toward the retry budget.
# Only compose consumes this: `restart` and `depends_on: condition: service_healthy`.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status == 200 else 1)"]

# Migrations then uvicorn: `docker compose up` has to produce a working app, not one
# that needs a second command nobody read about.
CMD ["./backend/entrypoint.sh"]
