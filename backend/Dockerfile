FROM python:3.11-slim

WORKDIR /pitiq

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install deps before copying src so this layer is cached unless pyproject.toml changes
COPY backend/pyproject.toml backend/pyproject.toml
RUN mkdir -p backend/src/pitiq && \
    touch backend/src/pitiq/__init__.py && \
    pip install --no-cache-dir -e backend

# Copy actual source (replaces the stub above)
COPY backend/src backend/src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "pitiq.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
