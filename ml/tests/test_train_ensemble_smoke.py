"""Smoke test: a 5-row training run completes end-to-end and produces an ONNX
artefact that can be loaded by onnxruntime.

This is a *minimal* exercise of the end-to-end pipeline; it deliberately
trains on a tiny synthetic sample (≈ 5 base rows + ring inflation) so the
test runs in under 60 s.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ml.data.synthetic_data import SyntheticConfig, generate
from ml.train_ensemble import (
    NUM_FEATURES, CAT_FEATURES, build_preprocessor, engineer_features,
)


def test_engineer_features_smoke():
    df = generate(SyntheticConfig(n_transactions=200, seed=11))
    df_fe = engineer_features(df)
    for c in NUM_FEATURES + CAT_FEATURES:
        assert c in df_fe.columns, f"missing feature {c}"
    assert df_fe["card_txn_count_24h"].notna().all()


@pytest.mark.timeout(120)
def test_train_ensemble_smoke(tmp_path: Path):
    """Run a tiny end-to-end training job and validate ONNX output."""
    from ml.train_ensemble import run

    out = tmp_path / "out"
    result = run(input_path=None, output_dir=str(out), n_smoke=2_000)

    onnx_path = out / "ensemble.onnx"
    assert onnx_path.exists(), "ONNX artefact must be written"
    assert (out / "ensemble_model_card.md").exists()
    assert (out / "metrics.json").exists()

    # Validate ONNX session opens
    import onnxruntime as ort
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    assert sess.get_inputs(), "ONNX inputs must be discoverable"

    assert result["metrics"]["onnx_per_row_ms"] < 50.0  # generous CI bound
