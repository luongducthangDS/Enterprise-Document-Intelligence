# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

WORKDIR /app

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN python -m venv "$VIRTUAL_ENV"

COPY requirements.prod.txt .
RUN pip install --no-cache-dir -r requirements.prod.txt

# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

# Copy the runtime environment to a location accessible by the non-root user.
COPY --from=builder /opt/venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Security: run as non-root user
RUN useradd -m appuser

# Copy application code
COPY . .

# Create data directory with correct ownership
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://localhost:{port}/health')" || exit 1

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

