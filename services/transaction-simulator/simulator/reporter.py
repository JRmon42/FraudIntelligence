"""Build JSON + interactive HTML reports from collected run metrics."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import mean

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


@dataclass
class RunResult:
    target: str
    pattern: str
    target_tps: int
    duration_s: float
    started_at: str
    finished_at: str
    requests_sent: int
    requests_ok: int
    requests_failed: int
    status_counts: dict[str, int] = field(default_factory=dict)
    decision_counts: dict[str, int] = field(default_factory=dict)
    latencies_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def actual_tps(self) -> float:
        return self.requests_sent / self.duration_s if self.duration_s else 0.0

    def percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        return float(np.percentile(self.latencies_ms, p))

    def summary(self) -> dict:
        return {
            "target": self.target,
            "pattern": self.pattern,
            "target_tps": self.target_tps,
            "actual_tps": round(self.actual_tps, 2),
            "duration_s": self.duration_s,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "requests": {
                "sent": self.requests_sent,
                "ok": self.requests_ok,
                "failed": self.requests_failed,
                "by_status": self.status_counts,
            },
            "decisions": self.decision_counts,
            "latency_ms": {
                "count": len(self.latencies_ms),
                "mean": round(mean(self.latencies_ms), 3) if self.latencies_ms else 0.0,
                "p50": round(self.percentile(50), 3),
                "p95": round(self.percentile(95), 3),
                "p99": round(self.percentile(99), 3),
                "max": round(max(self.latencies_ms), 3) if self.latencies_ms else 0.0,
            },
            "errors_sample": self.errors[:25],
        }


def write_reports(result: RunResult, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    html_path = out_dir / "report.html"

    payload = result.summary()
    payload["latencies_ms"] = result.latencies_ms
    json_path.write_text(json.dumps(payload, indent=2))

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Latency distribution (ms)",
            "Decision distribution",
            "HTTP status counts",
            "Latency percentiles",
        ),
        specs=[
            [{"type": "histogram"}, {"type": "pie"}],
            [{"type": "bar"}, {"type": "bar"}],
        ],
    )

    if result.latencies_ms:
        fig.add_trace(
            go.Histogram(x=result.latencies_ms, nbinsx=60, marker_color="#3b82f6", name="latency"),
            row=1,
            col=1,
        )

    if result.decision_counts:
        fig.add_trace(
            go.Pie(
                labels=list(result.decision_counts.keys()),
                values=list(result.decision_counts.values()),
                hole=0.4,
                name="decisions",
            ),
            row=1,
            col=2,
        )

    if result.status_counts:
        fig.add_trace(
            go.Bar(
                x=list(result.status_counts.keys()),
                y=list(result.status_counts.values()),
                marker_color="#10b981",
                name="status",
            ),
            row=2,
            col=1,
        )

    pct_labels = ["p50", "p95", "p99", "max"]
    pct_values = [
        result.percentile(50),
        result.percentile(95),
        result.percentile(99),
        max(result.latencies_ms) if result.latencies_ms else 0.0,
    ]
    fig.add_trace(
        go.Bar(x=pct_labels, y=pct_values, marker_color="#ef4444", name="latency_pct"),
        row=2,
        col=2,
    )

    fig.update_layout(
        title=f"Heimdall Simulator — {result.pattern} @ {result.target_tps} TPS",
        height=820,
        showlegend=False,
        template="plotly_white",
    )

    summary_html = (
        "<table style='font-family:sans-serif;border-collapse:collapse;margin:16px 0'>"
        + "".join(
            f"<tr><td style='padding:4px 12px;border:1px solid #ddd'><b>{k}</b></td>"
            f"<td style='padding:4px 12px;border:1px solid #ddd'>{v}</td></tr>"
            for k, v in result.summary().items()
            if k not in ("errors_sample",)
        )
        + "</table>"
    )

    html_path.write_text(
        "<html><head><meta charset='utf-8'><title>Simulator report</title></head>"
        f"<body><h1>Simulator Report</h1>{summary_html}"
        f"{fig.to_html(include_plotlyjs='cdn', full_html=False)}"
        "</body></html>"
    )
    return json_path, html_path


def to_dict(result: RunResult) -> dict:
    return asdict(result)
