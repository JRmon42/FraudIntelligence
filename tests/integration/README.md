# Integration tests

End-to-end tests that exercise the full local stack defined in the root `docker-compose.yml`.

## Run

```bash
docker compose up -d --wait
pip install -r tests/integration/requirements.txt
pip install -e services/transaction-simulator
pytest tests/integration -m integration -v
```

Assertions:

| Test                                           | Asserts                                                       |
| ---------------------------------------------- | ------------------------------------------------------------- |
| `test_p99_latency_and_decision_distribution`   | p99 < 50 ms, decision shares within bounds, no failed reqs    |
| `test_orchestrator_processes_sample_alert`     | POST /alerts returns processed/queued, echoes alertId         |
| `test_cosmos_has_features_after_run`           | `features` container has ≥ 1 row after 30s of traffic         |
| `test_simulator_can_be_invoked`                | The simulator CLI is importable & lists patterns              |
