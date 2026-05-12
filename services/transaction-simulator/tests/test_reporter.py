from pathlib import Path

from simulator.reporter import RunResult, write_reports


def _make_result() -> RunResult:
    return RunResult(
        target="http://x",
        pattern="normal",
        target_tps=100,
        duration_s=10.0,
        started_at="2025-01-01T00:00:00Z",
        finished_at="2025-01-01T00:00:10Z",
        requests_sent=1000,
        requests_ok=990,
        requests_failed=10,
        status_counts={"200": 990, "500": 10},
        decision_counts={"approve": 700, "decline": 200, "review": 90},
        latencies_ms=[float(x % 50) + 1.0 for x in range(1000)],
        errors=[],
    )


def test_summary_shapes():
    r = _make_result()
    s = r.summary()
    assert s["requests"]["sent"] == 1000
    assert s["latency_ms"]["p99"] >= s["latency_ms"]["p50"]
    assert s["decisions"]["approve"] == 700


def test_write_reports(tmp_path: Path):
    r = _make_result()
    j, h = write_reports(r, tmp_path)
    assert j.exists() and j.stat().st_size > 0
    assert h.exists() and h.stat().st_size > 0
    assert "Simulator Report" in h.read_text()
