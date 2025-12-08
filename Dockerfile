# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY carelesswhisper/ ./carelesswhisper/
COPY LICENSE .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY carelesswhisper/ ./carelesswhisper/

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TOOL=${TOOL:-cli}

# Create a non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Default command - runs the selected tool via CLI
CMD ["python", "-m", "carelesswhisper.tools.cli"]

# Usage examples:
# docker build -t careless-whisper .
# docker run -it careless-whisper                                                    # Run CLI
# docker run -it careless-whisper python -m carelesswhisper.tools.fingerprint        # Run fingerprint tool
# docker run -it careless-whisper python -m carelesswhisper.tools.dos                # Run DoS tool
# TOOL=fingerprint docker run -it -e TOOL=fingerprint careless-whisper               # Using TOOL env var
