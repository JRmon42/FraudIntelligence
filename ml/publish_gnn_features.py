"""Publish fraud-ring GNN outputs into the online feature store (Cosmos `cards`).

The GNN (``ml/train_gnn.py``) emits two parquet artifacts:

* ``ring_scores.parquet``     — ``card_id``, ``ring_score`` (0..1 ring membership)
* ``embeddings_card.parquet`` — ``card_id``, ``emb_0..emb_{D-1}`` GraphSAGE vector

The scoring API's stacked ensemble consumes those per-card features
(``card_ring_score`` + ``card_emb_0..15``), so for the GNN to influence *live*
per-transaction decisions its outputs must land on each card document that the
serving layer point-reads. This script merges the two parquet files by
``card_id`` and upserts ``ring_score`` + ``gnn_embedding`` onto the existing
card documents in the Cosmos ``cards`` container (id == partition key == card_id).

Usage:
    # Dry run — read parquet, show what would be written, touch nothing:
    python3 ml/publish_gnn_features.py --dry-run

    # Publish to Cosmos (DefaultAzureCredential, or COSMOS_KEY if set):
    COSMOS_ENDPOINT=https://acct.documents.azure.com:443/ \
        python3 ml/publish_gnn_features.py

Auth: uses ``COSMOS_KEY`` when present, otherwise ``DefaultAzureCredential``
(managed identity / az login). ``COSMOS_ENDPOINT`` is required unless --dry-run.
By default only cards that already exist in the container are patched; pass
``--create-missing`` to insert minimal documents for unseen cards.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

GNN_EMB_DIM = 16
DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"


def load_gnn_features(gnn_dir: Path, emb_dim: int = GNN_EMB_DIM) -> pd.DataFrame:
    """Merge ring_scores + embeddings parquet into one frame keyed by card_id."""

    ring_path = gnn_dir / "ring_scores.parquet"
    emb_path = gnn_dir / "embeddings_card.parquet"
    if not ring_path.exists() or not emb_path.exists():
        raise FileNotFoundError(
            f"expected {ring_path} and {emb_path}; run ml/train_gnn.py first"
        )

    ring = pd.read_parquet(ring_path)[["card_id", "ring_score"]]
    emb = pd.read_parquet(emb_path)
    emb_cols = [c for c in emb.columns if c != "card_id"][:emb_dim]
    if len(emb_cols) < emb_dim:
        raise ValueError(
            f"embeddings parquet has {len(emb_cols)} dims, expected {emb_dim}"
        )

    df = ring.merge(emb[["card_id", *emb_cols]], on="card_id", how="inner")
    df["ring_score"] = df["ring_score"].astype(float).clip(0.0, 1.0)
    df["gnn_embedding"] = df[emb_cols].astype(float).round(6).values.tolist()
    return df[["card_id", "ring_score", "gnn_embedding"]]


def _make_container(create_missing: bool):
    """Return a sync Cosmos container proxy using key or AAD credential."""

    from azure.cosmos import CosmosClient, PartitionKey  # noqa: PLC0415

    endpoint = os.environ.get("COSMOS_ENDPOINT", "")
    if not endpoint:
        raise SystemExit("COSMOS_ENDPOINT is required (or pass --dry-run)")

    key = os.environ.get("COSMOS_KEY", "")
    if key:
        client = CosmosClient(endpoint, credential=key)
    else:
        from azure.identity import DefaultAzureCredential  # noqa: PLC0415

        client = CosmosClient(endpoint, credential=DefaultAzureCredential())

    db = client.get_database_client(os.environ.get("COSMOS_DATABASE", "fraudintel"))
    container_name = os.environ.get("COSMOS_CARDS_CONTAINER", "cards")
    if create_missing:
        return db.create_container_if_not_exists(
            id=container_name, partition_key=PartitionKey(path="/card_id")
        )
    return db.get_container_client(container_name)


def publish(df: pd.DataFrame, *, create_missing: bool) -> tuple[int, int, int]:
    """Upsert GNN features onto card docs. Returns (patched, created, skipped)."""

    from azure.cosmos.exceptions import CosmosResourceNotFoundError  # noqa: PLC0415

    container = _make_container(create_missing)
    patched = created = skipped = 0
    for row in df.itertuples(index=False):
        card_id = row.card_id
        payload = {"ring_score": float(row.ring_score), "gnn_embedding": list(row.gnn_embedding)}
        try:
            doc = container.read_item(item=card_id, partition_key=card_id)
            doc.update(payload)
            container.upsert_item(doc)
            patched += 1
        except CosmosResourceNotFoundError:
            if not create_missing:
                skipped += 1
                continue
            container.upsert_item({"id": card_id, "card_id": card_id, **payload})
            created += 1
    return patched, created, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gnn-dir", type=Path, default=DEFAULT_ARTIFACT_DIR,
        help="directory holding ring_scores.parquet + embeddings_card.parquet",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="read + summarise the parquet outputs without writing to Cosmos",
    )
    parser.add_argument(
        "--create-missing", action="store_true",
        help="insert minimal card docs for card_ids not already in the container",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="only publish the N highest-ring_score cards (0 = all)",
    )
    args = parser.parse_args(argv)

    df = load_gnn_features(args.gnn_dir)
    df = df.sort_values("ring_score", ascending=False)
    if args.limit > 0:
        df = df.head(args.limit)

    n = len(df)
    n_ring = int((df["ring_score"] > 0.5).sum())
    print(f"loaded {n} card feature rows from {args.gnn_dir} ({n_ring} with ring_score>0.5)")
    print(df.head(10).to_string(index=False))

    if args.dry_run:
        print("\n[dry-run] no writes performed.")
        return 0

    patched, created, skipped = publish(df, create_missing=args.create_missing)
    print(f"\npublished: {patched} patched, {created} created, {skipped} skipped (card absent)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
