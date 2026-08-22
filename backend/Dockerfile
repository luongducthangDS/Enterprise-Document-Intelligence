# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

WORKDIR /app

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN python -m venv "$VIRTUAL_ENV"

COPY backend/requirements.prod.txt ./backend_requirements.txt
RUN pip install --no-cache-dir -r backend_requirements.txt

# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONPATH="/app/backend:/app"

RUN useradd -m appuser

COPY backend/ /app/backend/
COPY src/ /app/src/
COPY config/ /app/config/
COPY data/ /app/data/
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
