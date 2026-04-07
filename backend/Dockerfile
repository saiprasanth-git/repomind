# ── Stage 1: Builder ──────────────────────────────────────────────────────────
# Install dependencies in a separate stage so they're cached between builds.
# Only when requirements.txt changes do we rebuild this layer.
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies needed for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
# Slim final image — copy only what we need from the builder.
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install only runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/

# Create temp directory for repo clones
RUN mkdir -p /tmp/repomind_repos

# Non-root user for security
RUN useradd -m -u 1000 repomind && chown -R repomind:repomind /app /tmp/repomind_repos
USER repomind

# Expose the port
EXPOSE 8000

# Health check — Kubernetes uses this to know when the pod is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# Start the server
# --workers 1: single worker (we use async, not threads)
# --host 0.0.0.0: listen on all interfaces (required in containers)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
