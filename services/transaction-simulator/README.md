# Transaction Simulator

Async load generator that drives realistic Nordic card-payment traffic against the Heimdall
scoring API. Used for performance benchmarking, fraud-pattern replay and CI smoke tests.

## Usage

```bash
pip install -e .[dev]
python -m simulator run \
    --target http://localhost:8080 \
    --tps 500 \
    --pattern fraud-ring \
    --duration 60
```

Reports are written to `./reports/report.json` and `./reports/report.html`.

## Patterns

| Pattern              | Description                                                             |
| -------------------- | ----------------------------------------------------------------------- |
| `normal`             | Baseline e-commerce + POS distribution                                  |
| `fraud-ring`         | 10 cards × 3 merchants circular flows over a 90 s window                |
| `account-takeover`   | Velocity bursts from a single card after credential-stuffing pattern    |
| `mixed`              | 90 % normal + 7 % ATO + 3 % ring                                        |

## Docker

```bash
docker build -t fraud-intel/simulator .
docker run --rm --network host fraud-intel/simulator \
    run --target http://localhost:8080 --tps 200 --duration 30
```
