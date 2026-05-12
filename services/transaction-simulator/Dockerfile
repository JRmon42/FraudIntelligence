FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY simulator ./simulator

RUN pip install --upgrade pip && pip install .

RUN useradd --uid 10001 --create-home --shell /bin/bash simulator \
    && mkdir -p /app/reports && chown -R simulator:simulator /app
USER simulator

ENTRYPOINT ["python", "-m", "simulator"]
CMD ["run", "--help"]
