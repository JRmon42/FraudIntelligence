"""CLI entry point for the Heimdall transaction simulator."""

from __future__ import annotations

import asyncio
import random
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.table import Table

from simulator import patterns
from simulator.data import Population
from simulator.reporter import RunResult, write_reports

app = typer.Typer(add_completion=False, help="Heimdall transaction simulator")
console = Console()


async def _worker(
    name: int,
    client: httpx.AsyncClient,
    queue: asyncio.Queue,
    result: RunResult,
    endpoint: str,
) -> None:
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            return
        payload = item.to_payload()
        t0 = time.perf_counter()
        try:
            r = await client.post(endpoint, json=payload, timeout=5.0)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            result.latencies_ms.append(elapsed_ms)
            result.status_counts[str(r.status_code)] = result.status_counts.get(str(r.status_code), 0) + 1
            if r.is_success:
                result.requests_ok += 1
                try:
                    body = r.json()
                    decision = str(body.get("decision", body.get("action", "unknown"))).lower()
                except Exception:
                    decision = "unparseable"
                result.decision_counts[decision] = result.decision_counts.get(decision, 0) + 1
            else:
                result.requests_failed += 1
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            result.latencies_ms.append(elapsed_ms)
            result.requests_failed += 1
            if len(result.errors) < 50:
                result.errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            queue.task_done()


async def _producer(
    queue: asyncio.Queue,
    pattern_iter,
    tps: int,
    duration: float,
    result: RunResult,
) -> None:
    interval = 1.0 / tps
    deadline = time.monotonic() + duration
    next_emit = time.monotonic()
    while time.monotonic() < deadline:
        await queue.put(next(pattern_iter))
        result.requests_sent += 1
        next_emit += interval
        sleep_for = next_emit - time.monotonic()
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)


async def _drive(
    target: str,
    tps: int,
    duration: float,
    pattern_name: str,
    concurrency: int,
    seed: int,
) -> RunResult:
    rng = random.Random(seed)
    population = Population(rng, n_cards=2000, n_merchants=600)
    pattern_iter = iter(patterns.build(pattern_name, population, rng))

    started_at = datetime.now(UTC).isoformat()
    result = RunResult(
        target=target,
        pattern=pattern_name,
        target_tps=tps,
        duration_s=duration,
        started_at=started_at,
        finished_at="",
        requests_sent=0,
        requests_ok=0,
        requests_failed=0,
        status_counts={},
        decision_counts={},
        latencies_ms=[],
        errors=[],
    )

    limits = httpx.Limits(max_keepalive_connections=concurrency, max_connections=concurrency * 2)
    endpoint = target.rstrip("/") + "/score"

    queue: asyncio.Queue = asyncio.Queue(maxsize=concurrency * 4)
    async with httpx.AsyncClient(limits=limits, http2=False) as client:
        workers = [
            asyncio.create_task(_worker(i, client, queue, result, endpoint)) for i in range(concurrency)
        ]
        t0 = time.monotonic()
        await _producer(queue, pattern_iter, tps, duration, result)
        await queue.join()
        for _ in workers:
            await queue.put(None)
        await asyncio.gather(*workers, return_exceptions=True)
        result.duration_s = round(time.monotonic() - t0, 3)

    result.finished_at = datetime.now(UTC).isoformat()
    return result


def _print_summary(result: RunResult) -> None:
    table = Table(title=f"Simulator — {result.pattern} @ {result.target_tps} TPS")
    table.add_column("metric")
    table.add_column("value", justify="right")
    s = result.summary()
    table.add_row("requests sent", str(s["requests"]["sent"]))
    table.add_row("requests ok", str(s["requests"]["ok"]))
    table.add_row("requests failed", str(s["requests"]["failed"]))
    table.add_row("actual TPS", f"{s['actual_tps']:.1f}")
    table.add_row("p50 latency (ms)", f"{s['latency_ms']['p50']:.2f}")
    table.add_row("p95 latency (ms)", f"{s['latency_ms']['p95']:.2f}")
    table.add_row("p99 latency (ms)", f"{s['latency_ms']['p99']:.2f}")
    table.add_row("max latency (ms)", f"{s['latency_ms']['max']:.2f}")
    table.add_row("decisions", ", ".join(f"{k}={v}" for k, v in Counter(s["decisions"]).most_common()))
    console.print(table)


@app.command()
def run(
    target: str = typer.Option("http://localhost:8080", help="Scoring API base URL"),
    tps: int = typer.Option(500, min=1, max=20000, help="Target transactions per second"),
    pattern: str = typer.Option("mixed", help=f"One of: {', '.join(patterns.PATTERNS)}"),
    duration: float = typer.Option(60.0, min=1.0, help="Run duration in seconds"),
    concurrency: int = typer.Option(64, min=1, max=2048, help="HTTP concurrency"),
    seed: int = typer.Option(42, help="RNG seed for reproducibility"),
    out_dir: Path = typer.Option(Path("reports"), help="Output dir for report.json/html"),
    fail_on_p99_ms: float = typer.Option(0.0, help="Exit non-zero if p99 latency > this (ms)"),
) -> None:
    """Run a load test against the scoring API."""
    if pattern not in patterns.PATTERNS:
        raise typer.BadParameter(f"pattern must be one of {patterns.PATTERNS}")

    console.print(
        f"[bold cyan]Simulator starting[/]: target={target} tps={tps} pattern={pattern} duration={duration}s"
    )
    result = asyncio.run(_drive(target, tps, duration, pattern, concurrency, seed))
    json_path, html_path = write_reports(result, out_dir)
    _print_summary(result)
    console.print(f"[green]Reports:[/] {json_path} {html_path}")
    p99 = result.percentile(99)
    if fail_on_p99_ms > 0 and p99 > fail_on_p99_ms:
        console.print(f"[red]p99 {p99:.2f}ms > threshold {fail_on_p99_ms:.2f}ms[/]")
        raise typer.Exit(code=2)


@app.command("list-patterns")
def list_patterns() -> None:
    """List available traffic patterns."""
    for p in patterns.PATTERNS:
        console.print(f"- {p}")


if __name__ == "__main__":
    app()
