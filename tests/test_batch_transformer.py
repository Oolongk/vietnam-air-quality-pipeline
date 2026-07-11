import json
from pathlib import Path

import pandas as pd

from src.transform.batch_transformer import (
    transform_raw_batch,
)


def build_raw_payload(
    point_id: str,
    location_id: str,
    latitude: float,
    longitude: float,
) -> dict:
    return {
        "schema_version": "1.0",
        "source": "open_meteo",
        "ingested_at": (
            "2026-07-11T05:00:00+00:00"
        ),
        "request": {
            "point_id": point_id,
            "location_id": location_id,
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "response": {
            "latitude": latitude,
            "longitude": longitude,
            "utc_offset_seconds": 25200,
            "hourly": {
                "time": [
                    "2026-07-11T12:00",
                    "2026-07-11T13:00",
                ],
                "pm2_5": [
                    18.5,
                    19.2,
                ],
                "pm10": [
                    27.4,
                    28.1,
                ],
                "carbon_monoxide": [
                    150.0,
                    152.0,
                ],
                "nitrogen_dioxide": [
                    8.5,
                    8.9,
                ],
                "sulphur_dioxide": [
                    2.1,
                    2.2,
                ],
                "ozone": [
                    70.0,
                    72.0,
                ],
                "us_aqi": [
                    61,
                    63,
                ],
                "us_aqi_pm2_5": [
                    59,
                    61,
                ],
                "us_aqi_pm10": [
                    30,
                    31,
                ],
            },
        },
    }


def write_json(
    path: Path,
    data: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        mode="w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            data,
            output_file,
            ensure_ascii=False,
            indent=2,
        )


def create_raw_batch(
    raw_root: Path,
) -> Path:
    batch_directory = (
        raw_root
        / "open_meteo"
        / "air_quality"
        / "date=2026-07-11"
        / "hour=12"
        / "batch_id=test_batch"
    )

    write_json(
        batch_directory
        / "run_summary.json",
        {
            "status": "SUCCESS",
            "batch_id": "test_batch",
            "partition_date": "2026-07-11",
            "partition_hour": "12",
            "succeeded_points": 2,
        },
    )

    write_json(
        batch_directory
        / "point_id=HN_CENTER"
        / "data.json",
        build_raw_payload(
            point_id="HN_CENTER",
            location_id="HN",
            latitude=21.0285,
            longitude=105.8542,
        ),
    )

    write_json(
        batch_directory
        / "point_id=HCM_CENTER"
        / "data.json",
        build_raw_payload(
            point_id="HCM_CENTER",
            location_id="HCM",
            latitude=10.7769,
            longitude=106.7009,
        ),
    )

    return batch_directory


def test_transform_raw_batch_creates_combined_parquet(
    tmp_path: Path,
) -> None:
    raw_root = tmp_path / "raw"
    transformed_root = tmp_path / "transformed"

    batch_directory = create_raw_batch(
        raw_root
    )

    summary = transform_raw_batch(
        raw_batch_directory=batch_directory,
        transformed_root=transformed_root,
    )

    assert summary["status"] == "SUCCESS"
    assert summary["discovered_raw_files"] == 2
    assert summary["succeeded_files"] == 2
    assert summary["failed_files"] == 0
    assert summary["records_transformed"] == 4
    assert summary["duplicate_key_rows"] == 0

    parquet_path = (
        transformed_root
        / summary["transformed_data_path"]
    )

    assert parquet_path.exists()

    dataframe = pd.read_parquet(
        parquet_path
    )

    assert len(dataframe) == 4
    assert dataframe["point_id"].nunique() == 2

    assert sorted(
        dataframe["point_id"].unique()
    ) == [
        "HCM_CENTER",
        "HN_CENTER",
    ]


def test_transform_raw_batch_reports_partial_success(
    tmp_path: Path,
) -> None:
    raw_root = tmp_path / "raw"
    transformed_root = tmp_path / "transformed"

    batch_directory = create_raw_batch(
        raw_root
    )

    invalid_payload_path = (
        batch_directory
        / "point_id=HCM_CENTER"
        / "data.json"
    )

    invalid_payload = build_raw_payload(
        point_id="HCM_CENTER",
        location_id="HCM",
        latitude=10.7769,
        longitude=106.7009,
    )

    invalid_payload["source"] = (
        "invalid_source"
    )

    write_json(
        invalid_payload_path,
        invalid_payload,
    )

    summary = transform_raw_batch(
        raw_batch_directory=batch_directory,
        transformed_root=transformed_root,
    )

    assert (
        summary["status"]
        == "PARTIAL_SUCCESS"
    )
    assert summary["succeeded_files"] == 1
    assert summary["failed_files"] == 1
    assert summary["records_transformed"] == 2
    assert len(summary["failures"]) == 1

    parquet_path = (
        transformed_root
        / summary["transformed_data_path"]
    )

    dataframe = pd.read_parquet(
        parquet_path
    )

    assert len(dataframe) == 2

    assert dataframe[
        "point_id"
    ].unique().tolist() == [
        "HN_CENTER"
    ]