from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.estimate_aws_snapshot_cost import (
    BYTES_PER_MB,
    CostConfigurationError,
    SnapshotMetrics,
    estimate_monthly_cost,
    load_cost_config,
    measure_snapshot_directory,
)


def _config() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "pricing_date": "2026-08-02",
        "region": "ap-southeast-2",
        "currency": "USD",
        "workload": {
            "pipeline_runs_per_day": 48,
            "release_retention_days": 30,
            "dashboard_requests_per_day": 0,
            "s3_get_requests_per_dashboard_request": 2,
            "lambda_memory_mb": 128,
            "lambda_average_duration_ms": 100,
            "average_response_kb": 256,
            "cloudwatch_log_kb_per_request": 1,
        },
        "fallback_snapshot": {
            "file_count": 3,
            "total_size_mb": 1,
        },
        "pricing": {
            "s3_standard_storage_gb_month_usd": 1,
            "s3_put_per_1000_usd": 1,
            "s3_get_per_1000_usd": 1,
            "lambda_request_per_million_usd": 1,
            "lambda_gb_second_usd": 1,
            "cloudwatch_log_ingestion_gb_usd": 1,
            "internet_data_transfer_out_gb_usd": 1,
        },
        "free_tier": {
            "lambda_requests_per_month": 0,
            "lambda_gb_seconds_per_month": 0,
            "internet_data_transfer_out_gb_per_month": 0,
        },
    }


def test_load_checked_in_cost_config() -> None:
    config = load_cost_config()
    assert config["region"] == "ap-southeast-2"
    assert config["workload"]["pipeline_runs_per_day"] == 48


def test_measure_snapshot_directory_uses_manifest(tmp_path: Path) -> None:
    (tmp_path / "data.json").write_text("{}\n", encoding="utf-8")
    manifest = {
        "files": [
            "data.json",
            "manifest.json",
        ]
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    metrics = measure_snapshot_directory(
        tmp_path,
        {
            "file_count": 99,
            "total_size_mb": 99,
        },
    )

    assert metrics.source == "snapshot_manifest"
    assert metrics.file_count == 2
    assert metrics.total_bytes > 0


def test_measure_snapshot_directory_uses_fallback(tmp_path: Path) -> None:
    metrics = measure_snapshot_directory(
        tmp_path,
        {
            "file_count": 5,
            "total_size_mb": 2,
        },
    )

    assert metrics.source == "fallback_config"
    assert metrics.file_count == 5
    assert metrics.total_bytes == 2 * BYTES_PER_MB


def test_measure_snapshot_rejects_missing_manifest_file(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"files": ["missing.json", "manifest.json"]}),
        encoding="utf-8",
    )

    with pytest.raises(CostConfigurationError):
        measure_snapshot_directory(
            tmp_path,
            {
                "file_count": 5,
                "total_size_mb": 2,
            },
        )


def test_estimate_applies_release_retention() -> None:
    report = estimate_monthly_cost(
        _config(),
        SnapshotMetrics(
            file_count=3,
            total_bytes=BYTES_PER_MB,
            source="test",
        ),
    )

    quantities = report["monthly_quantities"]
    assert quantities["retained_releases_steady_state"] == 1440
    assert quantities["s3_storage_gb_steady_state"] == pytest.approx(
        1440 / 1024,
        abs=1e-6,
    )
    assert report["estimated_cost_usd"]["total_usd"] > 0
