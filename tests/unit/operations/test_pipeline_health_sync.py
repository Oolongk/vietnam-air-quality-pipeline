from __future__ import annotations

import pytest

from src.load.minio_pipeline_log_sync import (
    MinioPipelineLogSyncError,
    build_data_quality_log_rows,
    build_pipeline_log_rows,
)


BATCH_ID = "20260720T120000Z_test"
STARTED_AT = "2026-07-20T12:00:00+00:00"
FINISHED_AT = "2026-07-20T12:00:10+00:00"


def _container(
    object_name: str,
    summary: dict[str, object],
) -> dict[str, object]:
    return {
        "bucket_name": "test-bucket",
        "object_name": object_name,
        "summary": {
            "pipeline_name": (
                "air_quality_pipeline"
            ),
            "source": "open_meteo",
            "status": "SUCCESS",
            "started_at": STARTED_AT,
            "finished_at": FINISHED_AT,
            "duration_seconds": 10.0,
            **summary,
        },
    }


def _summaries() -> dict[str, object]:
    checks = [
        {
            "check_name": (
                "EXPECTED_RECORD_COUNT"
            ),
            "status": "PASSED",
            "bad_records_count": 0,
            "message": "Đủ record.",
        },
        {
            "check_name": "DATA_FRESHNESS",
            "status": "PASSED",
            "bad_records_count": 0,
            "message": "Dữ liệu còn mới.",
        },
    ]

    return {
        "batch_id": BATCH_ID,
        "raw": _container(
            "raw_summary.json",
            {
                "records_extracted": 240,
                "failed_points": 0,
            },
        ),
        "transform": _container(
            "transform_summary.json",
            {
                "input_objects": 10,
                "records_transformed": 240,
                "failed_objects": 0,
            },
        ),
        "quality": _container(
            "data_quality_summary.json",
            {
                "input_records": 240,
                "valid_records": 240,
                "bad_records": 0,
                "checks": checks,
            },
        ),
        "load": _container(
            "load_summary.json",
            {
                "input_rows": 240,
                "processed_rows": 240,
            },
        ),
        "alerts": _container(
            "alert_summary.json",
            {
                "input_records": 240,
                "alert_records": 8,
            },
        ),
        "mart": _container(
            "mart_summary.json",
            {
                "input_records": 12000,
                "output_records": 100,
                "failed_records": 0,
            },
        ),
    }


def test_pipeline_rows_include_six_unique_stages() -> None:
    rows = build_pipeline_log_rows(
        _summaries()
    )

    assert len(rows) == 6

    stage_names = [
        row["stage_name"]
        for row in rows
    ]

    assert stage_names == [
        "extract",
        "transform",
        "data_quality",
        "load_timescaledb",
        "alerts",
        "mart",
    ]

    run_ids = [
        row["run_id"]
        for row in rows
    ]

    assert len(run_ids) == len(
        set(run_ids)
    )

    mart_row = next(
        row
        for row in rows
        if row["stage_name"] == "mart"
    )

    assert mart_row["run_id"] == (
        f"{BATCH_ID}:mart"
    )
    assert mart_row["input_records"] == 12000
    assert mart_row["output_records"] == 100
    assert mart_row["failed_records"] == 0


def test_quality_rows_reference_data_quality_run() -> None:
    rows = build_data_quality_log_rows(
        _summaries()
    )

    assert len(rows) == 2

    assert {
        row["check_name"]
        for row in rows
    } == {
        "EXPECTED_RECORD_COUNT",
        "DATA_FRESHNESS",
    }

    assert all(
        row["run_id"]
        == f"{BATCH_ID}:data_quality"
        for row in rows
    )

    assert all(
        row["batch_id"] == BATCH_ID
        for row in rows
    )


def test_pipeline_rows_reject_missing_batch_id() -> None:
    summaries = _summaries()
    summaries["batch_id"] = ""

    with pytest.raises(
        MinioPipelineLogSyncError,
        match="batch_id",
    ):
        build_pipeline_log_rows(
            summaries
        )
