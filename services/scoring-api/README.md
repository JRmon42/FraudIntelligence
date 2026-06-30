# scoring-api

Real-time card-transaction scoring service for the Heimdall platform.

- **SLO:** p99 latency `< 18 ms` end-to-end (Cosmos point-read + Redis aggregates + ONNX inference + PSD2 optimiser + Event Hub emit).
- **Stack:** Python 3.11, FastAPI, ONNX Runtime, `azure-cosmos`, `redis.asyncio`, `azure-eventhub`, OpenTelemetry, structlog.
- **Container:** distroless multi-stage build, exposes port `8080`.

## Endpoints

| Method | Path                       | Description |
|--------|----------------------------|-------------|
| GET    | `/healthz`                 | Liveness probe |
| GET    | `/readyz`                  | Readiness probe (Cosmos / Redis / ONNX checks) |
| POST   | `/v1/score`                | Score a single transaction |
| POST   | `/v1/score?explain=true`   | Same, returns per-stage timings |

### Request body

```json
{
  "transaction_id": "txn_01HXYZ",
  "card_id": "card_42",
  "merchant_id": "mrc_99",
  "amount": 42.50,
  "currency": "EUR",
  "country": "SE",
  "channel": "ECOM",
  "timestamp": "2025-05-12T10:00:00Z",
  "device_fingerprint": "fp_abc",
  "ip": "203.0.113.7"
}
```

### Response

```json
{
  "decision": "APPROVE",
  "score": 0.0312,
  "reason_codes": ["LOW_RISK"],
  "psd2_exemption": "TRA",
  "model_version": "v1.0.0-ensemble",
  "latency_ms": 6.2,
  "explain": null
}
```

## Quickstart (local)

```bash
cd services/scoring-api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Run with fakeredis + stub ONNX (no Azure deps)
REDIS_FAKE=1 EVENTHUB_FQDN= COSMOS_ENDPOINT= \
  uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### Example curl

```bash
curl -s http://localhost:8080/healthz
curl -s http://localhost:8080/readyz

curl -s -X POST http://localhost:8080/v1/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id":"txn_demo_1",
    "card_id":"card_42",
    "merchant_id":"mrc_99",
    "amount":42.50,
    "currency":"EUR",
    "country":"SE",
    "channel":"ECOM",
    "timestamp":"2025-05-12T10:00:00Z",
    "device_fingerprint":"fp_abc",
    "ip":"203.0.113.7"
  }' | jq

curl -s -X POST 'http://localhost:8080/v1/score?explain=true' \
  -H "Content-Type: application/json" \
  -d @sample.json | jq
```

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

## Model

The scorer runs the trained **stacked ensemble** (XGBoost + LightGBM + Logistic
regression) exported to ONNX by `ml/train_ensemble.py`. The serving layer
(`app/scoring.py::build_onnx_inputs`) maps each request to the model's 34-feature
schema and feeds the fraud probability into the PSD2 policy layer
(`app/psd2_optimizer.py`):

- **10 numeric** transaction/aggregate features + **7 categorical** (one-hot with
  `handle_unknown="ignore"`).
- **17 fraud-ring GNN features** — `card_ring_score` plus the 16-dim GraphSAGE
  card embedding (`card_emb_0..15`) produced by `ml/train_gnn.py`. These are
  published into the online feature store (Cosmos `cards`) by
  `ml/publish_gnn_features.py` and read back per transaction via
  `CardFeatures.ring_score` / `CardFeatures.gnn_embedding`. Because the ensemble
  consumes them, a card the GNN flags as ring-linked is stepped up / declined
  even on an ordinary transaction — the **GNN genuinely drives live decisions**,
  not just an offline/advisory signal. Unknown cards default these to zeros.

- **Loaded from:** `MODEL_PATH` (default `/app/models/ensemble.onnx`), reported as
  `MODEL_VERSION` (default `v1.1.0-ensemble-gnn`).
- **Fallback:** if `MODEL_PATH` is unset/missing the service falls back to a
  deterministic in-memory **stub** scorer (`v0.0.0-stub`) — handy for local runs
  without the artifact.
- **Regenerate the artifact:**

  ```bash
  python ml/train_gnn.py                              # ring_scores + embeddings parquet
  python ml/train_ensemble.py --gnn-dir ml/artifacts  # writes ml/artifacts/ensemble.onnx
  cp ml/artifacts/ensemble.onnx services/scoring-api/models/ensemble.onnx
  python ml/publish_gnn_features.py                   # upsert GNN features into Cosmos
  ```

  The Dockerfile bundles `models/ensemble.onnx` into the image. The committed copy
  under `services/scoring-api/models/` keeps the image build self-contained.

## Docker

```bash
docker build -t fraudintel/scoring-api:dev .
docker run --rm -p 8080:8080 \
  -e REDIS_FAKE=1 -e COSMOS_ENDPOINT= -e EVENTHUB_FQDN= \
  fraudintel/scoring-api:dev
```

## Load testing (5 k TPS)

`scripts/load_test.py` is a `locust` driver pre-configured for ramp-up to 5 000 TPS. **Configuration only — not executed in CI.**

```bash
locust -f scripts/load_test.py --host=http://localhost:8080
```

## Configuration

All settings come from environment variables (see `.env.example`). Secrets are resolved through `DefaultAzureCredential` whenever a connection string / key is left empty.
