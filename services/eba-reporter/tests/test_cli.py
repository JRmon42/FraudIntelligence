from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from report import cli


def test_cli_dry_run_writes_local_files(tmp_path: Path, sample_rows) -> None:
    runner = CliRunner()
    with patch("report.load_rows", return_value=sample_rows):
        result = runner.invoke(
            cli,
            [
                "--country",
                "SE",
                "--quarter",
                "2025-Q1",
                "--out",
                str(tmp_path),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == [
        "eba_SE_2025-Q1.json",
        "eba_SE_2025-Q1.parquet",
        "eba_SE_2025-Q1.xlsx",
    ]
