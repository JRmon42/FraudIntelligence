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

> **Live decisions now span the full spectrum — driven by the real model *and the
> fraud-ring GNN*.** The deployed scoring API runs the trained **stacked ensemble**
> (XGBoost + LightGBM + Logistic regression, exported to ONNX by
> `ml/train_ensemble.py`, served in-process, `model_version = v1.1.0-ensemble-gnn`).
> The ensemble consumes the **fraud-ring GNN**'s per-card features — `ring_score`
> plus a 16-dim GraphSAGE embedding (`ml/train_gnn.py`), published into the feature
> store by `ml/publish_gnn_features.py`. So a card the GNN flags as ring-linked is
> stepped up / declined even on an ordinary small-hours transaction, while the
> *identical* transaction on a random card is approved — the **GNN genuinely drives
> the live decision**. The policy layer (`psd2_optimizer.py`) maps the score to a
> decision:
>  - `score --profile normal`  → APPROVE (random card, daytime, low value)
>  - `score --profile sca`     → SCA step-up (GNN ring card, 02:00-03:59, €300-550)
>  - `score --profile decline` → DECLINE (GNN ring card, 00:00-01:59, €350-700)
>  - `score --profile blocked` → DECLINE (seeded blocked card, hard policy rule)
>  - `load --profile mix`      → a realistic ~75/15/10 APPROVE/SCA/DECLINE stream
>
> Run the same payload on a non-ring card to show it APPROVE: the only thing that
> changed is the GNN's verdict on the card.
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
- **2 · Score normal (APPROVE)** / **3 · Score GNN ring-linked card (SCA step-up)** / **4 · Score GNN ring-linked card (DECLINE)** — single transactions with per-stage timings, driven by the **real stacked ensemble + fraud-ring GNN** (see the note above).
- **4 · Load burst** — adjustable TPS / duration / max / workers; watch the feed + metrics fill live.
- **5 · Inject fraud ring** — adjustable cards × merchants circular value-flow; the injected ring is rendered on the **🕸️ Fraud-ring graph** (`/graph`) view.
- **6 · Simulate scale test (synthetic → /ops)** — a clearly-labelled **synthetic** burst (default 18 000 TPS for 8 s, no live API calls) that drives `/ops` to show the surge and autoscale to the **60-replica** ceiling. Because these samples carry no latency, the modelled scoring p99 stays honest.
- **6 · Decision scenarios** — the full **APPROVE / SCA step-up (false-positive handling) / DECLINE** spectrum, with the handling explained per transaction (uses the production decision rules — see the note above).
- **🚀 Run full demo** — the whole `health → baseline → scenarios → load → ring` sequence end-to-end.
- **🧹 Clear feed & metrics** — resets the live feed **and** the server-side `/ops` metrics, the `/graph` view and the agentic case panel.

**🤖 Agentic case panel.** On any **DECLINE** (a single score or the scenario
walk-through), the console opens a *real* fraud case on the deployed **6-agent
Semantic-Kernel orchestrator** — Triage → GraphAnalyst → Policy → Narrative →
CaseManager → Reflector, running on **live Azure OpenAI `gpt-4o-mini`**
(managed-identity auth) with **Cosmos** case persistence — and streams each
agent step plus the generated SAR narrative into a dedicated panel. Best-effort:
if the orchestrator is unreachable the demo continues uninterrupted.

The header also links to **📊 Ops dashboard** (`/ops`) and the **🕸️ Fraud-ring
graph** (`/graph`). `/ops` is a management-grade operational view that
auto-refreshes every 2 s: throughput (TPS) with live replica count and surge
detection, scoring p99 vs. the < 18 ms SLO, 30-day availability, decision mix
(approve / SCA / decline), fraud caught today, false-positive rate, detection
quality (AUC / precision / recall), the HITL queue, drift status and the next
EBA report — all reflecting the **real session activity** (the scale-test button
is the only synthetic feed). It mirrors the Power BI executive dashboard and is
the same view summarised on the "Operations dashboard" briefing slide. JSON is
available at `/api/ops` for embedding elsewhere. `/graph` renders the most
recent injected fraud ring (Card · Merchant · Device · Country · IP
neighbourhood) and auto-refreshes; JSON at `/api/graph`.

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
- **Scoring API** (Phases 1–3, via Front Door): `https://scoring-prod-dpbebwgrfud2egd2.b01.azurefd.net` — `/healthz` + `/readyz` return 200. The scorer runs the **real trained stacked ensemble** (XGBoost + LightGBM + Logistic regression exported to ONNX, `model_version = v1.1.0-ensemble-gnn`) consuming the **fraud-ring GNN** features (`ring_score` + 16-dim GraphSAGE embedding) over a **seeded feature store** (`SEED_DEMO_FEATURES=true`), so live requests return real APPROVE / SCA / DECLINE decisions (see the `score`/`load` profiles above).
- **Agentic orchestrator** (Phase 4): `https://ca-orchestrator-prod-swc.purpleforest-f993111a.swedencentral.azurecontainerapps.io` — direct Container Apps FQDN (external ingress); `/healthz` 200, `/v1/agents` lists the **6 agents**. It runs the **real** multi-agent workflow on **live Azure OpenAI `gpt-4o-mini`** (managed-identity auth, key auth disabled) with **Cosmos** case persistence, and is now invoked **automatically by the web demo console on every DECLINE** (see the 🤖 agentic case panel above). Use this URL on stage. _Note: the Front Door console endpoint (`console-prod-…b01.azurefd.net`) currently returns an AFD 404 (edge route not serving) — use the direct FQDN above instead._

> **Newly-deployed platform tiers (formerly 📘 reference, now live in `heimdall_rg`).**
> The six components that used to be documented-only are now provisioned by IaC
> (`infra/modules/{apim,redis,servicebus,functions,sentinel}.bicep`, wired in
> `platform.bicep`, live-deployed via `infra/addons.bicep`):
> - **APIM** `apim-heimdall-prod-swc` (Developer SKU) — gateway
>   `https://apim-heimdall-prod-swc.azure-api.net`, `scoring` API (`POST /v1/score`,
>   `GET /healthz`) with a rate-limit policy and App Insights diagnostics.
> - **Azure Managed Redis** `redis-heimdall-prod-swc` (`Balanced_B0`, `EnterpriseCluster`,
>   key-less Entra access) — **read on every `POST /v1/score`** for rolling card
>   aggregates (see `explain.aggregates_ms` in the response, typically < 1 ms).
> - **Service Bus** `sbns-heimdall-prod-swc` (Standard) — `highrisk-alerts` queue for
>   the async enforcement path (Entra-only, `disableLocalAuth`); the scoring API
>   **publishes every DECLINE** to it (key-less send).
> - **Enforcement Function** `func-heimdall-enforce-prod-swc` (Flex Consumption FC1,
>   identity-based storage **locked to private endpoints** — blob/queue/table PEs in
>   `snet-pe`, `publicNetworkAccess=Disabled`; **VNet-integrated** to reach the Cosmos
>   private endpoint) — Service-Bus-triggered block / step-up / notify / **open-case**
>   consumer (`services/enforcement-function/`); each DECLINE persists a Cosmos case in `cases`.
> - **Microsoft Sentinel** — onboarded on `log-heimdall-prod-swc` (SIEM/SOAR).
>
> **On-stage honesty note:** **Redis and the Service Bus → enforcement Function loop
> are now genuinely wired into the live path** — every score reads Redis aggregates,
> and each DECLINE flows DECLINE → `highrisk-alerts` → Function → Cosmos case
> (async, out of the 18 ms budget; the case appears shortly after the decision). The
> **synchronous request path** is still AFD → Container Apps directly (the **APIM** hop
> is provisioned but not yet inserted into the hot 18 ms path) — present APIM as
> *deployed platform capability*, not a step the live demo exercises. See the Status
> column in `docs/architecture.md §3`.

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

## Phase 4 — Agentic case (7:00 → 9:00)

**Show**: the agentic case — either directly in the **web demo console's 🤖 panel**
(it opens automatically on the DECLINE from Phase 3 / the scenario step) or on the
standalone orchestrator UI (browser tab 3). The new case is at the top.

The Semantic Kernel state-graph planner routes the alert through the **6-agent
workflow**, animating each transition. All reasoning agents run on **live Azure
OpenAI `gpt-4o-mini`** (the deployed chat model; key auth is disabled, so the
orchestrator authenticates with its managed identity):

1. **TriageAgent** (gpt-4o-mini) — "Severity: HIGH. Pattern: circular merchant ring. 10 cards involved." → routes to the graph analyst.
2. **GraphAnalystAgent** (gpt-4o-mini) — pulls the 2-hop card/merchant/device neighbourhood from Cosmos: "Confirmed circular flow, depth 3, value €47 200, time-window 6 min. Merchant cluster previously associated with case CR-2024-0918."
3. **PolicyAgent** (gpt-4o-mini) — "PSD2 SCA: TRA was applied on 7/10. Within rolling-fraud guard. AML threshold for SAR met (FATF + national). Recommend: SAR draft + freeze + EBA tagging."
4. **NarrativeAgent** (gpt-4o-mini) — produces a SAR narrative pre-filled with the graph evidence (real generated text, ~800 chars).
5. **CaseManagerAgent** — opens/persists the case in **Cosmos** (`fraud`/`cases`); freezes all 10 PAN-tokens; notifies issuer.
6. **ReflectorAgent** (gpt-4o-mini) — reflects on case completeness/consistency and may request another agent pass before it is handed to a human analyst.

Talk track:
> "Every agent step is logged to an append-only Cosmos container plus immutable Storage — that's our **EU AI Act Article 12** record. The PolicyAgent has a hard rule that any decline of significant amount needs human review — that's our **Article 22 GDPR** safeguard. The reviewer signs the SAR; the agent never submits unilaterally. And this isn't scripted — the narrative you're reading was just generated by gpt-4o-mini from the real graph evidence."

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
