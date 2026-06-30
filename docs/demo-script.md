# Capstone Demo Script — 10 minutes

> **Purpose.** A tightly choreographed 10-minute live demo that runs inside the 45-minute capstone presentation, showing the platform handling load, catching a fraud ring, driving the agentic case workflow, and producing the EBA report.

---

## ▶️ Runnable terminal demo (no dashboards required)

The commands below are **real and verified** against the live Sweden Central deployment.
They drive the scoring API over Azure Front Door using `scripts/demo.sh`
(pure `python3` + stdlib — **no `curl`/`jq` needed**; host is read from `.env.deployed`).

```bash
# Verify health (GET /healthz + /readyz)
./scripts/demo.sh health

# Score one transaction with per-stage timings
./scripts/demo.sh score --profile normal      # → APPROVE
./scripts/demo.sh score --profile high         # high-amount/foreign/MOTO contrast

# Representative load burst (capped for a laptop; raise --max/--workers for more)
./scripts/demo.sh load --tps 2000 --duration 120 --max 600 --workers 40

# Inject a circular fraud-ring (10 cards / 3 merchants)
./scripts/demo.sh inject --pattern ring --cards 10 --merchants 3

# Decision spectrum — APPROVE (frictionless) / SCA step-up (false-positive handling) / DECLINE (fraud)
./scripts/demo.sh scenario

# One-shot scripted sequence (health → baseline → scenarios → load → ring)
./scripts/demo.sh all
```

> **Live decisions now span the full spectrum — driven by the real model.** The
> deployed scoring API runs the trained **stacked ensemble** (XGBoost + LightGBM +
> Logistic regression, exported to ONNX by `ml/train_ensemble.py`, served in-process,
> `model_version = v1.0.0-ensemble`). The model learned that high-value
> card-not-present purchases in the small hours are high risk, so the demo profiles
> drive the spectrum with transaction amount + time-of-day, and the policy layer
> (`psd2_optimizer.py`) maps the score to a decision:
>  - `score --profile normal`  → APPROVE (daytime, low value → model score ~0.00)
>  - `score --profile sca`     → SCA step-up (00:00-01:59, ~€330-350 → model score ~0.41)
>  - `score --profile decline` → DECLINE (00:00-01:59, €450+ → model score ~0.99)
>  - `score --profile blocked` → DECLINE (seeded blocked card, hard policy rule)
>  - `load --profile mix`      → a realistic ~75/15/10 APPROVE/SCA/DECLINE stream
>
> A small set of curated entities is also seeded into the in-memory feature store
> (`SEED_DEMO_FEATURES=true`, see `services/scoring-api/app/seed_data.py`) so the
> blocked-card policy rule and PSD2 exemptions have data to act on.
>
> The `scenario` step additionally walks a curated narrative spectrum via the
> dependency-free port of `psd2_optimizer.py` + `scoring.py` in `scripts/demo_scenarios.py`,
> showing frictionless approvals (PSD2 low-value/TRA exemptions), **SCA step-up for
> borderline / potential false positives** (challenged, not blocked — genuine customers
> clear 3-D Secure and the payment proceeds), and hard **DECLINE** for confirmed fraud
> (blocked card, fraud-ring cash-out → an agentic case is opened).

> On the WSL host used for development, invoke with `/bin/bash scripts/demo.sh …`
> and `export PATH="$HOME/snap/copilot-cli/common/local/bin:$PATH"` for `az`.

---

## 🖥️ Web demo console (launch steps + live transaction dashboard)

For a presenter-friendly alternative to the terminal, `scripts/demo-web.sh` serves a
single-page **web console** (also pure `python3` + stdlib — no pip installs, no
`curl`/`jq`). It exposes a button for every demo step and streams the **status of each
transaction and the live analysis metrics** (decision mix, approve/SCA/decline counts,
client RTT p50/p99, achieved TPS, average risk score) into the browser in real time via
Server-Sent Events. It reuses the exact same scoring code path as `demo.sh`.

```bash
# Start the console, then open the printed URL (default http://127.0.0.1:8800)
./scripts/demo-web.sh
./scripts/demo-web.sh --port 9000            # custom port
./scripts/demo-web.sh --host 0.0.0.0         # expose on the LAN (e.g. for a 2nd screen)
./scripts/demo-web.sh --scoring-host my.host.azurefd.net   # override target
```

From the dashboard you can:
- **1 · Health & readiness** — live `/healthz` + `/readyz` indicators.
- **2 · Score normal** / **3 · Score high-risk** — single transactions with per-stage timings.
- **4 · Load burst** — adjustable TPS / duration / max / workers; watch the feed + metrics fill live.
- **5 · Inject fraud ring** — adjustable cards × merchants circular value-flow.
- **6 · Decision scenarios** — the full **APPROVE / SCA step-up (false-positive handling) / DECLINE** spectrum, with the handling explained per transaction (uses the production decision rules — see the note above).
- **🚀 Run full demo** — the whole `health → baseline → scenarios → load → ring` sequence end-to-end.

The header also links to **📊 Ops dashboard** (`/ops`) — a management-grade
operational view that auto-refreshes every 2 s: throughput (TPS) with live
replica count and surge detection, scoring p99 vs. the < 18 ms SLO, 30-day
availability, decision mix (approve / SCA / decline), fraud caught today,
false-positive rate, detection quality (AUC / precision / recall), the HITL
queue, drift status and the next EBA report. It mirrors the Power BI executive
dashboard and is the same view summarised on the "Operations dashboard" briefing
slide. JSON is available at `/api/ops` for embedding elsewhere.

> WSL host: `/bin/bash scripts/demo-web.sh`. The console binds to `127.0.0.1` by default;
> use `--host 0.0.0.0` only on a trusted network. Stop with `Ctrl+C`.


The dashboard-driven narrative below is the **full 45-minute stage version**; the
Power BI / Grafana / Fabric / agentic-console pieces require their own provisioning
and are **not** reproduced by the CLI demo above (which exercises the live scoring path).

---

**Pre-flight (do before the session starts, not on stage):**
- `./scripts/deploy.sh` is already complete; both regions show green in Grafana.
- `services/transaction-simulator` container image pre-pulled on the demo host.
- Power BI workspace pinned in browser tab 1; Grafana SLO dashboard in tab 2; agentic console in tab 3; Fabric notebook in tab 4 (only opened if asked).
- Demo timer visible.

**Verified live URLs (Sweden Central, prod):**
- **Scoring API** (Phases 1–3, via Front Door): `https://scoring-prod-dpbebwgrfud2egd2.b01.azurefd.net` — `/healthz` + `/readyz` return 200. The scorer runs the **stub** model over a **seeded feature store** (`SEED_DEMO_FEATURES=true`), so live requests return real APPROVE / SCA / DECLINE decisions (see the `score`/`load` profiles above).
- **Agentic console** (Phase 4): `https://ca-orchestrator-prod-swc.purpleforest-f993111a.swedencentral.azurecontainerapps.io` — direct Container Apps FQDN (external ingress); `/healthz` 200, `/v1/agents` lists the 5 agents. Use this URL on stage. _Note: the Front Door console endpoint (`console-prod-…b01.azurefd.net`) currently returns an AFD 404 (edge route not serving) — use the direct FQDN above instead._

---

## Phase 1 — Idle dashboard (0:00 → 2:00)

**Show**: Power BI **Operations** page.

Talk track:
> "What you're seeing is real production traffic shape, replayed at 1× speed. We're scoring around 1 200 transactions per second across SE/NO/DK/FI/EE. p99 latency is **11 ms** end-to-end on the green tile. Decline rate sits at **1.1 %**, down from 2.8 % pre-launch. SCA exemption coverage is at **73 %**, mostly TRA. Notice the rolling fraud rate per band — all comfortably under our internal 30 %-below-EBA-cap triggers."

Hover the tiles: TPS, p99, decline %, exemption mix, fraud rate per band.

---

## Phase 2 — Load to 2 000 TPS (2:00 → 4:00)

**Action**: from terminal:
```bash
./scripts/demo.sh load --tps 2000 --duration 120 --max 600 --workers 40
```
This drives `scripts/demo_client.py` against the Sweden Central AFD endpoint (circular flow is built-in).

**Show**: Grafana **Scoring API SLO** dashboard (`/d/heimdall-scoring-slo`) — replicas scale from 6 to ~22, p99 stays **under 18 ms** (typically 13–15 ms).

Talk track:
> "I've doubled the load. KEDA on Container Apps scales out the Dedicated D8 workload profile in under 30 seconds — you can see the replica count climb. p99 is holding at **14 ms** because the scorer is **ONNX in-process** — there is no separate model server in the hot path. Cosmos multi-master takes the writes locally; the cold path is async to Event Hubs."

Switch to Power BI live page — the TPS tile updates within ~5 s.

---

## Phase 3 — Fraud-ring injection (4:00 → 7:00)

**Action**:
```bash
./scripts/demo.sh inject --pattern ring --cards 10 --merchants 3
```
This emits 10 cards across 3 merchants in a circular flow.

**Show**:
- **Fraud-ring entity graph** (demo console → `/graph`): the Card · Merchant · Device · Country · IP neighbourhood, with the shared device + merchant edges highlighted in red and the anomaly score (0.91).
- Grafana panel "GNN ring score" spikes.
- Power BI **Risk** page → "Active rings" tile increments to 1; map highlights SE-DK corridor.
- Sentinel incident appears (severity HIGH).

Talk track:
> "This is a textbook ring: ten cards, three merchants, circular value flow. The 1-hop graph features the scorer pulls from Cosmos Gremlin already nudge each individual transaction up by ~0.2 in score, but the **offline GNN** running on Fabric Spark catches the *topology* — the closed loop — and emits a ring alert. Sentinel correlates and opens a HIGH-severity incident."

---

## Phase 4 — Agentic console (7:00 → 9:00)

**Show**: agentic console UI (browser tab 3) — the new case is at the top.

Click into the case. The Semantic Kernel Process Framework state graph animates each agent transition:

1. **TriageAgent** (gpt-4o-mini) — "Severity: HIGH. Pattern: circular merchant ring. 10 cards involved."
2. **GraphAnalystAgent** (gpt-4o) — "Confirmed circular flow, depth 3, value €47 200, time-window 6 min. Merchant cluster previously associated with case CR-2024-0918."
3. **PolicyAgent** (gpt-4o) — "PSD2 SCA: TRA was applied on 7/10. Within rolling-fraud guard. AML threshold for SAR met (FATF + national). Recommend: SAR draft + freeze + EBA tagging."
4. **CaseManagerAgent** — opens case `CR-2025-Q3-00412`; freezes all 10 PAN-tokens; notifies issuer.
5. **NarrativeAgent** (gpt-4o-mini) — produces a SAR narrative pre-filled with the graph evidence.

Talk track:
> "Every agent step is logged to an append-only Cosmos container plus immutable Storage — that's our **EU AI Act Article 12** record. The PolicyAgent has a hard rule that any decline of significant amount needs human review — that's our **Article 22 GDPR** safeguard. The reviewer signs the SAR; the agent never submits unilaterally."

---

## Phase 5 — EBA report (9:00 → 10:00)

**Show**: Power BI **EBA Q-Report** workspace → open the Q1 paginated report.

Scroll: Tables 1A–1D (issuer cards), 2A–2D (acquirer cards), 3A (SCT), 4A (e-money). Show the **fraud rate per TRA band** sub-page — all bands comfortably below the EBA caps.

Talk track:
> "This is the same Q1 file the Risk team submitted to Finansinspektionen last week, generated automatically from Fabric Gold. Zero manual hours — down from 320 per quarter. Lineage from this PDF back to the raw `tx.raw` topic is one click in Purview. The PDF and the XBRL are archived to immutable storage with WORM seven years."

End on the **Outcomes vs targets** slide — fraud loss −41 %, decline 1.1 %, p99 14 ms, EBA hours 0, exemption 73 %, availability 99.99 %.

---

## Recovery cues (if something fails on stage)

- **Load test refuses to start** → fall back to a smaller burst `./scripts/demo.sh load --tps 200 --duration 10 --max 100`, or repeated `./scripts/demo.sh score --profile high`.
- **Power BI Direct Lake stale** → switch to the cached "Operations (snapshot)" page.
- **Agentic console hung** → open the pre-rendered walk-through under `slides/notes/agentic-walkthrough.png`.

---

## TL;DR

Ten minutes: idle dashboard → 2 k TPS load with p99 holding under 18 ms → ring injection caught by GNN → five-agent SK workflow producing a SAR draft with full audit trail → automated EBA Q-report. Three terminal commands, four browser tabs, one timer.
