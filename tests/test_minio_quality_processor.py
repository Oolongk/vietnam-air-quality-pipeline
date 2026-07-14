from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

import src.quality.minio_quality_processor as quality_module
from src.quality.minio_quality_processor import (
    build_clean_prefix,
    build_quality_prefix,
    evaluate_data_quality,
    find_latest_quality_candidate,
)
from src.utils.minio_client import (
    MinioSettings,
)


def build_test_settings() -> MinioSettings:
    return MinioSettings(
        endpoint="localhost:9000",
        access_key="testaccess",
        secret_key="testsecret",
        secure=False,
        raw_bucket="air-quality-raw",
        clean_bucket="air-quality-clean",
        mart_bucket="air-quality-mart",
    )


def build_valid_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "point_id": "HN_CENTER",
                "location_id": "HN",
                "forecast_time": pd.Timestamp(
                    "2026-07-13T21:00:00+07:00"
                ),
                "pm2_5": 18.5,
                "pm10": 30.0,
                "us_aqi": 75,
                "latitude": 21.0285,
                "longitude": 105.8542,
                "source": "open_meteo",
            },
            {
                "point_id": "HCM_CENTER",
                "location_id": "HCM",
                "forecast_time": pd.Timestamp(
                    "2026-07-13T21:00:00+07:00"
                ),
                "pm2_5": 20.1,
                "pm10": 32.5,
                "us_aqi": 82,
                "latitude": 10.7769,
                "longitude": 106.7009,
                "source": "open_meteo",
            },
        ]
    )


def test_all_valid_records_pass() -> None:
    (
        clean_dataframe,
        bad_dataframe,
        checks,
    ) = evaluate_data_quality(
        build_valid_dataframe()
    )

    assert len(clean_dataframe) == 2

    assert bad_dataframe.empty

    assert len(checks) == 10

    assert all(
        check["status"] == "PASSED"
        for check in checks
    )


def test_splits_invalid_record() -> None:
    dataframe = (
        build_valid_dataframe()
    )

    dataframe.loc[
        0,
        "pm2_5",
    ] = -5.0

    (
        clean_dataframe,
        bad_dataframe,
        checks,
    ) = evaluate_data_quality(
        dataframe
    )

    assert len(clean_dataframe) == 1

    assert len(bad_dataframe) == 1

    assert (
        "PM2_5_NON_NEGATIVE"
        in bad_dataframe.loc[
            0,
            "dq_error_codes",
        ]
    )

    check_by_name = {
        check["check_name"]: check
        for check in checks
    }

    assert (
        check_by_name[
            "PM2_5_NON_NEGATIVE"
        ]["bad_records_count"]
        == 1
    )


def test_duplicate_marks_both_records() -> None:
    dataframe = pd.concat(
        [
            build_valid_dataframe().iloc[
                [0]
            ],
            build_valid_dataframe().iloc[
                [0]
            ],
        ],
        ignore_index=True,
    )

    (
        clean_dataframe,
        bad_dataframe,
        checks,
    ) = evaluate_data_quality(
        dataframe
    )

    assert clean_dataframe.empty

    assert len(bad_dataframe) == 2

    assert all(
        "UNIQUE_LOGICAL_KEY"
        in error_code
        for error_code in bad_dataframe[
            "dq_error_codes"
        ]
    )


def test_builds_minio_prefixes() -> None:
    clean_prefix = build_clean_prefix(
        partition_date="2026-07-13",
        partition_hour="21",
        batch_id="test_batch",
    )

    quality_prefix = (
        build_quality_prefix(
            partition_date="2026-07-13",
            partition_hour="21",
            batch_id="test_batch",
        )
    )

    assert clean_prefix == (
        "clean/air_quality/hourly/"
        "date=2026-07-13/"
        "hour=21/"
        "batch_id=test_batch"
    )

    assert quality_prefix == (
        "quality/air_quality/hourly/"
        "date=2026-07-13/"
        "hour=21/"
        "batch_id=test_batch"
    )


def test_latest_candidate_ignores_failed_transform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_test_settings()

    failed_name = (
        "transformed/air_quality/hourly/"
        "date=2026-07-13/hour=20/"
        "batch_id=failed/"
        "transform_summary.json"
    )

    success_name = (
        "transformed/air_quality/hourly/"
        "date=2026-07-13/hour=21/"
        "batch_id=success/"
        "transform_summary.json"
    )

    monkeypatch.setattr(
        quality_module,
        "list_object_names",
        lambda **kwargs: [
            failed_name,
            success_name,
        ],
    )

    summaries = {
        failed_name: {
            "status": "FAILED",
            "started_at": (
                "2026-07-13T13:00:00+00:00"
            ),
            "finished_at": (
                "2026-07-13T13:01:00+00:00"
            ),
            "records_transformed": 0,
            "transformed_object_name": None,
        },
        success_name: {
            "status": "SUCCESS",
            "started_at": (
                "2026-07-13T14:00:00+00:00"
            ),
            "finished_at": (
                "2026-07-13T14:01:00+00:00"
            ),
            "records_transformed": 240,
            "transformed_object_name": (
                "transformed/data.parquet"
            ),
        },
    }

    monkeypatch.setattr(
        quality_module,
        "get_json_object",
        lambda object_name, **kwargs: (
            summaries[object_name]
        ),
    )

    (
        selected_object_name,
        selected_summary,
    ) = find_latest_quality_candidate(
        settings=settings,
        client=object(),
    )

    assert (
        selected_object_name
        == success_name
    )

    assert (
        selected_summary["status"]
        == "SUCCESS"
    )