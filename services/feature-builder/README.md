# feature-builder

Azure Functions v2 (Python) app that consumes raw card transactions from
Event Hub `txn.events` and writes per-card / per-merchant rolling features
(1 m / 5 m / 1 h / 24 h windows) into Cosmos DB, then re-emits them on
`feature.events` for downstream graph + reporter agents.

## Triggers / bindings

- **Trigger:** Event Hub `txn.events`, consumer group `feature-builder`
- **Outputs:**
  - Cosmos DB container `features` (partition key `/entity_key`)
  - Event Hub `feature.events` (fire-and-forget producer)
- **Idempotency:** dedup container `dedup` on `transaction_id`
  (TTL configured via `FEATURE_BUILDER_DEDUP_TTL_S`).

## Sliding-window feature schema

For each `(entity_type, entity_id)` ∈ `{card, merchant}`:

| Feature           | Type   | Description |
|-------------------|--------|-------------|
| `count_1m`        | int    | rolling count, 1-minute window |
| `amount_1m`       | float  | rolling sum, 1-minute window  |
| `count_5m`        | int    | rolling count, 5-minute window |
| `amount_5m`       | float  | rolling sum, 5-minute window  |
| `count_1h`        | int    | rolling count, 1-hour window  |
| `amount_1h`       | float  | rolling sum, 1-hour window    |
| `count_24h`       | int    | rolling count, 24-hour window |
| `amount_24h`      | float  | rolling sum, 24-hour window   |
| `unique_merchants_1h` | int | distinct merchants per card, 1-hour window |

The state document also stores a bounded sliding-window event log so
the windows can be recomputed exactly when an event arrives out of
order.

## Local development

```bash
cd services/feature-builder
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio
cp local.settings.json local.settings.local.json   # add real values
func start --python   # requires Azure Functions Core Tools v4
```

## Tests

```bash
pytest -q
```

The test suite uses an in-memory Cosmos / Event Hub fake plus a
`make_event` factory.

## Deployment

```bash
func azure functionapp publish <function-app-name>
```

Identity & secret access uses `DefaultAzureCredential` whenever the
Cosmos / Event Hub connection-string variables are left empty.
