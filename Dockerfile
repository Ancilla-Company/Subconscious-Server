# ── Stage 1: Build dependencies ────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install build tools (gcc needed for some native wheels + venv)
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Create an isolated venv so the install path is always predictable.
# hatchling (the build backend) must be present before `pip install .`
COPY pyproject.toml README.md ./
RUN python -m venv /venv && \
    /venv/bin/pip install --upgrade pip hatchling && \
    /venv/bin/pip install . && \
    find /venv -name "*.pyc" -delete && \
    find /venv -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Copy application source
COPY app/ /build/app/
COPY migrations/ /build/migrations/
COPY alembic.ini /build/alembic.ini

# ── Stage 2: Standard runtime (slim) ───────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy virtualenv and app files from builder
COPY --from=builder /venv /venv
COPY --from=builder /build/app /app/app
COPY --from=builder /build/migrations /app/migrations
COPY --from=builder /build/alembic.ini /app/alembic.ini

ENV PYTHONPATH=/app:/venv/lib/python3.12/site-packages \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Create non-root user, ensure the data directory exists for SQLite + LMDB,
# and hand ownership of /app and /venv to the unprivileged user.
RUN groupadd -g 1000 appuser || true && useradd -u 1000 -g 1000 -m appuser || true && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app /venv

USER appuser

ENTRYPOINT ["/venv/bin/python3", "-m", "uvicorn", "app.main:app", \
            "--host", "0.0.0.0", "--port", "8000", \
            "--workers", "1"
            ]
            # "--loop", "uvloop", \
            # "--http", "httptools", \
            # "--no-access-log", \
            # "--timeout-graceful-shutdown", "5", \
            # "--proxy-headers", "--forwarded-allow-ips", "*"
