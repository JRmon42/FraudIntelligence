# syntax=docker/dockerfile:1.7
# ----- Stage 1: build wheels -----
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
COPY pyproject.toml ./
COPY app ./app

RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install .

# ----- Stage 2: distroless runtime -----
FROM gcr.io/distroless/python3-debian12:nonroot

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/opt/venv/lib/python3.11/site-packages" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SCORING_API_PORT=8080

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/app /app/app

WORKDIR /app
EXPOSE 8080
USER nonroot

# distroless python image entrypoint is /usr/bin/python3.11
CMD ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--http", "h11", "--no-access-log"]
