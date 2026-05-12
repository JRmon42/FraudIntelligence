# Expected Narrative (canonical fraud-ring scenario)

When the demo (`python -m app.demo`) is executed against
`examples/sample_alert.json`, the orchestrator produces a SAR resembling:

## Suspicious Activity Report

Subject: Coordinated card-not-present fraud ring detected on YYYY-MM-DD.

A network of 5 payment cards transacted with merchant `merch-9001` via shared
device fingerprint `device-FP-7731` within a 90-minute window. The aggregate
exposure is 487.55 EUR. Graph analysis revealed a 2-hop neighbourhood
containing 7 entities with anomaly score 0.91.

Recommended action: freeze affected cards, file SAR with the FIU, and notify
the acquirer.

## EBA Fraud Reporting Narrative

Reporting category: organised fraud (C). Channel: card-not-present. PSD2 SCA
was enforced; no exemption applied. Loss event classified as confirmed fraud
per EBA Guidelines on Fraud Reporting under PSD2.
