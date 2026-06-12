# Day-2 Operations Runbook

> **Purpose.** Standard operating procedures for running the Nordic Heimdall Platform after go-live: model rollout, blue/green for the scoring API, feature-store re-warm, Cosmos failover, key rotation, Defender alert response, and EBA report publication.

All procedures assume:
- You are a member of `aad-fraudops-oncall` (PIM-elevated to `Contributor` on `rg-fraud-prod-*` for the duration of the change).
- Change is tracked in ServiceNow and posted to `#fraud-ops`.
- All commands run from the `scripts/` folder unless noted.

---

## 1. Model rollout (champion → challenger → champion)

**Trigger**: AML registry shows a new model version in `Staging` with passing eval + Responsible-AI scorecard.

1. **Pre-checks**
   - Eval delta vs champion ≥ 0 on AUC, no FPR-parity regression > 2 pp across countries.
   - Model card updated; SBOM attached; cosign signature verified.
2. **Promote artefact**
   ```bash
   az ml model update --name fraud-ensemble --version <N> --stage Production
   ```
3. **Build new ACA revision** (image tag = model version + git SHA).
4. **Shadow at 5 %** via ACA traffic split for 2 h:
   ```bash
   az containerapp revision set-mode --mode multiple ...
   az containerapp ingress traffic set --revision-weight champion=95 challenger=5
   ```
5. Watch App Insights: p99 latency, error rate, score-distribution drift (Evidently).
6. Increase to 25 % → 50 % → 100 % over 24 h with a 30-min hold at each step.
7. **Roll back**: re-set traffic to champion=100; revision retained for 7 days for forensics.
8. Update the model card "deployed" field; archive the previous champion as `Archived`.

---

## 2. Blue/green for scoring API (code change, no model change)

1. CI builds image, pushes to ACR, creates new ACA revision (`--revision-suffix bluegreen-<sha>`).
2. Smoke test on revision-specific URL via APIM internal route.
3. Shift traffic 0 → 10 → 50 → 100 over 30 min.
4. Watch the SLO dashboard (Grafana → "Scoring API SLO"): error budget, p99, scale-out events.
5. On regression, traffic shift to old revision (single command); incident if needed.

---

## 3. Feature-store re-warm

**Trigger**: Cosmos region rebuild, schema change, or post-disaster cold cache.

1. Pause `tx.scored` consumer that writes derived features (Stream Analytics job `asa-feature-derive`).
2. Run `scripts/feature-rewarm.py --hours 24 --regions sec,nec` — replays last 24 h from Bronze into Cosmos `features` container with idempotent upsert (`If-Match` etag = `*` for first write, then `*` for retries).
3. Wait until cache hit ratio in Redis ≥ 95 % (Grafana panel).
4. Resume `asa-feature-derive`.
5. Run smoke `scripts/smoke-test.sh` (50 synthetic transactions) and verify p99 < 18 ms.

---

## 4. Cosmos failover drill (quarterly)

Goal: validate RTO ≤ 90 s for regional Cosmos failure.

1. Announce drill in `#fraud-ops` and to NCAs if required by drill scope.
2. Force failover from SE Central to North Europe:
   ```bash
   az cosmosdb failover-priority-change \
     --name cosmos-fraud-prod \
     --resource-group rg-fraud-prod-shared \
     --failover-policies northeurope=0 swedencentral=1
   ```
3. Confirm ACA in NE handles 100 % of `tx.scored` writes; SE replicas in NE accept traffic.
4. Validate: scoring p99 < 18 ms in NE; agentic orchestrator unchanged; no data loss in `audit_scoring`.
5. Fail back after 1 h by reversing priorities.
6. Capture timings, RU/s, error rates → DR drill report → DPO + CRO.

---

## 5. Key rotation

**Cadence**: HSM keys every 12 months; certificates per their own cadence; secrets every 90 days.

1. **CMK** for Cosmos / OneLake / Storage:
   - Create new key version in Key Vault Premium HSM.
   - Update encryption key reference on the resource (`az cosmosdb update --key-uri ...`).
   - Verify reads/writes; old key version retained for 90 d (recovery).
2. **APIM ↔ ACA mTLS** certs: rotate via Key Vault, APIM auto-pulls; verify via `openssl s_client`.
3. **AOAI keys**: switch to managed identity wherever possible; for any remaining keys, dual-key swap with zero-downtime via Key Vault references in ACA.
4. **GitHub Actions OIDC**: federated, no rotation needed (audit federation subjects quarterly).

---

## 6. Defender alert response

**Severity routing**: P1/P2 → page on-call (PagerDuty); P3 → ticket.

1. Triage in **Defender for Cloud** → click through to the resource.
2. If suspected data-plane compromise: **isolate** the ACA revision (set `--min-replicas 0` for that revision) and route 100 % to the previous revision.
3. Pull container logs + App Insights traces for the affected `requestId`s to a forensic Storage container with **Immutable** policy.
4. If GDPR personal data may be affected: open the `pb-gdpr-breach` Sentinel playbook → 72 h timer.
5. RCA within 5 business days; preventive control added to Policy initiative if applicable.

---

## 7. EBA report publication (quarterly / semi-annual)

1. **T-7 days**: `pl-eba-aggregate` Fabric pipeline runs in dry-run; Reviewer Group `aad-eba-reviewers` checks reconciliation report.
2. **T-2 days**: full run; Power BI paginated report rendered to PDF; XBRL/CSV file generated by `services/eba-reporter`; both signed (cosign) and archived to **Storage Immutable Blob** (WORM 7 yr).
3. Reviewers sign off in the case tool (immutable record).
4. Submission to each NCA via existing channel (host-to-host SFTP for SE/NO/DK/FI; portal upload for EE).
5. Receipts attached to the archive entry; entry referenced from the next AI Risk Committee minutes.

---

## TL;DR

Operations are **scripted, observable and reversible**: ACA revisions for blue/green, AML registry for model lifecycle, scripted Cosmos failover validated quarterly, HSM-backed key rotation, Defender → Sentinel for incidents with a wired GDPR breach playbook, and a fully automated EBA submission pipeline with WORM-archived evidence.

---

## 8. Stream Analytics & private networking

The Event Hubs namespace `evhns-heimdall-prod-swc` is intentionally locked down:
`publicNetworkAccess=Disabled`, `disableLocalAuth=true`, reachable only via its private
endpoint. A standard **Stream Analytics cloud job** is a multi-tenant PaaS service and
**cannot reach a private-only namespace**, so `scripts/scale-to-prod.sh` may report:

> `Access to EventHub … is not authorized. Ip has been prevented to connect to the endpoint.`

This is a **network-architecture constraint, not an RBAC bug** — the ASA managed identity
already holds the required data-plane roles (granted in `infra/modules/streamanalytics.bicep`:
Event Hubs Data Receiver + Data Sender on the namespace, DocumentDB Account Contributor and
the Cosmos built-in Data Contributor on the account). The real-time **scoring API demo does
not depend on ASA** and is unaffected.

To run ASA against the stream live, choose one (both are deliberate decisions):

**Option A — Trusted-service bypass (relaxes posture).** Allow Azure trusted services to
bypass the namespace firewall. This flips `publicNetworkAccess` to `Enabled` with a
default-deny rule, so the public internet is still blocked but trusted Azure services
(incl. Stream Analytics via managed identity) may connect:

```bash
RG=heimdall_rg ; NS=evhns-heimdall-prod-swc
az eventhubs namespace update -g $RG -n $NS --public-network-access Enabled
az eventhubs namespace network-rule-set update -g $RG --namespace-name $NS \
  --default-action Deny --trusted-service-access-enabled true
# then re-run: ./scripts/scale-to-prod.sh   (ASA start should now succeed)
```

**Option B — ASA dedicated cluster (preserves private-only posture).** Provision a
Stream Analytics **dedicated cluster** and create a **managed private endpoint** from the
cluster to the Event Hubs namespace, then move the job into the cluster. This keeps
`publicNetworkAccess=Disabled` but adds cost (dedicated cluster SKU). Recommended for
production where the private boundary must not be relaxed.

> Decision pending owner sign-off — the platform ships with the hardened private-only
> default (Option B posture) and ASA left stopped, since the scoring demo does not need it.
