"""End-to-end smoke driving the simulator against the live compose stack."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SIMULATOR_DIR = REPO_ROOT / "services" / "transaction-simulator"


def _run_simulator(target: str, duration: int, tps: int, out_dir: Path) -> dict:
    cmd = [
        sys.executable, "-m", "simulator", "run",
        "--target", target,
        "--tps", str(tps),
        "--pattern", "mixed",
        "--duration", str(duration),
        "--out-dir", str(out_dir),
        "--concurrency", "64",
    ]
    env = {"PYTHONPATH": str(SIMULATOR_DIR)}
    res = subprocess.run(cmd, cwd=SIMULATOR_DIR, env={**env, **dict(__import__("os").environ)},
                         capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"simulator failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    return json.loads((out_dir / "report.json").read_text())


def test_p99_latency_and_decision_distribution(scoring_api_url, tmp_path):
    report = _run_simulator(scoring_api_url, duration=30, tps=200, out_dir=tmp_path)

    p99 = report["latency_ms"]["p99"]
    assert p99 < 50.0, f"p99 latency {p99}ms exceeds 50ms budget"

    total_ok = report["requests"]["ok"]
    assert total_ok > 0, "no successful scoring responses"

    decisions = report["decisions"]
    total = sum(decisions.values())
    assert total > 0
    approve_pct = decisions.get("approve", 0) / total
    decline_pct = decisions.get("decline", 0) / total
    review_pct = decisions.get("review", 0) / total
    # Loose bounds: scoring API distribution depends on mock model
    assert 0.50 <= approve_pct <= 0.99, f"approve share out of bounds: {approve_pct:.2%}"
    assert decline_pct <= 0.30, f"decline share too high: {decline_pct:.2%}"
    assert 0.0 <= review_pct <= 0.30, f"review share out of bounds: {review_pct:.2%}"


def test_orchestrator_processes_sample_alert(orchestrator_url):
    sample_alert = {
        "alertId": "alert-int-001",
        "transactionId": "tx-int-001",
        "score": 0.92,
        "rationale": "circular flow over 3 merchants",
        "context": {"pan": "4000110000000010", "ringId": "ring-int-001"},
    }
    with httpx.Client(timeout=30.0) as c:
        r = c.post(f"{orchestrator_url}/alerts", json=sample_alert)
        assert r.status_code in (200, 202), r.text
        body = r.json()
        assert body.get("status") in ("processed", "queued", "completed")
        assert body.get("alertId") == "alert-int-001"


def test_cosmos_has_features_after_run(cosmos_config):
    """After a 30s run the feature-builder function should have written some rows."""
    try:
        from azure.cosmos import CosmosClient
    except ImportError:
        pytest.skip("azure-cosmos not installed")

    client = CosmosClient(
        cosmos_config["endpoint"],
        credential=cosmos_config["key"],
        connection_verify=False,
    )
    db = client.create_database_if_not_exists("fraudintel")
    container = db.create_container_if_not_exists(
        id="features",
        partition_key={"paths": ["/pan"], "kind": "Hash"},
    )
    items = list(container.query_items(
        query="SELECT VALUE COUNT(1) FROM c",
        enable_cross_partition_query=True,
    ))
    count = items[0] if items else 0
    assert count >= 1, f"expected at least 1 feature row in cosmos; got {count}"


def test_simulator_can_be_invoked():
    """Sanity check that simulator CLI is importable in this environment."""
    asyncio.get_event_loop_policy()  # touch asyncio so CI logs include the import
    res = subprocess.run(
        [sys.executable, "-m", "simulator", "list-patterns"],
        cwd=SIMULATOR_DIR, capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0, res.stderr
    assert "fraud-ring" in res.stdout
