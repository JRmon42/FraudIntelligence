"""Shared fixtures for integration tests.

These tests assume `docker compose up -d` has been executed and the stack is healthy.
Override targets via env vars:

    SCORING_API_URL        default http://localhost:8080
    ORCHESTRATOR_URL       default http://localhost:8090
    COSMOS_ENDPOINT        default https://localhost:8081
    COSMOS_KEY             default emulator key
"""
from __future__ import annotations

import os
import time

import httpx
import pytest

SCORING_API_URL = os.environ.get("SCORING_API_URL", "http://localhost:8080")
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://localhost:8090")
COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT", "https://localhost:8081")
COSMOS_KEY = os.environ.get(
    "COSMOS_KEY",
    "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==",
)


def _wait_for(url: str, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code < 500:
                return
        except Exception as exc:
            last_exc = exc
        time.sleep(2.0)
    raise RuntimeError(f"Timed out waiting for {url}: {last_exc}")


@pytest.fixture(scope="session")
def scoring_api_url() -> str:
    _wait_for(f"{SCORING_API_URL}/health")
    return SCORING_API_URL


@pytest.fixture(scope="session")
def orchestrator_url() -> str:
    _wait_for(f"{ORCHESTRATOR_URL}/health")
    return ORCHESTRATOR_URL


@pytest.fixture(scope="session")
def cosmos_config() -> dict:
    return {"endpoint": COSMOS_ENDPOINT, "key": COSMOS_KEY}
