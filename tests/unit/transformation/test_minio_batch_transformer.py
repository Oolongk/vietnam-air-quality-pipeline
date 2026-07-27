from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

import src.transform.minio_batch_transformer as transformer_module
from src.transform.minio_batch_transformer import (
    MinioBatchTransformError,
    build_transformed_prefix,
    find_latest_transformable_raw_batch,
    transform_raw_object,
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


def build_raw_object() -> dict:
    return {
        "schema_version": "1.0",
        "batch_id": "test_batch",
        "source": "open_meteo",
        "extracted_at": (
            "2026-07-13T14:00:00+00:00"
        ),
        "point": {
            "point_id": "HN_CENTER",
            "location_id": "HN",
            "point_name": "Trung tâm Hà Nội",
            "point_type": "urban_center",
            "latitude": 21.0285,
            "longitude": 105.8542,
        },
        "api_response": {
            "data": {
                "hourly": {
                    "time": [
                        "2026-07-13T21:00",
                        "2026-07-13T22:00",
                    ],
                    "pm2_5": [
                        18.5,
                        19.2,
                    ],
                    "pm10": [
                        30.1,
                        31.2,
                    ],
                    "carbon_monoxide": [
                        200.0,
                        205.0,
                    ],
                    "nitrogen_dioxide": [
                        12.5,
                        13.0,
                    ],
                    "sulphur_dioxide": [
                        3.5,
                        3.7,
                    ],
                    "ozone": [
                        70.0,
                        72.0,
                    ],
                    "us_aqi": [
                        75,
                        80,
                    ],
                    "us_aqi_pm2_5": [
                        60,
                        65,
                    ],
                    "us_aqi_pm10": [
                        40,
                        42,
                    ],
                }
            }
        },
    }


def test_transforms_nested_raw_envelope() -> None:
    dataframe = transform_raw_object(
        build_raw_object()
    )

    assert len(dataframe) == 2

    assert dataframe[
        "point_id"
    ].tolist() == [
        "HN_CENTER",
        "HN_CENTER",
    ]

    assert dataframe[
        "location_id"
    ].tolist() == [
        "HN",
        "HN",
    ]

    assert dataframe[
        "us_aqi"
    ].tolist() == [
        75,
        80,
    ]

    assert str(
        dataframe[
            "forecast_time"
        ].dt.tz
    ) == "Asia/Ho_Chi_Minh"

    assert (
        str(dataframe["us_aqi"].dtype)
        == "Int64"
    )

    assert (
        str(dataframe["pm2_5"].dtype)
        == "Float64"
    )


def test_rejects_mismatched_hourly_lengths() -> None:
    raw_object = build_raw_object()

    raw_object[
        "api_response"
    ]["data"]["hourly"][
        "pm2_5"
    ] = [18.5]

    with pytest.raises(
        MinioBatchTransformError,
        match="phần tử",
    ):
        transform_raw_object(
            raw_object
        )


def test_builds_transformed_prefix() -> None:
    result = build_transformed_prefix(
        partition_date="2026-07-13",
        partition_hour="21",
        batch_id="test_batch",
    )

    assert result == (
        "transformed/air_quality/hourly/"
        "date=2026-07-13/"
        "hour=21/"
        "batch_id=test_batch"
    )


def test_latest_batch_ignores_failed_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_test_settings()

    summary_names = [
        (
            "open_meteo/air_quality/"
            "date=2026-07-13/hour=21/"
            "batch_id=failed/"
            "run_summary.json"
        ),
        (
            "open_meteo/air_quality/"
            "date=2026-07-13/hour=22/"
            "batch_id=success/"
            "run_summary.json"
        ),
    ]

    monkeypatch.setattr(
        transformer_module,
        "list_object_names",
        lambda **kwargs: summary_names,
    )

    summaries = {
        summary_names[0]: {
            "status": "FAILED",
            "started_at": (
                "2026-07-13T14:00:00+00:00"
            ),
            "finished_at": (
                "2026-07-13T14:01:00+00:00"
            ),
            "successes": [],
        },
        summary_names[1]: {
            "status": "SUCCESS",
            "started_at": (
                "2026-07-13T15:00:00+00:00"
            ),
            "finished_at": (
                "2026-07-13T15:01:00+00:00"
            ),
            "successes": [
                {
                    "point_id": "HN_CENTER",
                    "object_name": (
                        "raw/data.json"
                    ),
                }
            ],
        },
    }

    monkeypatch.setattr(
        transformer_module,
        "get_json_object",
        lambda object_name, **kwargs: (
            summaries[object_name]
        ),
    )

    (
        selected_name,
        selected_summary,
    ) = find_latest_transformable_raw_batch(
        settings=settings,
        client=object(),
    )

    assert (
        selected_name
        == summary_names[1]
    )

    assert (
        selected_summary["status"]
        == "SUCCESS"
    )