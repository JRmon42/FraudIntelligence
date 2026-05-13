# syntax=docker/dockerfile:1.7
FROM mcr.microsoft.com/azurelinux/base/python:3.12 AS builder

WORKDIR /build
COPY pyproject.toml ./
COPY report.py models.py ./
RUN python3 -m pip install --no-cache-dir build && \
    python3 -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM mcr.microsoft.com/azurelinux/base/python:3.12

LABEL org.opencontainers.image.title="eba-reporter" \
      org.opencontainers.image.description="EBA/GL/2020/01 quarterly fraud reporting batch job" \
      org.opencontainers.image.source="https://github.com/FraudIntelligence/eba-reporter"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Run as non-root for Container Apps Job. Azure Linux base lacks shadow-utils
# (no useradd), so we install it before creating the runtime user. Use tdnf
# which is the package manager on the Azure Linux 3 base image.
USER root
RUN tdnf install -y shadow-utils && tdnf clean all && \
    useradd --create-home --uid 10001 ebareporter
USER ebareporter
WORKDIR /home/ebareporter

COPY --from=builder /wheels /wheels
RUN pip3 install --user --no-cache-dir /wheels/*.whl && rm -rf /wheels

COPY --chown=ebareporter:ebareporter report.py models.py ./
COPY --chown=ebareporter:ebareporter templates ./templates

ENV PATH="/home/ebareporter/.local/bin:${PATH}"

ENTRYPOINT ["python3", "-m", "report"]
CMD ["--help"]
