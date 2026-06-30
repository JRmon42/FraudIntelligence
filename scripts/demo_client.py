#!/usr/bin/env python3
"""Heimdall demo client — drives the live scoring API over HTTPS.

Dependency-free (stdlib only: urllib, argparse, concurrent.futures). Designed to
run on hosts without curl/jq. Reads the scoring Front Door host from
``.env.deployed`` (key ``SCORING_FRONTDOOR_HOST``) unless ``--host`` is given.

Subcommands:
  health                      GET /healthz and /readyz
  score   [--profile P]       Score one transaction (normal|high), with stage timings
  load    --tps N --duration S   Send a representative burst, report throughput + latency
  inject  --pattern ring      Emit a circular fraud-ring of transactions
  all                         Scripted sequence: health -> baseline -> load -> ring
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COUNTRIES = ["SE", "NO", "DK", "FI", "EE"]
CHANNELS = ["ECOM", "POS", "ATM", "MOTO"]

# Seeded demo entities — MUST match services/scoring-api/app/seed_data.py.
# These IDs are recognised by the live scoring API's in-memory feature store
# (when SEED_DEMO_FEATURES=true) and drive real APPROVE/SCA/DECLINE decisions.
DEMO_BLOCKED_CARD = "card-blocked-001"
DEMO_HOT_CARD = "card-hot-014"
DEMO_CORP_CARD = "card-corp-700"
DEMO_RING_CARD = "card-ring-099"
DEMO_RING_CARDS = ["card-ring-099", "card-ring-100", "card-ring-101"]
DEMO_FRAUD_MERCHANT = "merch-darkbazaar-66"
DEMO_RISKY_MERCHANT = "merch-luckyspin-21"
DEMO_CLEAN_MERCHANT = "merch-nordstore-5"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def load_host(explicit: str | None) -> str:
    """Resolve the scoring host from --host, env, or .env.deployed."""
    if explicit:
        return explicit.replace("https://", "").replace("http://", "").rstrip("/")
    env_host = os.environ.get("SCORING_FRONTDOOR_HOST")
    if env_host:
        return env_host
    env_file = os.path.join(REPO_ROOT, ".env.deployed")
    if os.path.isfile(env_file):
        with open(env_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("SCORING_FRONTDOOR_HOST="):
                    return line.split("=", 1)[1].strip().strip('"')
    sys.exit(
        "ERROR: scoring host not found. Pass --host, set SCORING_FRONTDOOR_HOST, "
        "or run scripts/deploy.sh to generate .env.deployed."
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_at_hour(hour: int) -> str:
    """ISO timestamp for today at a given UTC hour (drives the model's
    time-of-day fraud signal — the ensemble learned that high-value
    card-not-present purchases in the small hours are high risk)."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=hour % 24, minute=random.randint(0, 59),
                       second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_tx(profile: str = "normal", **overrides) -> dict:
    """Build a valid ScoreRequest payload (snake_case, extra=forbid).

    Every profile produces a decision from the **live stacked-ensemble**
    (XGBoost + LightGBM + Logistic, ONNX in-process). The ensemble consumes the
    fraud-ring **GNN**'s per-card features (ring_score + GraphSAGE embedding,
    published into the feature store), so the elevated decisions are genuinely
    GNN-driven: an ordinary small-hours transaction on a GNN-flagged ring card is
    stepped up / declined, while the *identical* transaction on a random card is
    approved.
      normal  -> random card, daytime, low value     -> APPROVE
      sca     -> ring card, 02:00-03:59, EUR 300-550  -> SCA  (GNN-driven step-up)
      decline -> ring card, 00:00-01:59, EUR 350-700  -> DECLINE (GNN-driven)
      ring    -> alias of ``sca`` (GNN ring step-up)
      high    -> alias of ``decline``
    A seeded blocked card (``blocked`` profile) is additionally hard-declined by
    the policy layer to demonstrate the rule path.
    """
    txid = f"demo-{random.randint(10**5, 10**6)}"
    if profile == "blocked":
        tx = {
            "transaction_id": txid,
            "card_id": DEMO_BLOCKED_CARD,
            "merchant_id": DEMO_FRAUD_MERCHANT,
            "amount": round(random.uniform(40, 400), 2),
            "currency": "EUR",
            "country": random.choice(COUNTRIES),
            "channel": "ECOM",
            "timestamp": _ts_at_hour(14),
            "device_fingerprint": f"df-{random.randint(0, 99999)}",
            "ip": "203.0.113.7",
        }
    elif profile in ("ring", "sca"):
        # GNN-flagged ring card, deep-night step-up band -> SCA.
        tx = {
            "transaction_id": txid,
            "card_id": random.choice(DEMO_RING_CARDS),
            "merchant_id": f"m-{random.randint(1, 200)}",
            "amount": round(random.uniform(300, 550), 2),
            "currency": "EUR",
            "country": random.choice(COUNTRIES),
            "channel": "ECOM",
            "timestamp": _ts_at_hour(random.choice([2, 3])),
            "device_fingerprint": f"df-{random.randint(0, 99999)}",
            "ip": "203.0.113.7",
        }
    elif profile in ("high", "decline"):
        # GNN-flagged ring card, midnight high-confidence band -> DECLINE.
        tx = {
            "transaction_id": txid,
            "card_id": random.choice(DEMO_RING_CARDS),
            "merchant_id": f"m-{random.randint(1, 200)}",
            "amount": round(random.uniform(350, 700), 2),
            "currency": "EUR",
            "country": random.choice(COUNTRIES),
            "channel": "ECOM",
            "timestamp": _ts_at_hour(random.choice([0, 1])),
            "device_fingerprint": f"df-{random.randint(0, 99999)}",
            "ip": "203.0.113.7",
        }
    else:  # normal — random card, daytime low value -> APPROVE
        tx = {
            "transaction_id": txid,
            "card_id": f"c-{random.randint(1, 999)}",
            "merchant_id": f"m-{random.randint(1, 200)}",
            "amount": round(random.uniform(5, 250), 2),
            "currency": "SEK",
            "country": random.choice(COUNTRIES),
            "channel": random.choice(["ECOM", "POS"]),
            "timestamp": _ts_at_hour(random.randint(9, 19)),
            "device_fingerprint": f"df-{random.randint(0, 99999)}",
            "ip": "203.0.113.7",
        }
    tx.update(overrides)
    return tx


# Weighted profile mix for representative load bursts: mostly approvals, a
# minority of step-ups, and a few declines — like a healthy production stream.
_MIX_PROFILES = ["normal"] * 7 + ["sca"] * 2 + ["decline"]


def make_mixed_tx(**overrides) -> dict:
    """Draw a transaction from a realistic decision-mix distribution."""
    return make_tx(random.choice(_MIX_PROFILES), **overrides)


def post_score(host: str, tx: dict, explain: bool = False, timeout: int = 20):
    """POST one transaction. Returns (ok, status, body_dict_or_text, elapsed_ms)."""
    url = f"https://{host}/v1/score" + ("?explain=true" if explain else "")
    data = json.dumps(tx).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            elapsed = (time.perf_counter() - t0) * 1000.0
            return True, resp.status, json.loads(body), elapsed
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - t0) * 1000.0
        try:
            return False, exc.code, exc.read().decode(), elapsed
        except Exception:
            return False, exc.code, str(exc), elapsed
    except Exception as exc:  # noqa: BLE001
        elapsed = (time.perf_counter() - t0) * 1000.0
        return False, 0, str(exc), elapsed


def get(host: str, path: str, timeout: int = 15):
    url = f"https://{host}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def pct(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_health(host: str, _args) -> int:
    print(f"==> Health checks against https://{host}")
    ok = True
    for path in ("/healthz", "/readyz"):
        status, body = get(host, path)
        flag = "OK " if status == 200 else "FAIL"
        ok = ok and status == 200
        print(f"  [{flag}] GET {path} -> {status} {body[:160]}")
    return 0 if ok else 1


def cmd_score(host: str, args) -> int:
    tx = make_tx(args.profile)
    print(f"==> Scoring one '{args.profile}' transaction")
    print("  request:", json.dumps(tx))
    ok, status, body, elapsed = post_score(host, tx, explain=True)
    if not ok:
        print(f"  FAIL {status}: {body}")
        return 1
    print(f"  decision={body['decision']} score={body['score']:.4f} "
          f"exemption={body['psd2_exemption']} reasons={body['reason_codes']}")
    print(f"  model={body['model_version']} server_latency_ms={body['latency_ms']} "
          f"client_rtt_ms={elapsed:.1f}")
    if body.get("explain"):
        print("  stage_timings_ms:", json.dumps(body["explain"]))
    return 0


def _run_burst(host: str, total: int, workers: int, profile: str):
    """Send `total` requests with a thread pool. Returns metrics dict."""
    latencies, decisions, errors = [], {}, 0
    tx_factory = make_mixed_tx if profile == "mix" else (lambda: make_tx(profile))
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(post_score, host, tx_factory()) for _ in range(total)]
        for fut in as_completed(futs):
            ok, _status, body, elapsed = fut.result()
            if ok and isinstance(body, dict):
                latencies.append(elapsed)
                decisions[body["decision"]] = decisions.get(body["decision"], 0) + 1
            else:
                errors += 1
    wall = time.perf_counter() - t0
    return {
        "total": total, "ok": len(latencies), "errors": errors,
        "wall_s": wall, "tps": (len(latencies) / wall) if wall else 0.0,
        "p50": pct(latencies, 50), "p95": pct(latencies, 95), "p99": pct(latencies, 99),
        "decisions": decisions,
    }


def cmd_load(host: str, args) -> int:
    target = args.tps * args.duration
    total = min(target, args.max)
    workers = min(args.workers, max(1, total))
    print(f"==> Load: target {args.tps} TPS x {args.duration}s = {target} req "
          f"(sending a representative burst of {total}, {workers} workers)")
    m = _run_burst(host, total, workers, args.profile)
    print(f"  sent_ok={m['ok']}/{m['total']} errors={m['errors']} "
          f"wall={m['wall_s']:.1f}s achieved_tps={m['tps']:.0f}")
    print(f"  client_latency_ms p50={m['p50']:.1f} p95={m['p95']:.1f} p99={m['p99']:.1f}")
    print(f"  decision_mix={m['decisions']}")
    return 0 if m["errors"] == 0 else 1


def cmd_inject(host: str, args) -> int:
    cards = [f"ring-card-{i:02d}" for i in range(args.cards)]
    merchants = [f"ring-mer-{i:02d}" for i in range(args.merchants)]
    print(f"==> Injecting '{args.pattern}' pattern: {args.cards} cards across "
          f"{args.merchants} merchants (circular value flow)")
    sent, declines, scas, approves, errors = 0, 0, 0, 0, 0
    scores = []
    for i, card in enumerate(cards):
        merchant = merchants[i % len(merchants)]  # circular assignment
        tx = make_tx(
            "high",
            transaction_id=f"ring-{int(time.time())}-{i}",
            card_id=card,
            merchant_id=merchant,
            amount=round(random.uniform(3000, 6000), 2),
            currency="EUR",
            country="SE",
            channel="ECOM",
        )
        ok, status, body, _elapsed = post_score(host, tx)
        sent += 1
        if ok and isinstance(body, dict):
            scores.append(body["score"])
            d = body["decision"]
            approves += d == "APPROVE"
            scas += d == "SCA"
            declines += d == "DECLINE"
            print(f"  {card} -> {merchant}  €{tx['amount']:>8}  "
                  f"score={body['score']:.3f}  decision={d}")
        else:
            errors += 1
            print(f"  {card} -> {merchant}  ERROR {status}: {str(body)[:80]}")
    avg = statistics.mean(scores) if scores else 0.0
    print(f"==> Ring summary: sent={sent} approve={approves} sca={scas} "
          f"decline={declines} errors={errors} avg_score={avg:.3f}")
    print("    (Topology: closed circular loop. The offline GNN on Fabric Spark is "
          "what flags the ring shape; the in-line scorer sees per-tx features only.)")
    return 0 if errors == 0 else 1


def cmd_scenario(host: str, _args) -> int:
    """Walk the curated decision spectrum (APPROVE / SCA / DECLINE) using the
    production decision rules over feature-enriched demo transactions. This shows
    declines and false-positive (SCA step-up) handling that the stubbed live
    endpoint cannot produce on its own. See scripts/demo_scenarios.py."""
    try:
        import demo_scenarios as ds
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import demo_scenarios as ds
    print("==> Decision scenarios (production rules + enriched demo features)")
    for sc in ds.SCENARIOS:
        r = ds.evaluate(sc)
        print(f"\n  [{r['decision']}] {sc.title}  "
              f"(score={r['score']:.2f}, exemption={r['psd2_exemption']})")
        print(f"     {sc.card.card_id} → {sc.merchant.merchant_id}  "
              f"{sc.currency} {sc.amount:.2f}  {sc.country}/{sc.channel}")
        print(f"     reasons: {', '.join(r['reason_codes'])}")
        print(f"     handling: {sc.handling}")
        if sc.recovers_after_sca and r["decision"] == "SCA":
            print("     → 3-D Secure passed → APPROVED (false positive avoided).")
    tally = ds.scenario_summary()
    print(f"\n==> Tally: APPROVE={tally.get('APPROVE', 0)} "
          f"SCA={tally.get('SCA', 0)} DECLINE={tally.get('DECLINE', 0)}")
    return 0


def cmd_all(host: str, args) -> int:
    print("############ HEIMDALL LIVE DEMO ############\n")
    rc = cmd_health(host, args)
    print()
    rc |= cmd_score(host, argparse.Namespace(profile="normal"))
    print()
    rc |= cmd_score(host, argparse.Namespace(profile="high"))
    print()
    rc |= cmd_scenario(host, args)
    print()
    rc |= cmd_load(host, argparse.Namespace(
        tps=args.tps, duration=args.duration, max=args.max,
        workers=args.workers, profile="normal"))
    print()
    rc |= cmd_inject(host, argparse.Namespace(
        pattern="ring", cards=args.cards, merchants=args.merchants))
    print("\n############ DEMO COMPLETE ############")
    return rc


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Heimdall live demo client")
    p.add_argument("--host", help="Scoring host (default: from .env.deployed)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="GET /healthz and /readyz")

    sp = sub.add_parser("score", help="Score one transaction")
    sp.add_argument(
        "--profile",
        choices=["normal", "sca", "decline", "high"],
        default="normal",
    )

    lp = sub.add_parser("load", help="Send a representative load burst")
    lp.add_argument("--tps", type=int, default=200)
    lp.add_argument("--duration", type=int, default=5, help="seconds")
    lp.add_argument("--max", type=int, default=1000, help="hard cap on total requests")
    lp.add_argument("--workers", type=int, default=20)
    lp.add_argument(
        "--profile",
        choices=["normal", "sca", "decline", "high", "mix"],
        default="mix",
    )

    ip = sub.add_parser("inject", help="Inject a fraud-ring pattern")
    ip.add_argument("--pattern", choices=["ring"], default="ring")
    ip.add_argument("--cards", type=int, default=10)
    ip.add_argument("--merchants", type=int, default=3)

    sub.add_parser("scenario",
                   help="Walk the decision spectrum (approve / SCA step-up / decline)")

    ap = sub.add_parser("all", help="Run the full scripted demo")
    ap.add_argument("--tps", type=int, default=200)
    ap.add_argument("--duration", type=int, default=5)
    ap.add_argument("--max", type=int, default=600)
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--cards", type=int, default=10)
    ap.add_argument("--merchants", type=int, default=3)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    host = load_host(args.host)
    dispatch = {
        "health": cmd_health, "score": cmd_score, "load": cmd_load,
        "inject": cmd_inject, "scenario": cmd_scenario, "all": cmd_all,
    }
    return dispatch[args.cmd](host, args)


if __name__ == "__main__":
    raise SystemExit(main())
