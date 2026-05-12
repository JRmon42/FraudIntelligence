# scoring-api

Real-time card-transaction scoring service for the FraudIntelligence platform.

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
  "model_version": "v0.0.0-stub",
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
