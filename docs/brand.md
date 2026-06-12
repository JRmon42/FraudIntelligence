# Heimdall — Brand Guide

> ***The watchful guardian of every transaction.***

## 1. The name

**Heimdall** is the Norse god who stands watch at **Bifröst**, the rainbow bridge to Asgard. He sees and hears everything — the approach of any threat, day or night — and never sleeps. It is the perfect metaphor for a real-time fraud-intelligence platform:

| Heimdall the god | Heimdall the platform |
|---|---|
| Watches every approach to the realm | Scores **every** card transaction (4.2 B/yr) in-line at p99 < 18 ms |
| Sees across vast distances | Graph-Neural-Network ring detection sees fraud *topology*, not just single events |
| Guards the Bifröst bridge | Sits at the edge (Front Door + APIM) — the bridge between customers and the bank |
| Never sleeps | 24/7 autonomous agentic case workflow with human-in-the-loop gates |
| Nordic mythology | Built for a **Nordic** payments provider (SE/NO/DK/FI/EE), EU-sovereign |

## 2. Tagline

**Primary:** *The watchful guardian of every transaction.*

Alternates (by context):
- Short / product: **"Sees every transaction. Stops every fraud."**
- Regulatory / trust: **"Vigilance you can prove."** (ties to EBA reporting + Purview lineage)
- Technical / latency: **"Fraud, caught in 14 milliseconds."**

## 3. Logo concept

A single mark fusing three ideas — see [`assets/heimdall-logo.svg`](assets/heimdall-logo.svg):

1. **Shield** — protection, banking-grade trust, security-by-design.
2. **Bifröst arc** — the rainbow bridge Heimdall guards, rendered as a gradient sweep (teal → blue → deep navy). Doubles as the "edge" the platform defends.
3. **All-seeing eye** — set within the shield, the watchful gaze: real-time, always-on scoring.

**Construction:** eye centred in a navy shield; the Bifröst arc passes behind the eye; 8 px gradient stroke on the shield edge. Scales cleanly to a 16 px favicon (drop the arc, keep shield + eye) and up to hero size.

## 4. Colour palette

| Token | Hex | Use |
|---|---|---|
| `--heimdall-navy` (primary) | `#0E2A47` | Shield body, headers, dark UI |
| `--heimdall-blue` | `#1F8FE5` | Primary accent, links, active states |
| `--heimdall-teal` | `#3DD6C4` | Bifröst highlight, success/healthy, charts |
| `--heimdall-ink` | `#04111F` | Text on light, pupil |
| `--heimdall-mist` | `#EAF6FF` | Light backgrounds, eye highlight |
| `--heimdall-deep` | `#1F4E78` | Bifröst shadow, secondary headings (matches existing Power BI title colour) |

Gradient (Bifröst): `#3DD6C4 → #1F8FE5 → #1F4E78`.

## 5. Usage

- **Wordmark:** "Heimdall" in a humanist sans (e.g. Inter / Segoe UI Semibold). Optional descriptor beneath: *Fraud Intelligence Platform*.
- **Shield emoji** 🛡️ may prefix the name in plain-text contexts (READMEs, CLI banners, Slack).
- **Do not** rename deployed Azure resources to "heimdall-*": the live stack keeps the `fraudintel*` resource tokens and `fraudintelligence_rg` group (see note below). Heimdall is the *brand*, not the resource-naming prefix.

## 6. Brand vs. infrastructure naming (important)

The rebrand to Heimdall is **display-only**. The deployed Sweden-Central stack retains its original resource-naming tokens because renaming live Azure resources would orphan all 75 resources and require a full teardown + redeploy:

- Resource group: `fraudintelligence_rg`
- Name prefix: `fraudintel` (e.g. `acrfraudintelprodswc`, `kv-fraudintel-prod-swc`, `cosmos-fraudintel-prod-swc`)
- GitHub repo: `JRmon42/FraudIntelligence`

To make the infrastructure prefix "heimdall" as well, that is a separate, deliberate operation: change the `namePrefix` in `infra/main.bicep` / `infra/platform.bicep`, then teardown + redeploy + rebuild images. Optionally rename the GitHub repo (GitHub auto-redirects the old URL). Until then, all commit/repo links intentionally still point to `JRmon42/FraudIntelligence`.
