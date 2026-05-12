"""Synthetic transaction / card / merchant data generator.

Produces realistic-looking card-not-present transaction data for the
FraudIntelligence platform with:

* ~0.7 % global fraud rate (matching Nordic acquirer baselines)
* 5 Nordic country codes (SE, NO, DK, FI, EE)
* MCC distribution biased toward online retail / travel / digital goods
* Intentional fraud-ring subgraphs (small clusters of cards sharing devices /
  IPs and hitting the same merchants in tight time windows) -- used by the GNN
  to learn ring-membership.

The generator is deterministic given a seed so that smoke tests are stable.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

NORDIC_COUNTRIES = ["SE", "NO", "DK", "FI", "EE"]
MCC_CODES = [5411, 5812, 5912, 5732, 4511, 7995, 5967, 4814, 5944, 5399]
DEVICE_OS = ["iOS", "Android", "Windows", "macOS", "Linux"]


@dataclass
class SyntheticConfig:
    n_transactions: int = 50_000
    n_cards: int = 8_000
    n_merchants: int = 1_500
    n_devices: int = 6_000
    n_ips: int = 4_000
    fraud_rate: float = 0.007
    n_rings: int = 8
    ring_size: int = 12
    seed: int = 42


def _make_entities(cfg: SyntheticConfig, rng: np.random.Generator) -> dict:
    cards = pd.DataFrame({
        "card_id": [f"c_{i:06d}" for i in range(cfg.n_cards)],
        "card_country": rng.choice(NORDIC_COUNTRIES, size=cfg.n_cards,
                                   p=[0.40, 0.20, 0.18, 0.17, 0.05]),
        "card_age_days": rng.integers(30, 3650, size=cfg.n_cards),
        "card_brand": rng.choice(["VISA", "MC", "AMEX"], size=cfg.n_cards,
                                 p=[0.55, 0.40, 0.05]),
    })
    merchants = pd.DataFrame({
        "merchant_id": [f"m_{i:05d}" for i in range(cfg.n_merchants)],
        "mcc": rng.choice(MCC_CODES, size=cfg.n_merchants),
        "merchant_country": rng.choice(NORDIC_COUNTRIES + ["GB", "US", "DE"],
                                       size=cfg.n_merchants),
        "merchant_risk": rng.beta(2, 20, size=cfg.n_merchants),
    })
    devices = pd.DataFrame({
        "device_id": [f"d_{i:06d}" for i in range(cfg.n_devices)],
        "device_os": rng.choice(DEVICE_OS, size=cfg.n_devices),
    })
    ips = pd.DataFrame({
        "ip_id": [f"ip_{i:06d}" for i in range(cfg.n_ips)],
        "ip_country": rng.choice(NORDIC_COUNTRIES + ["GB", "US", "RU", "CN"],
                                 size=cfg.n_ips,
                                 p=[0.30, 0.15, 0.15, 0.15, 0.05, 0.05, 0.05, 0.05, 0.05]),
    })
    return {"cards": cards, "merchants": merchants, "devices": devices, "ips": ips}


def _generate_transactions(cfg: SyntheticConfig, ent: dict, rng: np.random.Generator) -> pd.DataFrame:
    n = cfg.n_transactions
    card_idx = rng.integers(0, cfg.n_cards, size=n)
    merch_idx = rng.integers(0, cfg.n_merchants, size=n)
    dev_idx = rng.integers(0, cfg.n_devices, size=n)
    ip_idx = rng.integers(0, cfg.n_ips, size=n)

    base_ts = pd.Timestamp("2024-01-01", tz="UTC")
    timestamps = base_ts + pd.to_timedelta(rng.integers(0, 86400 * 90, size=n), unit="s")
    amounts = np.round(np.exp(rng.normal(3.2, 1.1, size=n)), 2)

    df = pd.DataFrame({
        "tx_id": [f"t_{i:08d}" for i in range(n)],
        "ts": timestamps,
        "card_id": ent["cards"]["card_id"].values[card_idx],
        "merchant_id": ent["merchants"]["merchant_id"].values[merch_idx],
        "device_id": ent["devices"]["device_id"].values[dev_idx],
        "ip_id": ent["ips"]["ip_id"].values[ip_idx],
        "amount": amounts,
        "currency": rng.choice(["SEK", "NOK", "DKK", "EUR"], size=n,
                               p=[0.40, 0.20, 0.18, 0.22]),
        "channel": rng.choice(["ecom", "pos", "moto"], size=n, p=[0.78, 0.20, 0.02]),
    })
    df = df.merge(ent["cards"], on="card_id", how="left")
    df = df.merge(ent["merchants"], on="merchant_id", how="left")
    df = df.merge(ent["devices"], on="device_id", how="left")
    df = df.merge(ent["ips"], on="ip_id", how="left")

    # Baseline fraud: random noise + inflate when ip_country is non-nordic and amount high
    noise = rng.uniform(0, 1, size=n)
    base_p = (
        0.002
        + 0.015 * (~df["ip_country"].isin(NORDIC_COUNTRIES)).astype(float)
        + 0.010 * (df["amount"] > 200).astype(float)
        + 0.6 * df["merchant_risk"].values
    )
    df["is_fraud"] = ((noise < base_p) & (rng.uniform(0, 1, size=n) < 0.35)).astype(int)

    # Re-balance to hit target fraud_rate exactly-ish
    current_rate = df["is_fraud"].mean()
    if current_rate > cfg.fraud_rate:
        flip = df.index[df["is_fraud"] == 1].to_numpy()
        n_keep = int(cfg.fraud_rate * n)
        drop = rng.choice(flip, size=max(0, len(flip) - n_keep), replace=False)
        df.loc[drop, "is_fraud"] = 0

    df["ring_id"] = ""
    return df


def _inject_rings(cfg: SyntheticConfig, df: pd.DataFrame, ent: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Inject fraud-ring patterns: shared devices/IPs across many cards hitting
    the same merchants in tight bursts."""
    cards = ent["cards"]["card_id"].values
    devices = ent["devices"]["device_id"].values
    ips = ent["ips"]["ip_id"].values
    merchants = ent["merchants"]["merchant_id"].values

    new_rows = []
    for r in range(cfg.n_rings):
        ring_cards = rng.choice(cards, size=cfg.ring_size, replace=False)
        ring_devices = rng.choice(devices, size=2, replace=False)
        ring_ips = rng.choice(ips, size=2, replace=False)
        ring_merchants = rng.choice(merchants, size=3, replace=False)
        ts0 = pd.Timestamp("2024-02-15", tz="UTC") + pd.Timedelta(days=int(r))
        for c in ring_cards:
            for _ in range(rng.integers(3, 8)):
                new_rows.append({
                    "tx_id": f"tr_{r}_{c}_{rng.integers(0, 1_000_000)}",
                    "ts": ts0 + pd.Timedelta(minutes=int(rng.integers(0, 240))),
                    "card_id": c,
                    "merchant_id": rng.choice(ring_merchants),
                    "device_id": rng.choice(ring_devices),
                    "ip_id": rng.choice(ring_ips),
                    "amount": float(np.round(rng.uniform(150, 900), 2)),
                    "currency": "EUR",
                    "channel": "ecom",
                    "is_fraud": 1,
                    "ring_id": f"ring_{r:02d}",
                })
    ring_df = pd.DataFrame(new_rows)
    ring_df = ring_df.merge(ent["cards"], on="card_id", how="left")
    ring_df = ring_df.merge(ent["merchants"], on="merchant_id", how="left")
    ring_df = ring_df.merge(ent["devices"], on="device_id", how="left")
    ring_df = ring_df.merge(ent["ips"], on="ip_id", how="left")
    return pd.concat([df, ring_df], ignore_index=True, sort=False)


def generate(cfg: SyntheticConfig | None = None) -> pd.DataFrame:
    cfg = cfg or SyntheticConfig()
    rng = np.random.default_rng(cfg.seed)
    ent = _make_entities(cfg, rng)
    df = _generate_transactions(cfg, ent, rng)
    df = _inject_rings(cfg, df, ent, rng)
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=str, default="ml/artifacts/synthetic.parquet")
    ap.add_argument("--n", type=int, default=50_000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cfg = SyntheticConfig(n_transactions=args.n, seed=args.seed)
    df = generate(cfg)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"Wrote {len(df):,} rows  fraud_rate={df['is_fraud'].mean():.4f}  -> {out}")


if __name__ == "__main__":
    main()
