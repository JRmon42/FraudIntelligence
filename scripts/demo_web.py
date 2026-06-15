#!/usr/bin/env python3
"""Heimdall demo web console — a real-time dashboard for the live demo.

Dependency-free (stdlib only: http.server, urllib, json, threading). Serves a
single-page dashboard from which you can launch every demo step (health, score,
load burst, fraud-ring injection, or the full scripted sequence) and watch the
status of each transaction — plus rolling analysis metrics — stream in live.

It reuses the scoring helpers in ``demo_client.py`` (same directory) so the web
console and the CLI (`scripts/demo.sh`) exercise the *exact* same code paths and
the deployed scoring API behind Azure Front Door.

Run:
    ./scripts/demo-web.sh                 # then open http://127.0.0.1:8800
    python3 scripts/demo_web.py --port 8800 --host 127.0.0.1
    python3 scripts/demo_web.py --scoring-host my.host.azurefd.net

Transport: each demo run streams Server-Sent Events (text/event-stream) so the
browser updates with zero polling and no external JS libraries.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# Reuse the battle-tested CLI demo helpers (same directory).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import demo_client as dc  # noqa: E402  (path set above)
import demo_scenarios as ds  # noqa: E402  curated decision-spectrum scenarios

# Resolved once at startup; overridable via --scoring-host / SCORING_FRONTDOOR_HOST.
SCORING_HOST = ""


# --------------------------------------------------------------------------- #
# Streaming demo runners — each yields (event_name, data_dict) tuples.
# --------------------------------------------------------------------------- #
def _emit(_event: str, **data):
    return _event, data


def run_health(_params):
    yield _emit("phase", name="health", label="Health & readiness probes")
    all_ok = True
    for path in ("/healthz", "/readyz"):
        status, body = dc.get(SCORING_HOST, path)
        ok = status == 200
        all_ok = all_ok and ok
        yield _emit("health", path=path, status=status, ok=ok, body=body[:200])
    yield _emit("log", level="info" if all_ok else "error",
                text=f"Health {'OK' if all_ok else 'FAILED'} for https://{SCORING_HOST}")


def _tx_event(tx, ok, status, body, elapsed, phase):
    """Normalise a scored transaction into a dashboard event payload."""
    if ok and isinstance(body, dict):
        return _emit(
            "tx",
            phase=phase,
            transaction_id=tx["transaction_id"],
            card_id=tx["card_id"],
            merchant_id=tx["merchant_id"],
            amount=tx["amount"],
            currency=tx["currency"],
            country=tx["country"],
            channel=tx["channel"],
            decision=body.get("decision"),
            score=body.get("score"),
            reason_codes=body.get("reason_codes", []),
            psd2_exemption=body.get("psd2_exemption"),
            server_latency_ms=body.get("latency_ms"),
            client_rtt_ms=round(elapsed, 1),
            explain=body.get("explain"),
            ok=True,
        )
    return _emit(
        "tx",
        phase=phase,
        transaction_id=tx.get("transaction_id"),
        card_id=tx.get("card_id"),
        merchant_id=tx.get("merchant_id"),
        amount=tx.get("amount"),
        currency=tx.get("currency"),
        country=tx.get("country"),
        channel=tx.get("channel"),
        decision="ERROR",
        ok=False,
        status=status,
        error=str(body)[:200],
        client_rtt_ms=round(elapsed, 1),
    )


def run_score(params):
    profile = (params.get("profile", ["normal"])[0]) or "normal"
    yield _emit("phase", name="score", label=f"Single '{profile}' transaction (explain)")
    tx = dc.make_tx(profile)
    ok, status, body, elapsed = dc.post_score(SCORING_HOST, tx, explain=True)
    yield _tx_event(tx, ok, status, body, elapsed, phase="score")
    if ok and isinstance(body, dict):
        yield _emit("log", level="info",
                    text=(f"decision={body['decision']} score={body['score']:.4f} "
                          f"exemption={body['psd2_exemption']} "
                          f"server={body['latency_ms']}ms rtt={elapsed:.1f}ms"))
    else:
        yield _emit("log", level="error", text=f"score failed {status}: {str(body)[:160]}")


def run_load(params):
    tps = int(params.get("tps", ["200"])[0])
    duration = int(params.get("duration", ["5"])[0])
    max_total = int(params.get("max", ["1000"])[0])
    workers = int(params.get("workers", ["20"])[0])
    profile = (params.get("profile", ["normal"])[0]) or "normal"
    target = tps * duration
    total = min(target, max_total)
    workers = min(workers, max(1, total))
    yield _emit("phase", name="load",
                label=f"Load burst — target {tps} TPS x {duration}s ({total} req, {workers} workers)")
    yield _emit("log", level="info",
                text=f"Sending representative burst of {total} requests ({workers} workers)…")

    # Stream each result as it completes for a real-time feel. We bound the live
    # tx feed to keep the browser snappy, but every request still counts toward metrics.
    results_q: queue.Queue = queue.Queue()
    emit_detail_cap = 300  # cap individual tx rows streamed to the UI
    t0 = time.perf_counter()

    def _worker(_i):
        tx = dc.make_tx(profile)
        ok, status, body, elapsed = dc.post_score(SCORING_HOST, tx)
        results_q.put((tx, ok, status, body, elapsed))

    pool = ThreadPoolExecutor(max_workers=workers)
    for i in range(total):
        pool.submit(_worker, i)

    done = 0
    detailed = 0
    while done < total:
        tx, ok, status, body, elapsed = results_q.get()
        done += 1
        if detailed < emit_detail_cap:
            detailed += 1
            yield _tx_event(tx, ok, status, body, elapsed, phase="load")
        else:
            # Still surface aggregate-only progress for the remaining volume.
            decision = body.get("decision") if (ok and isinstance(body, dict)) else "ERROR"
            score = body.get("score") if (ok and isinstance(body, dict)) else None
            yield _emit("tx_agg", phase="load", ok=bool(ok),
                        decision=decision, score=score,
                        client_rtt_ms=round(elapsed, 1))
        if done % max(1, total // 50) == 0 or done == total:
            yield _emit("progress", done=done, total=total,
                        elapsed_s=round(time.perf_counter() - t0, 2))
    pool.shutdown(wait=True)
    wall = time.perf_counter() - t0
    yield _emit("log", level="info",
                text=f"Load complete: {total} requests in {wall:.1f}s "
                     f"(~{(total / wall) if wall else 0:.0f} TPS achieved client-side)")


def run_inject(params):
    cards_n = int(params.get("cards", ["10"])[0])
    merchants_n = int(params.get("merchants", ["3"])[0])
    yield _emit("phase", name="inject",
                label=f"Fraud-ring injection — {cards_n} cards x {merchants_n} merchants (circular)")
    cards = [f"ring-card-{i:02d}" for i in range(cards_n)]
    merchants = [f"ring-mer-{i:02d}" for i in range(merchants_n)]
    for i, card in enumerate(cards):
        merchant = merchants[i % len(merchants)]
        tx = dc.make_tx(
            "high",
            transaction_id=f"ring-{int(time.time())}-{i}",
            card_id=card,
            merchant_id=merchant,
            amount=round(dc.random.uniform(3000, 6000), 2),
            currency="EUR",
            country="SE",
            channel="ECOM",
        )
        ok, status, body, elapsed = dc.post_score(SCORING_HOST, tx)
        yield _tx_event(tx, ok, status, body, elapsed, phase="inject")
        yield _emit("ring_edge", card=card, merchant=merchant)
    yield _emit("log", level="info",
                text="Ring injected. The closed circular value-flow is what the offline GNN on "
                     "Fabric Spark flags as a ring; the in-line scorer sees per-tx features only.")


def run_scenario(params):
    """Walk the curated decision spectrum (APPROVE / SCA / DECLINE) using the
    production decision rules (ported in demo_scenarios.py), with feature-enriched
    transactions, so the demo can show declines and false-positive handling that
    the stubbed live endpoint cannot currently produce on its own."""
    yield _emit("phase", name="scenario",
                label="Decision scenarios — approve · step-up (false positive) · decline")
    yield _emit("log", level="info",
                text="Decision engine = production rules (psd2_optimizer + scoring) over "
                     "enriched demo features. Watch the full outcome spectrum + handling.")
    pause = float(params.get("pause", ["0.9"])[0] or 0.9)
    for sc in ds.SCENARIOS:
        r = ds.evaluate(sc)
        yield _emit("log", level="info", text=f"▸ {sc.title}: {sc.narrative}")
        yield _emit(
            "tx",
            phase="scenario",
            scenario=sc.title,
            narrative=sc.narrative,
            handling=sc.handling,
            transaction_id=sc.key,
            card_id=sc.card.card_id,
            merchant_id=sc.merchant.merchant_id,
            amount=sc.amount,
            currency=sc.currency,
            country=sc.country,
            channel=sc.channel,
            decision=r["decision"],
            score=r["score"],
            reason_codes=r["reason_codes"],
            psd2_exemption=r["psd2_exemption"],
            ok=True,
        )
        level = "error" if r["decision"] == "DECLINE" else "info"
        yield _emit("log", level=level,
                    text=f"   → {r['decision']} (score {r['score']:.2f}, "
                         f"exemption {r['psd2_exemption']}). {sc.handling}")
        # Show that a genuine customer flagged as a potential false positive clears
        # the SCA challenge and the payment is ultimately approved.
        if sc.recovers_after_sca and r["decision"] == "SCA":
            time.sleep(pause)
            yield _emit(
                "tx",
                phase="scenario",
                scenario=sc.title + " — after 3-D Secure",
                handling="Customer completed Strong Customer Authentication; the payment was "
                         "re-authorised and approved. False positive avoided.",
                transaction_id=sc.key + "-reauth",
                card_id=sc.card.card_id,
                merchant_id=sc.merchant.merchant_id,
                amount=sc.amount,
                currency=sc.currency,
                country=sc.country,
                channel=sc.channel,
                decision="APPROVE",
                score=r["score"],
                reason_codes=["SCA_AUTHENTICATED", "FALSE_POSITIVE_RECOVERED"],
                psd2_exemption="NONE",
                ok=True,
            )
            yield _emit("log", level="info",
                        text="   ✓ 3-D Secure passed → APPROVED (genuine customer not lost).")
        time.sleep(pause)
    tally = ds.scenario_summary()
    yield _emit("log", level="info",
                text=f"Scenario tally — APPROVE={tally.get('APPROVE',0)} "
                     f"SCA={tally.get('SCA',0)} DECLINE={tally.get('DECLINE',0)} "
                     f"(plus false-positive recoveries).")


def run_all(params):
    yield _emit("log", level="info", text="### HEIMDALL LIVE DEMO — full sequence ###")
    yield from run_health(params)
    yield from run_score({"profile": ["normal"]})
    yield from run_score({"profile": ["high"]})
    yield from run_scenario(params)
    yield from run_load({
        "tps": params.get("tps", ["200"]),
        "duration": params.get("duration", ["5"]),
        "max": params.get("max", ["600"]),
        "workers": params.get("workers", ["20"]),
        "profile": ["normal"],
    })
    yield from run_inject({
        "cards": params.get("cards", ["10"]),
        "merchants": params.get("merchants", ["3"]),
    })
    yield _emit("log", level="info", text="### DEMO COMPLETE ###")


RUNNERS = {
    "health": run_health,
    "score": run_score,
    "scenario": run_scenario,
    "load": run_load,
    "inject": run_inject,
    "all": run_all,
}


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "HeimdallDemoConsole/1.0"

    def log_message(self, fmt, *args):  # quieter console
        sys.stderr.write("  [web] " + (fmt % args) + "\n")

    def _send_html(self, body: str):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj, status=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        params = parse_qs(parsed.query)

        if route in ("/", "/index.html"):
            return self._send_html(INDEX_HTML)
        if route == "/api/config":
            return self._send_json({
                "scoring_host": SCORING_HOST,
                "actions": list(RUNNERS.keys()),
            })
        if route == "/api/stream":
            return self._stream(params)
        return self._send_json({"error": "not found", "path": route}, status=404)

    def _stream(self, params):
        action = (params.get("action", ["health"])[0])
        runner = RUNNERS.get(action)
        if runner is None:
            return self._send_json({"error": f"unknown action '{action}'"}, status=400)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def write_event(name, data):
            payload = f"event: {name}\ndata: {json.dumps(data)}\n\n"
            self.wfile.write(payload.encode("utf-8"))
            self.wfile.flush()

        try:
            write_event("start", {"action": action, "scoring_host": SCORING_HOST,
                                  "ts": time.time()})
            for name, data in runner(params):
                write_event(name, data)
            write_event("end", {"action": action, "ts": time.time()})
        except (BrokenPipeError, ConnectionResetError):
            pass  # client navigated away / closed the tab
        except Exception as exc:  # noqa: BLE001  surface runtime errors to the UI
            try:
                write_event("log", {"level": "error", "text": f"server error: {exc}"})
                write_event("end", {"action": action, "error": str(exc)})
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Single-page dashboard (embedded; no external assets so it runs fully offline).
# --------------------------------------------------------------------------- #
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Heimdall — Live Demo Console</title>
<style>
  :root{
    --navy:#0E2A47; --blue:#1F8FE5; --teal:#3DD6C4; --ink:#04111F;
    --mist:#EAF6FF; --deep:#1F4E78;
    --approve:#3DD6C4; --sca:#F2B441; --decline:#FF5C72; --error:#9aa7b4;
    --panel:#10243d; --panel2:#0c1c30; --line:#1d3a5c; --txt:#dbe9f7;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:Inter,"Segoe UI",system-ui,sans-serif;background:
    radial-gradient(1200px 600px at 80% -10%, #14365a 0%, transparent 60%), var(--ink);
    color:var(--txt);}
  header{display:flex;align-items:center;gap:14px;padding:16px 22px;
    background:linear-gradient(90deg,#3DD6C4 0%,#1F8FE5 45%,#1F4E78 100%);
    color:#fff;box-shadow:0 2px 18px rgba(0,0,0,.4)}
  header .shield{font-size:26px}
  header h1{font-size:19px;margin:0;font-weight:700;letter-spacing:.3px}
  header .sub{font-size:12px;opacity:.9;margin-top:2px}
  header .host{margin-left:auto;font-size:12px;background:rgba(0,0,0,.25);
    padding:6px 12px;border-radius:20px;font-family:ui-monospace,Menlo,monospace}
  .wrap{display:grid;grid-template-columns:330px 1fr;gap:16px;padding:16px 22px;max-width:1500px}
  @media(max-width:1050px){.wrap{grid-template-columns:1fr}}
  .card{background:linear-gradient(180deg,var(--panel) 0%,var(--panel2) 100%);
    border:1px solid var(--line);border-radius:12px;padding:16px;
    box-shadow:0 6px 22px rgba(0,0,0,.25)}
  .card h2{font-size:12px;text-transform:uppercase;letter-spacing:1.2px;
    color:#7fb6e6;margin:0 0 12px}
  /* Controls */
  .btn{display:block;width:100%;border:0;border-radius:9px;padding:11px 14px;margin:7px 0;
    font-size:14px;font-weight:600;cursor:pointer;color:#fff;text-align:left;
    background:#173354;border:1px solid #244a73;transition:.15s;display:flex;
    align-items:center;gap:10px}
  .btn:hover{background:#1d4470;transform:translateY(-1px)}
  .btn:disabled{opacity:.5;cursor:not-allowed;transform:none}
  .btn.primary{background:linear-gradient(90deg,#1F8FE5,#3DD6C4);border:0;color:#04111F}
  .btn .ic{font-size:16px}
  .params{margin:8px 0 4px;padding:10px;background:#0b1c30;border-radius:8px;border:1px solid #1b3550}
  .params label{display:flex;justify-content:space-between;align-items:center;
    font-size:12px;color:#9fc2e6;margin:6px 0}
  .params input,.params select{width:110px;background:#0e253d;border:1px solid #28507c;
    color:#fff;border-radius:6px;padding:4px 8px;font-size:12px}
  .pill{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700}
  .pill.on{background:var(--teal);color:#04111F}
  .pill.off{background:#3a4a5c;color:#cfe0f0}
  /* Metrics */
  .metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
  .metric{background:#0c1f36;border:1px solid var(--line);border-radius:10px;padding:10px 12px}
  .metric .v{font-size:22px;font-weight:800;line-height:1}
  .metric .l{font-size:10.5px;text-transform:uppercase;letter-spacing:.7px;color:#7fa8d0;margin-top:6px}
  .v.approve{color:var(--approve)} .v.sca{color:var(--sca)}
  .v.decline{color:var(--decline)} .v.error{color:var(--error)}
  /* decision bar */
  .mix{height:16px;border-radius:8px;overflow:hidden;display:flex;background:#0c1f36;margin-top:6px}
  .mix span{height:100%}
  .mix .a{background:var(--approve)} .mix .s{background:var(--sca)}
  .mix .d{background:var(--decline)} .mix .e{background:var(--error)}
  .legend{display:flex;gap:14px;font-size:11px;margin-top:8px;color:#9fc2e6;flex-wrap:wrap}
  .legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:middle}
  /* phase + progress */
  #phase{font-size:13px;color:#bcd6f2;min-height:18px}
  .bar{height:7px;background:#0c1f36;border-radius:6px;overflow:hidden;margin-top:8px}
  .bar>div{height:100%;width:0;background:linear-gradient(90deg,#1F8FE5,#3DD6C4);transition:width .2s}
  /* table */
  .feedwrap{max-height:46vh;overflow:auto;border-radius:8px;border:1px solid var(--line)}
  table{width:100%;border-collapse:collapse;font-size:12.5px}
  thead th{position:sticky;top:0;background:#0c2138;color:#7fb6e6;text-align:left;
    padding:8px 10px;font-weight:600;border-bottom:1px solid var(--line);z-index:1}
  tbody td{padding:7px 10px;border-bottom:1px solid #142c47;white-space:nowrap}
  tbody tr:hover{background:#102842}
  .tag{padding:2px 8px;border-radius:6px;font-weight:700;font-size:11px}
  .tag.APPROVE{background:rgba(61,214,196,.18);color:var(--teal)}
  .tag.SCA{background:rgba(242,180,65,.18);color:var(--sca)}
  .tag.DECLINE{background:rgba(255,92,114,.18);color:var(--decline)}
  .tag.ERROR{background:rgba(154,167,180,.2);color:var(--error)}
  .mono{font-family:ui-monospace,Menlo,monospace}
  .score{font-weight:700}
  .handling{color:#9fc2e6;font-size:11px;margin-top:3px;line-height:1.35;white-space:normal}
  .scn{display:inline-block;background:#143a5c;color:#aee0ff;border-radius:5px;
    padding:1px 7px;font-size:10.5px;font-weight:700;margin-bottom:3px}
  /* log */
  #log{height:150px;overflow:auto;background:#06121f;border:1px solid var(--line);
    border-radius:8px;padding:8px 10px;font-family:ui-monospace,Menlo,monospace;font-size:11.5px}
  #log .info{color:#9fd8ff} #log .error{color:#ff8b9c}
  .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
  .dot.ok{background:var(--teal)} .dot.bad{background:var(--decline)} .dot.idle{background:#3a4a5c}
  .health-row{display:flex;align-items:center;gap:8px;font-size:12.5px;margin:5px 0;font-family:ui-monospace,monospace}
  .right-col{display:flex;flex-direction:column;gap:16px}
  .muted{color:#6f8aa8;font-size:11px;margin-top:8px}
</style>
</head>
<body>
<header>
  <div class="shield">🛡️</div>
  <div>
    <h1>Heimdall — Live Demo Console</h1>
    <div class="sub">The watchful guardian of every transaction · real-time scoring &amp; ring detection</div>
  </div>
  <div class="host">scoring: <span id="host">…</span></div>
</header>

<div class="wrap">
  <!-- LEFT: controls -->
  <div class="card" style="align-self:start">
    <h2>Demo steps</h2>
    <button class="btn" data-action="health"><span class="ic">🩺</span>1 · Health &amp; readiness</button>

    <button class="btn" data-action="score" data-profile="normal"><span class="ic">✅</span>2 · Score normal transaction</button>
    <button class="btn" data-action="score" data-profile="high"><span class="ic">⚠️</span>3 · Score high-risk transaction</button>

    <div class="params">
      <label>TPS target <input id="tps" type="number" value="2000" min="1"></label>
      <label>Duration (s) <input id="duration" type="number" value="120" min="1"></label>
      <label>Max requests <input id="max" type="number" value="600" min="1"></label>
      <label>Workers <input id="workers" type="number" value="40" min="1"></label>
    </div>
    <button class="btn" data-action="load"><span class="ic">📈</span>4 · Run load burst</button>

    <div class="params">
      <label>Ring cards <input id="cards" type="number" value="10" min="2"></label>
      <label>Merchants <input id="merchants" type="number" value="3" min="1"></label>
    </div>
    <button class="btn" data-action="inject"><span class="ic">🕸️</span>5 · Inject fraud ring</button>

    <button class="btn" data-action="scenario"><span class="ic">⚖️</span>6 · Decision scenarios (approve / step-up / decline)</button>

    <button class="btn primary" data-action="all"><span class="ic">🚀</span>Run full demo (all steps)</button>

    <button class="btn" id="clearBtn" style="margin-top:14px"><span class="ic">🧹</span>Clear feed &amp; metrics</button>
    <div class="muted">Status: <span class="pill off" id="status">idle</span></div>
    <div class="muted" id="phase">Ready.</div>
    <div class="bar"><div id="progbar"></div></div>
  </div>

  <!-- RIGHT: metrics + feed -->
  <div class="right-col">
    <div class="card">
      <h2>Transaction analysis — live metrics</h2>
      <div class="metrics">
        <div class="metric"><div class="v" id="m_total">0</div><div class="l">Scored</div></div>
        <div class="metric"><div class="v approve" id="m_appr">0</div><div class="l">Approve</div></div>
        <div class="metric"><div class="v sca" id="m_sca">0</div><div class="l">Step-up (SCA)</div></div>
        <div class="metric"><div class="v decline" id="m_decl">0</div><div class="l">Decline</div></div>
        <div class="metric"><div class="v error" id="m_err">0</div><div class="l">Errors</div></div>
        <div class="metric"><div class="v" id="m_tps">0</div><div class="l">Client TPS</div></div>
        <div class="metric"><div class="v" id="m_p50">0<small style="font-size:11px"> ms</small></div><div class="l">RTT p50</div></div>
        <div class="metric"><div class="v" id="m_p99">0<small style="font-size:11px"> ms</small></div><div class="l">RTT p99</div></div>
      </div>
      <div class="mix" id="mix">
        <span class="a" style="width:0"></span><span class="s" style="width:0"></span>
        <span class="d" style="width:0"></span><span class="e" style="width:0"></span>
      </div>
      <div class="legend">
        <span><i style="background:var(--approve)"></i>Approve</span>
        <span><i style="background:var(--sca)"></i>SCA</span>
        <span><i style="background:var(--decline)"></i>Decline</span>
        <span><i style="background:var(--error)"></i>Error</span>
        <span style="margin-left:auto">avg score <b id="m_avg" class="mono">0.000</b></span>
      </div>
      <div class="health-row" id="health-box" style="margin-top:12px">
        <span><span class="dot idle" id="h_healthz"></span>/healthz</span>
        <span><span class="dot idle" id="h_readyz"></span>/readyz</span>
      </div>
    </div>

    <div class="card">
      <h2>Transaction feed <span id="feedcount" class="muted"></span></h2>
      <div class="feedwrap">
        <table>
          <thead><tr>
            <th>Time</th><th>Transaction</th><th>Card → Merchant</th><th>Amount</th>
            <th>Country</th><th>Decision</th><th>Score</th><th>RTT</th><th>Reasons / handling</th>
          </tr></thead>
          <tbody id="feed"></tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h2>Event log</h2>
      <div id="log"></div>
    </div>
  </div>
</div>

<script>
const $ = (id)=>document.getElementById(id);
let es = null;
let M = newMetrics();
let rtts = [];
let loadStart = 0, loadActive = false;

function newMetrics(){return {total:0,approve:0,sca:0,decline:0,error:0,scoreSum:0,scoreN:0};}

function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}

fetch('/api/config').then(r=>r.json()).then(c=>{ $('host').textContent = c.scoring_host || 'unknown'; });

function pct(arr,p){ if(!arr.length) return 0; const s=[...arr].sort((a,b)=>a-b);
  const k=Math.max(0,Math.min(s.length-1,Math.round((p/100)*(s.length-1)))); return s[k]; }

function setStatus(on,label){ const el=$('status'); el.textContent=label;
  el.className='pill '+(on?'on':'off'); }

function renderMetrics(){
  $('m_total').textContent=M.total;
  $('m_appr').textContent=M.approve;
  $('m_sca').textContent=M.sca;
  $('m_decl').textContent=M.decline;
  $('m_err').textContent=M.error;
  $('m_p50').innerHTML=pct(rtts,50).toFixed(0)+'<small style="font-size:11px"> ms</small>';
  $('m_p99').innerHTML=pct(rtts,99).toFixed(0)+'<small style="font-size:11px"> ms</small>';
  $('m_avg').textContent=(M.scoreN? (M.scoreSum/M.scoreN):0).toFixed(3);
  const denom=Math.max(1,M.approve+M.sca+M.decline+M.error);
  const mix=$('mix').children;
  mix[0].style.width=(100*M.approve/denom)+'%';
  mix[1].style.width=(100*M.sca/denom)+'%';
  mix[2].style.width=(100*M.decline/denom)+'%';
  mix[3].style.width=(100*M.error/denom)+'%';
  if(loadActive){ const el=(performance.now()-loadStart)/1000;
    $('m_tps').textContent= el>0 ? Math.round((M.total)/el) : 0; }
}

function countDecision(d,ok){
  M.total++;
  if(!ok || d==='ERROR'){M.error++; return;}
  if(d==='APPROVE')M.approve++; else if(d==='SCA')M.sca++; else if(d==='DECLINE')M.decline++;
}

function addRow(d){
  countDecision(d.decision, d.ok);
  if(typeof d.client_rtt_ms==='number') rtts.push(d.client_rtt_ms);
  if(typeof d.score==='number'){M.scoreSum+=d.score; M.scoreN++;}
  const feed=$('feed');
  const tr=document.createElement('tr');
  const t=new Date().toLocaleTimeString();
  const dec=d.decision||'ERROR';
  const score=(typeof d.score==='number')? d.score.toFixed(3): (d.ok?'':'—');
  const reasonsArr=(d.reason_codes&&d.reason_codes.length)? d.reason_codes.slice(): [];
  if(d.psd2_exemption && d.psd2_exemption!=='NONE') reasonsArr.push('exempt:'+d.psd2_exemption);
  const reasons=reasonsArr.length? reasonsArr.join(', '): (d.error? d.error : '');
  const handling = d.handling? `<div class="handling">↳ ${esc(d.handling)}</div>`: '';
  const scenarioTag = d.scenario? `<span class="scn">${esc(d.scenario)}</span> `: '';
  tr.innerHTML=`<td class="mono">${t}</td>
    <td class="mono">${esc(d.transaction_id||'')}</td>
    <td class="mono">${esc(d.card_id||'')} → ${esc(d.merchant_id||'')}</td>
    <td class="mono">${esc(d.currency||'')} ${typeof d.amount==='number'? d.amount.toLocaleString():''}</td>
    <td>${esc(d.country||'')}</td>
    <td><span class="tag ${dec}">${dec}</span></td>
    <td class="score">${score}</td>
    <td class="mono">${typeof d.client_rtt_ms==='number'? d.client_rtt_ms.toFixed(0)+'ms':''}</td>
    <td style="max-width:340px;white-space:normal">${scenarioTag}<span class="mono">${esc(reasons)}</span>${handling}</td>`;
  feed.insertBefore(tr,feed.firstChild);
  while(feed.children.length>250) feed.removeChild(feed.lastChild);
  $('feedcount').textContent='('+feed.children.length+' shown)';
}

function logLine(level,text){
  const log=$('log'); const div=document.createElement('div');
  div.className=level||'info'; div.textContent='› '+text;
  log.insertBefore(div,log.firstChild);
  while(log.children.length>200) log.removeChild(log.lastChild);
}

function setHealth(path,ok){
  const id = path==='/healthz'?'h_healthz': path==='/readyz'?'h_readyz':null;
  if(id) $(id).className='dot '+(ok?'ok':'bad');
}

function disableButtons(dis){
  document.querySelectorAll('.btn[data-action]').forEach(b=>b.disabled=dis);
}

function run(action,opts){
  if(es){ es.close(); }
  opts=opts||{};
  const q=new URLSearchParams({action});
  if(action==='score') q.set('profile',opts.profile||'normal');
  if(action==='load'||action==='all'){
    q.set('tps',$('tps').value); q.set('duration',$('duration').value);
    q.set('max',$('max').value); q.set('workers',$('workers').value);
  }
  if(action==='inject'||action==='all'){
    q.set('cards',$('cards').value); q.set('merchants',$('merchants').value);
  }
  if(action==='load'||action==='all'){ loadStart=performance.now(); loadActive=true; }
  disableButtons(true); setStatus(true,'running: '+action);
  $('progbar').style.width='0%';

  es=new EventSource('/api/stream?'+q.toString());
  es.addEventListener('start',e=>{ logLine('info','▶ start '+JSON.parse(e.data).action); });
  es.addEventListener('phase',e=>{ const d=JSON.parse(e.data); $('phase').textContent='● '+d.label; logLine('info',d.label); });
  es.addEventListener('health',e=>{ const d=JSON.parse(e.data);
    setHealth(d.path,d.ok); logLine(d.ok?'info':'error',`${d.path} → ${d.status} ${d.body}`); });
  es.addEventListener('tx',e=>{ addRow(JSON.parse(e.data)); renderMetrics(); });
  es.addEventListener('tx_agg',e=>{ const d=JSON.parse(e.data);
    countDecision(d.decision,d.ok); if(typeof d.client_rtt_ms==='number')rtts.push(d.client_rtt_ms);
    if(typeof d.score==='number'){M.scoreSum+=d.score;M.scoreN++;} renderMetrics(); });
  es.addEventListener('progress',e=>{ const d=JSON.parse(e.data);
    $('progbar').style.width=(100*d.done/d.total)+'%';
    $('phase').textContent=`● ${d.done}/${d.total} processed (${d.elapsed_s}s)`; });
  es.addEventListener('log',e=>{ const d=JSON.parse(e.data); logLine(d.level,d.text); });
  es.addEventListener('ring_edge',e=>{});
  es.addEventListener('end',e=>{ finish(); });
  es.onerror=()=>{ finish(); };
}

function finish(){
  if(es){ es.close(); es=null; }
  loadActive=false; disableButtons(false); setStatus(false,'idle');
  $('progbar').style.width='100%'; renderMetrics();
  setTimeout(()=>{ if(!es) $('progbar').style.width='0%'; },800);
}

document.querySelectorAll('.btn[data-action]').forEach(b=>{
  b.addEventListener('click',()=>run(b.dataset.action,{profile:b.dataset.profile}));
});
$('clearBtn').addEventListener('click',()=>{
  M=newMetrics(); rtts=[]; $('feed').innerHTML=''; $('log').innerHTML='';
  $('feedcount').textContent=''; ['h_healthz','h_readyz'].forEach(i=>$(i).className='dot idle');
  $('m_tps').textContent='0'; renderMetrics(); $('phase').textContent='Cleared.';
});
renderMetrics();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    global SCORING_HOST
    p = argparse.ArgumentParser(description="Heimdall demo web console")
    p.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=8800, help="Bind port (default 8800)")
    p.add_argument("--scoring-host", default=None,
                   help="Scoring host (default: from SCORING_FRONTDOOR_HOST / .env.deployed)")
    args = p.parse_args(argv)

    SCORING_HOST = dc.load_host(args.scoring_host)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print("=" * 64)
    print("  🛡️  Heimdall — Live Demo Console")
    print(f"     scoring API : https://{SCORING_HOST}")
    print(f"     dashboard   : {url}")
    print("     press Ctrl+C to stop")
    print("=" * 64)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  shutting down…")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
