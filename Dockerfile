# Build stage
FROM python:3.11-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Install dependencies first (cached layer) using the lockfile
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy project files and install the project itself
COPY carelesswhisper/ ./carelesswhisper/
COPY LICENSE README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Copy the resolved virtual environment and application code
COPY --from=builder /app/.venv /app/.venv
COPY carelesswhisper/ ./carelesswhisper/

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Create a non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Default command - runs the interactive CLI
CMD ["carelesswhisper"]

# Usage examples:
# docker build -t careless-whisper .
# docker run -it careless-whisper                       # Run CLI
# docker run -it careless-whisper cw-fingerprint --help # Run fingerprint tool
# docker run -it careless-whisper cw-dos                # Run DoS tool
