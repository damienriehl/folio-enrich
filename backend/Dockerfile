FROM python:3.13-slim AS base

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Download spacy model
RUN python -m spacy download en_core_web_sm

# Copy application code
COPY app/ app/

# Create non-root user
RUN useradd -m -r appuser && \
    mkdir -p /home/appuser/.folio-enrich/jobs && \
    chown -R appuser:appuser /home/appuser
USER appuser

ENV FOLIO_ENRICH_JOBS_DIR=/home/appuser/.folio-enrich/jobs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
