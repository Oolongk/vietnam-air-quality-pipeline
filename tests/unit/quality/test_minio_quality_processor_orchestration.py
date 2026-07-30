from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

import src.quality.minio_quality_processor as quality_processor

BATCH_ID = "BATCH_1"
PARTITION_DATE = "2026-07-25"
PARTITION_HOUR = "02"

TRANSFORM_SUMMARY_OBJECT = (
    "transformed/air_quality/hourly/"
    "date=2026-07-25/"
    "hour=02/"
    "batch_id=BATCH_1/"
    "transform_summary.json"
)

TRANSFORMED_OBJECT = (
    "transformed/air_quality/hourly/"
    "date=2026-07-25/"
    "hour=02/"
    "batch_id=BATCH_1/"
    "data.parquet"
)


def build_settings() -> SimpleNamespace:
    return SimpleNamespace(
        clean_bucket="air-quality-clean",
        mart_bucket="air-quality-mart",
    )


def build_transform_summary() -> dict[str, Any]:
    return {
        "status": "SUCCESS",
        "batch_id": BATCH_ID,
        "partition_date": PARTITION_DATE,
        "partition_hour": PARTITION_HOUR,
        "transformed_object_name": (TRANSFORMED_OBJECT),
        "records_transformed": 3,
        "finished_at": ("2026-07-25T02:30:00+00:00"),
    }


def build_quality_result(
    *,
    valid_count: int,
    bad_count: int,
) -> SimpleNamespace:
    total_records = valid_count + bad_count

    valid_records = pd.DataFrame(
        {
            "point_id": [f"VALID_{index}" for index in range(valid_count)],
            "batch_id": [BATCH_ID] * valid_count,
        }
    )

    bad_records = pd.DataFrame(
        {
            "point_id": [f"BAD_{index}" for index in range(bad_count)],
            "batch_id": [BATCH_ID] * bad_count,
        }
    )

    return SimpleNamespace(
        total_records=total_records,
        valid_count=valid_count,
        bad_count=bad_count,
        valid_records=valid_records,
        bad_records=bad_records,
        pipeline_status=("SUCCESS" if bad_count == 0 else "PARTIAL_SUCCESS"),
        quality_status=("PASSED" if bad_count == 0 else "WARNING"),
        quality_score=(100.0 if bad_count == 0 else 66.67),
        checked_at=("2026-07-25T02:35:00+00:00"),
        expected_records=3,
        expected_active_points=1,
        actual_active_points=1,
        expected_forecast_hours=3,
        passed_check_count=8,
        warning_check_count=(0 if bad_count == 0 else 1),
        failed_check_count=0,
        checks=[
            {
                "check_name": ("REQUIRED_COLUMNS"),
                "status": "PASSED",
                "check_scope": "BATCH",
                "bad_records_count": 0,
            }
        ],
        row_checks={
            "passed": valid_count,
            "failed": bad_count,
        },
        batch_checks={"status": ("PASSED" if bad_count == 0 else "WARNING")},
    )


def create_config_files(
    tmp_path: Path,
) -> tuple[Path, Path]:
    monitoring_points_path = tmp_path / "monitoring_points.csv"

    locations_path = tmp_path / "locations.csv"

    pd.DataFrame(
        [
            {
                "point_id": "NA_VINH",
                "location_id": "NA",
                "point_name": "Vinh",
                "point_type": ("urban_center"),
                "latitude": 18.6796,
                "longitude": 105.6813,
                "is_active": True,
            }
        ]
    ).to_csv(
        monitoring_points_path,
        index=False,
        encoding="utf-8-sig",
    )

    pd.DataFrame(
        [
            {
                "location_id": "NA",
                "location_name": "Nghệ An",
                "region": ("North Central Vietnam"),
                "is_active": True,
            }
        ]
    ).to_csv(
        locations_path,
        index=False,
        encoding="utf-8-sig",
    )

    return (
        monitoring_points_path,
        locations_path,
    )


def clear_quality_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for environment_name in (
        "DQ_EXPECTED_FORECAST_HOURS",
        "DQ_FRESHNESS_MINUTES",
        "DQ_COORDINATE_TOLERANCE",
    ):
        monkeypatch.delenv(
            environment_name,
            raising=False,
        )


def test_process_batch_writes_clean_bad_and_quality_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        monitoring_points_path,
        locations_path,
    ) = create_config_files(tmp_path)

    clear_quality_environment(monkeypatch)

    settings = build_settings()
    client = object()

    transformed_dataframe = pd.DataFrame(
        {
            "point_id": [
                "NA_VINH",
            ],
            "batch_id": [
                BATCH_ID,
            ],
        }
    )

    quality_result = build_quality_result(
        valid_count=2,
        bad_count=1,
    )

    captured_quality_arguments: dict[
        str,
        Any,
    ] = {}

    parquet_writes: list[dict[str, Any]] = []

    json_writes: list[dict[str, Any]] = []

    ensure_buckets_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        quality_processor,
        "ensure_buckets",
        lambda **kwargs: ensure_buckets_calls.append(kwargs),
    )

    def fake_resolve_config_path(
        environment_name: str,
        default_path: str,
    ) -> Path:
        if environment_name == ("MONITORING_POINTS_CONFIG_PATH"):
            return monitoring_points_path

        if environment_name == ("LOCATIONS_CONFIG_PATH"):
            return locations_path

        raise AssertionError(environment_name)

    monkeypatch.setattr(
        quality_processor,
        "_resolve_config_path",
        fake_resolve_config_path,
    )

    monkeypatch.setattr(
        quality_processor,
        "get_parquet_object",
        lambda **kwargs: transformed_dataframe.copy(),
    )

    def fake_run_data_quality(
        **kwargs: Any,
    ) -> SimpleNamespace:
        captured_quality_arguments.update(kwargs)

        return quality_result

    monkeypatch.setattr(
        quality_processor,
        "run_air_quality_data_quality",
        fake_run_data_quality,
    )

    def fake_put_parquet_object(
        **kwargs: Any,
    ) -> dict[str, Any]:
        parquet_writes.append(kwargs)

        return {
            "size_bytes": 1000,
        }

    monkeypatch.setattr(
        quality_processor,
        "put_parquet_object",
        fake_put_parquet_object,
    )

    def fake_put_json_object(
        **kwargs: Any,
    ) -> dict[str, Any]:
        json_writes.append(kwargs)

        return {
            "size_bytes": 500,
        }

    monkeypatch.setattr(
        quality_processor,
        "put_json_object",
        fake_put_json_object,
    )

    monkeypatch.setattr(
        quality_processor,
        "object_exists",
        lambda **kwargs: False,
    )

    monkeypatch.setattr(
        quality_processor,
        "delete_object",
        lambda **kwargs: None,
    )

    summary = quality_processor.process_transformed_batch_on_minio(
        transform_summary=(build_transform_summary()),
        transform_summary_object_name=(TRANSFORM_SUMMARY_OBJECT),
        settings=settings,
        client=client,
    )

    assert len(ensure_buckets_calls) == 1

    assert ensure_buckets_calls[0]["settings"] is settings

    assert ensure_buckets_calls[0]["client"] is client

    assert captured_quality_arguments["expected_batch_id"] == BATCH_ID

    assert captured_quality_arguments["expected_forecast_hours"] == 24

    assert captured_quality_arguments["freshness_minutes"] == 90

    assert captured_quality_arguments["coordinate_tolerance"] == pytest.approx(0.001)

    monitoring_points = captured_quality_arguments["monitoring_points"]

    locations = captured_quality_arguments["locations"]

    assert "NA" in set(monitoring_points["location_id"])

    assert "NA" in set(locations["location_id"])

    clean_object_name = (
        "clean/air_quality/hourly/date=2026-07-25/hour=02/batch_id=BATCH_1/data.parquet"
    )

    bad_object_name = (
        "quality/air_quality/hourly/"
        "date=2026-07-25/"
        "hour=02/"
        "batch_id=BATCH_1/"
        "bad_records.parquet"
    )

    summary_object_name = (
        "quality/air_quality/hourly/"
        "date=2026-07-25/"
        "hour=02/"
        "batch_id=BATCH_1/"
        "data_quality_summary.json"
    )

    history_snapshot_name = (
        "data_quality/history/"
        "date=2026-07-25/"
        "hour=02/"
        "batch_id=BATCH_1/"
        "quality_snapshot.json"
    )

    assert {write["object_name"] for write in parquet_writes} == {
        clean_object_name,
        bad_object_name,
    }

    assert {write["object_name"] for write in json_writes} == {
        history_snapshot_name,
        ("data_quality/latest/quality_snapshot.json"),
        summary_object_name,
    }

    assert summary["status"] == ("PARTIAL_SUCCESS")

    assert summary["quality_status"] == "WARNING"

    assert summary["batch_id"] == BATCH_ID

    assert summary["input_records"] == 3

    assert summary["valid_records"] == 2

    assert summary["bad_records"] == 1

    assert summary["valid_percentage"] == pytest.approx(66.67)

    assert summary["clean_object_name"] == clean_object_name

    assert summary["bad_records_object_name"] == bad_object_name

    assert summary["clean_size_bytes"] == 1000

    assert summary["bad_records_size_bytes"] == 1000

    assert summary["summary_object_name"] == summary_object_name


def test_process_batch_deletes_stale_bad_records_when_all_rows_are_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        monitoring_points_path,
        locations_path,
    ) = create_config_files(tmp_path)

    clear_quality_environment(monkeypatch)

    settings = build_settings()
    client = object()

    quality_result = build_quality_result(
        valid_count=3,
        bad_count=0,
    )

    deleted_objects: list[str] = []
    parquet_objects: list[str] = []
    json_objects: list[str] = []

    monkeypatch.setattr(
        quality_processor,
        "ensure_buckets",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        quality_processor,
        "_resolve_config_path",
        lambda environment_name, default_path: (
            monitoring_points_path
            if environment_name == "MONITORING_POINTS_CONFIG_PATH"
            else locations_path
        ),
    )

    monkeypatch.setattr(
        quality_processor,
        "get_parquet_object",
        lambda **kwargs: pd.DataFrame(
            {
                "point_id": [
                    "NA_VINH",
                ]
            }
        ),
    )

    monkeypatch.setattr(
        quality_processor,
        "run_air_quality_data_quality",
        lambda **kwargs: quality_result,
    )

    def fake_put_parquet_object(
        **kwargs: Any,
    ) -> dict[str, Any]:
        parquet_objects.append(kwargs["object_name"])

        return {
            "size_bytes": 1200,
        }

    monkeypatch.setattr(
        quality_processor,
        "put_parquet_object",
        fake_put_parquet_object,
    )

    monkeypatch.setattr(
        quality_processor,
        "put_json_object",
        lambda **kwargs: (
            json_objects.append(kwargs["object_name"])
            or {
                "size_bytes": 500,
            }
        ),
    )

    bad_object_name = (
        "quality/air_quality/hourly/"
        "date=2026-07-25/"
        "hour=02/"
        "batch_id=BATCH_1/"
        "bad_records.parquet"
    )

    monkeypatch.setattr(
        quality_processor,
        "object_exists",
        lambda **kwargs: kwargs["object_name"] == bad_object_name,
    )

    monkeypatch.setattr(
        quality_processor,
        "delete_object",
        lambda **kwargs: deleted_objects.append(kwargs["object_name"]),
    )

    summary = quality_processor.process_transformed_batch_on_minio(
        transform_summary=(build_transform_summary()),
        transform_summary_object_name=(TRANSFORM_SUMMARY_OBJECT),
        settings=settings,
        client=client,
    )

    assert deleted_objects == [
        bad_object_name,
    ]

    assert bad_object_name not in (parquet_objects)

    assert len(parquet_objects) == 1

    assert summary["status"] == "SUCCESS"

    assert summary["quality_status"] == "PASSED"

    assert summary["valid_records"] == 3

    assert summary["bad_records"] == 0

    assert summary["valid_percentage"] == 100.0

    assert summary["bad_records_object_name"] is None

    assert summary["bad_records_size_bytes"] == 0

    assert len(json_objects) == 3
