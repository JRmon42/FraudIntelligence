import json
from pathlib import Path

import httpx
from typer.testing import CliRunner

from simulator.main import app

runner = CliRunner()


def test_cli_help_lists_patterns():
    result = runner.invoke(app, ["list-patterns"])
    assert result.exit_code == 0
    for p in ("normal", "fraud-ring", "account-takeover", "mixed"):
        assert p in result.stdout


def test_run_against_mock(monkeypatch, tmp_path: Path):
    """Patch httpx.AsyncClient.post to a deterministic local responder, then call run()."""

    async def fake_post(self, url, json=None, timeout=None):  # noqa: A002
        decision = "approve" if (int(json["amount"]["valueEur"]) % 2) == 0 else "review"
        request = httpx.Request("POST", url, json=json)
        return httpx.Response(200, json={"decision": decision, "score": 0.1}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = tmp_path / "rep"
    result = runner.invoke(
        app,
        [
            "run",
            "--target",
            "http://mock",
            "--tps",
            "50",
            "--duration",
            "1",
            "--pattern",
            "normal",
            "--concurrency",
            "8",
            "--out-dir",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads((out / "report.json").read_text())
    assert payload["requests"]["ok"] >= 1
    assert payload["latency_ms"]["p99"] >= 0
    assert (out / "report.html").exists()
