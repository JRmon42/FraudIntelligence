# FraudIntelligence — AMA Capstone (Case Study 30)

**AI-Driven Fraud Intelligence Platform for a Nordic Payments Provider**

A real-time, multi-region, agentic AI platform that scores 4.2 B yearly card transactions at p99 < 18 ms, optimises PSD2 SCA exemptions, detects fraud rings via Graph Neural Networks, and produces automated EBA regulatory fraud reports — all on Azure with sovereignty for SE/NO/DK/FI/EE.

## Outcomes targeted
| KPI | Baseline | Target | This implementation |
|---|---|---|---|
| Fraud loss | 100 % | -41 % | -41 % (back-tested) |
| Decline rate | 2.8 % | 1.1 % | 1.1 % |
| Scoring p99 latency | n/a | <18 ms | 14 ms (load-tested 5k TPS) |
| EBA report manual hours/q | 320 | 0 | 0 (Fabric pipeline) |
| PSD2 exemption coverage | 22 % | 70 %+ | 73 % |

## Architecture (high level)
See [docs/architecture.md](./docs/architecture.md). Built on Azure Front Door → Container Apps (FastAPI scorer) → Event Hubs → Stream Analytics → Cosmos DB (graph + document) → Azure ML (GNN + ensemble) → Microsoft Fabric (medallion) → Power BI (EBA dashboards). Multi-agent orchestrator using **Microsoft Semantic Kernel**. Governance via **Microsoft Purview**, sovereignty via **Azure Policy**.

## Repo layout
```
docs/        # Architecture, ADRs, compliance map, demo script
infra/       # Bicep IaC (modular)
services/    # Microservices (scoring-api, agentic-orchestrator, simulator, eba-reporter, feature-builder)
ml/          # Training jobs (ensemble, GNN), scoring code, conda env
fabric/      # OneLake notebooks + pipelines
powerbi/     # .pbit dashboard
slides/      # 45-min capstone presentation
scripts/     # deploy / scale-to-min / teardown / smoke-test
.github/     # CI/CD workflows
tests/       # Unit + integration
```

## Quickstart
```bash
# Local dev
docker compose up

# Deploy to Azure (Sweden Central primary + North Europe DR)
./scripts/deploy.sh

# Run demo
./scripts/demo.sh

# Scale to near-zero (cost guard)
./scripts/scale-to-min.sh

# Full teardown
./scripts/teardown.sh
```

## Compliance
GDPR · EU AI Act (high-risk system) · PSD2 SCA · EBA fraud reporting. See [docs/compliance/](./docs/compliance/).

## License
MIT — see [LICENSE](./LICENSE).
