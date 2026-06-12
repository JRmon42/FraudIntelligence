# Checkpoint 003 — Architecture updated from source docs

> Repo-resident copy so this checkpoint can be loaded from **any** session without
> a session-ID path. To resume, point an agent at this file and ask it to verify
> the working tree and continue from the open items.

## Scope / purpose
Update `docs/architecture.md` (and reconcile related docs) from the source design
documents — async enforcement path, sync/async latency split, ensemble + SHAP
detail, PAN protection, EU AI Act fraud carve-out — and capture the verified state.

## Verified state of the working tree
All edits described by the checkpoint are present and consistent:

- **Async action path** — `docs/architecture.md §4.3` (Service Bus high-risk alert
  queue → Azure Functions enforcement / case open / step-up / notify), with the
  component table (§3) and mermaid data-plane diagram (§2.1) showing `SBQ` + `FUNC`.
- **Sync vs async split** — explicit note in §4.1 + §4.2; the 18 ms budget covers
  only the synchronous decision; durable enforcement is off the latency path.
- **Ensemble detail + SHAP** — §4.1.4 (GBDT + LSTM + meta-learner + GNN embeddings,
  ONNX in-proc) and SHAP-derived reason codes in §4.1 / §4.3.
- **PAN protection** — §5 NFR: "Raw PAN is never stored — tokenised / HMAC-SHA-256
  with an HSM-managed key".
- **Implementation-status note** — after the §3 component table: APIM, Redis
  Enterprise, Service Bus, Managed Grafana, Sentinel are *documented targets*;
  `feature-builder` Function implemented, enforcement Function planned.
- **EU AI Act Annex III §5(b) fraud carve-out + voluntary high-risk-grade
  governance** — reconciled across **4 files**: `docs/architecture.md` (§1, §7, TL;DR),
  `docs/compliance/eu-ai-act.md`, `ml/README.md`, `docs/adr/ADR-0008-security-governance-triad.md`.

## Infra cross-check (infra/)
- **App Insights**: present — created in `infra/modules/loganalytics.bicep`
  (workspace-based), wired to ACA (`appInsightsConnectionString`), AML
  (`appInsightsId`) and `monitor.bicep` alerts.
- **Redis**: no `redis.bicep` module — consistent with "documented target" status.
- **Stream Analytics**: `infra/modules/streamanalytics.bicep` deployed on primary;
  networking hardening still an open note.
- **Service Bus / enforcement Function**: not yet in `infra/` (documented target).

## Carried-forward open items
1. **App Insights** — ✅ **RESOLVED (verified 2026-06-11).** Alert wiring confirmed
   end-to-end: `loganalytics.bicep` outputs `appInsightsId` →
   `platform.bicep:166,263` passes it to `monitor.bicep`, which defines an action
   group + 6 alert rules (scoring p99 > 18 ms, decline-rate spike via scheduled
   query, Cosmos 429 throttle, Event Hubs backlog, Defender high-severity activity
   log). `mon` module is gated on `isPrimary`.
2. **Redis Enterprise** — **DECISION: keep as documented target.** Consistent with
   the other deferred components (APIM, Service Bus, Managed Grafana, Sentinel) that
   the §3 implementation-status note lists as documented targets. No `redis.bicep`
   added; revisit if/when the hot-path feature cache is provisioned.
3. **ASA networking** — **deliberate deferral.** `streamanalytics.bicep` already
   hardens auth (SystemAssigned MSI + RBAC for Event Hubs in/out and Cosmos; relies
   on namespace `disableLocalAuth=true`). Full private networking / VNet integration
   for the ASA job requires the dedicated **Stream Analytics cluster** SKU — a
   cost/scope decision left open.
4. **Commit decision** — still open. ckpt 002 + 003 doc edits remain uncommitted.
   `git`/`bash` are blocked for this repo path by org content-exclusion policy in the
   Copilot CLI WSL environment, so committing must be done by the user directly.

   Suggested commit message when ready:
   ```
   docs: reconcile architecture with source design docs (ckpt 002+003)

   Async enforcement path, sync/async 18ms split, ensemble+SHAP detail,
   PAN HMAC-SHA-256 protection, implementation-status note, and EU AI Act
   Annex III §5(b) fraud carve-out + voluntary high-risk-grade governance
   reconciled across architecture.md, compliance/eu-ai-act.md, ml/README.md
   and ADR-0008. Verified App Insights alert wiring end-to-end.

   Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
   ```

## Environment note
- In the Copilot CLI WSL environment, the repo path may be blocked for the `bash`/`git`
  tools by org content-exclusion policy; use `view`/`glob`/`grep`/`edit` tools instead.

## To resume in any session
> Load checkpoint 003 from `docs/checkpoint-003-architecture-updated-from-docs.md`,
> verify the FraudIntelligence working tree still matches the described state, then
> resume from the carried-forward open items.
