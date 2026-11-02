# syntax=docker/dockerfile:1

# ---------------------------------------------------------
# Stage 1: Build virtual environment with uv
# ---------------------------------------------------------
FROM python:3.14-slim AS builder

WORKDIR /app

# Install uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# UV settings
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install dependencies using frozen lockfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ---------------------------------------------------------
# Stage 2: Production runtime image
# ---------------------------------------------------------
FROM python:3.14-slim AS runner

WORKDIR /app

# Install runtime system packages (curl for healthchecks, libpq5 for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Environment settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Create unprivileged user & directories
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/sh -m appuser && \
    mkdir -p /app/staticfiles /app/logs && \
    chown -R appuser:appgroup /app

# Copy virtual environment from builder stage
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv

# Copy application source code
COPY --chown=appuser:appgroup . .

# Ensure entrypoint script is executable
RUN chmod +x /app/docker-entrypoint.sh

# Collect static files into STATIC_ROOT using a dummy secret key for build
RUN SECRET_KEY=dummy-build-key-for-collectstatic python manage.py collectstatic --noinput

# Switch to non-root user
USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2", "--access-logfile", "-", "--error-logfile", "-"]
