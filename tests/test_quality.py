from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.quality.data_quality_checks import (
    run_air_quality_data_quality,
)
from src.quality.quality_processor import (
    process_transformed_batch_quality,
)


BATCH_ID = "test_batch"
PARTITION_DATE = "2026-07-11"
PARTITION_HOUR = "12"
FORECAST_TIME = "2026-07-11T12:00:00+07:00"
INGESTED_AT = "2026-07-11T12:00:00+07:00"


def build_monitoring_points() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "point_id": "HN_CENTER",
                "location_id": "HN",
                "point_name": "Hà Nội Center",
                "point_type": "urban_center",
                "latitude": 21.0285,
                "longitude": 105.8542,
                "is_active": True,
            },
            {
                "point_id": "HCM_CENTER",
                "location_id": "HCM",
                "point_name": "Hồ Chí Minh Center",
                "point_type": "urban_center",
                "latitude": 10.7769,
                "longitude": 106.7009,
                "is_active": True,
            },
        ]
    )


def build_locations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "location_id": "HN",
                "location_name": "Hà Nội",
                "region": "North",
                "admin_type": "municipality",
                "is_active": True,
            },
            {
                "location_id": "HCM",
                "location_name": "Hồ Chí Minh",
                "region": "South",
                "admin_type": "municipality",
                "is_active": True,
            },
        ]
    )


def build_valid_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "point_id": "HN_CENTER",
                "location_id": "HN",
                "point_name": "Hà Nội Center",
                "point_type": "urban_center",
                "latitude": 21.0285,
                "longitude": 105.8542,
                "forecast_time": FORECAST_TIME,
                "pm2_5": 15.5,
                "pm10": 25.3,
                "carbon_monoxide": 120.0,
                "nitrogen_dioxide": 8.0,
                "sulphur_dioxide": 4.0,
                "ozone": 35.0,
                "us_aqi": 55,
                "us_aqi_pm2_5": 55,
                "us_aqi_pm10": 25,
                "us_aqi_nitrogen_dioxide": 8,
                "us_aqi_carbon_monoxide": 4,
                "us_aqi_ozone": 18,
                "us_aqi_sulphur_dioxide": 3,
                "source": "open_meteo",
                "batch_id": BATCH_ID,
                "schema_version": "1.0",
                "ingested_at": INGESTED_AT,
            },
            {
                "point_id": "HCM_CENTER",
                "location_id": "HCM",
                "point_name": "Hồ Chí Minh Center",
                "point_type": "urban_center",
                "latitude": 10.7769,
                "longitude": 106.7009,
                "forecast_time": FORECAST_TIME,
                "pm2_5": 20.1,
                "pm10": 30.2,
                "carbon_monoxide": 150.0,
                "nitrogen_dioxide": 10.0,
                "sulphur_dioxide": 5.0,
                "ozone": 40.0,
                "us_aqi": 65,
                "us_aqi_pm2_5": 65,
                "us_aqi_pm10": 30,
                "us_aqi_nitrogen_dioxide": 10,
                "us_aqi_carbon_monoxide": 5,
                "us_aqi_ozone": 20,
                "us_aqi_sulphur_dioxide": 4,
                "source": "open_meteo",
                "batch_id": BATCH_ID,
                "schema_version": "1.0",
                "ingested_at": INGESTED_AT,
            },
        ]
    )


def run_quality(
    dataframe: pd.DataFrame,
):
    return run_air_quality_data_quality(
        dataframe=dataframe,
        monitoring_points=build_monitoring_points(),
        locations=build_locations(),
        expected_forecast_hours=1,
        freshness_minutes=90,
        coordinate_tolerance=0.001,
        expected_batch_id=BATCH_ID,
    )


def test_valid_records_pass_all_checks() -> None:
    result = run_quality(
        build_valid_dataframe()
    )

    assert result.quality_status == "PASS"
    assert result.pipeline_status == "SUCCESS"
    assert result.quality_score == 100.0
    assert result.total_records == 2
    assert result.valid_count == 2
    assert result.bad_count == 0


def test_invalid_record_contains_error_reasons() -> None:
    dataframe = build_valid_dataframe()

    dataframe.loc[0, "point_id"] = ""
    dataframe.loc[0, "pm2_5"] = -10.0
    dataframe.loc[0, "source"] = (
        "invalid_source"
    )

    result = run_quality(
        dataframe
    )

    assert result.bad_count >= 1

    error_codes = str(
        result.bad_records.loc[
            0,
            "dq_error_codes",
        ]
    )

    assert "POINT_ID_REQUIRED" in error_codes
    assert "PM2_5_NON_NEGATIVE" in error_codes
    assert "SOURCE_OPEN_METEO" in error_codes


def test_duplicate_rows_are_rejected() -> None:
    dataframe = build_valid_dataframe()

    dataframe = pd.concat(
        [
            dataframe,
            dataframe.iloc[[0]].copy(),
        ],
        ignore_index=True,
    )

    result = run_quality(
        dataframe
    )

    duplicate_rows = (
        result.bad_records[
            result.bad_records[
                "dq_error_codes"
            ]
            .astype(str)
            .str.contains(
                "UNIQUE_LOGICAL_KEY",
                regex=False,
            )
        ]
    )

    assert len(duplicate_rows) == 2
    assert result.quality_status == "FAIL"
    assert result.pipeline_status == "FAILED"


def test_quality_processor_writes_clean_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monitoring_points_path = (
        tmp_path
        / "monitoring_points.csv"
    )

    locations_path = (
        tmp_path
        / "locations.csv"
    )

    build_monitoring_points().to_csv(
        monitoring_points_path,
        index=False,
        encoding="utf-8",
    )

    build_locations().to_csv(
        locations_path,
        index=False,
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "MONITORING_POINTS_CONFIG_PATH",
        str(monitoring_points_path),
    )
    monkeypatch.setenv(
        "LOCATIONS_CONFIG_PATH",
        str(locations_path),
    )
    monkeypatch.setenv(
        "DQ_EXPECTED_FORECAST_HOURS",
        "1",
    )
    monkeypatch.setenv(
        "DQ_FRESHNESS_MINUTES",
        "90",
    )
    monkeypatch.setenv(
        "DQ_COORDINATE_TOLERANCE",
        "0.001",
    )

    transformed_batch = (
        tmp_path
        / "transformed"
        / "air_quality"
        / "hourly"
        / f"date={PARTITION_DATE}"
        / f"hour={PARTITION_HOUR}"
        / f"batch_id={BATCH_ID}"
    )

    transformed_batch.mkdir(
        parents=True,
        exist_ok=True,
    )

    build_valid_dataframe().to_parquet(
        transformed_batch
        / "data.parquet",
        engine="pyarrow",
        index=False,
    )

    (
        transformed_batch
        / "transform_summary.json"
    ).write_text(
        (
            "{\n"
            '  "status": "SUCCESS",\n'
            f'  "batch_id": "{BATCH_ID}",\n'
            f'  "partition_date": "{PARTITION_DATE}",\n'
            f'  "partition_hour": "{PARTITION_HOUR}"\n'
            "}"
        ),
        encoding="utf-8",
    )

    clean_root = tmp_path / "clean"
    quality_root = tmp_path / "quality"

    summary = (
        process_transformed_batch_quality(
            transformed_batch_directory=(
                transformed_batch
            ),
            clean_root=clean_root,
            quality_root=quality_root,
        )
    )

    clean_data_path = (
        clean_root
        / "air_quality"
        / "hourly"
        / f"date={PARTITION_DATE}"
        / f"hour={PARTITION_HOUR}"
        / f"batch_id={BATCH_ID}"
        / "data.parquet"
    )

    quality_summary_path = (
        quality_root
        / "air_quality"
        / "hourly"
        / f"date={PARTITION_DATE}"
        / f"hour={PARTITION_HOUR}"
        / f"batch_id={BATCH_ID}"
        / "data_quality_summary.json"
    )

    assert summary["status"] == "SUCCESS"
    assert summary["batch_id"] == BATCH_ID
    assert summary["input_records"] == 2
    assert summary["valid_records"] == 2
    assert summary["bad_records"] == 0
    assert clean_data_path.exists()
    assert quality_summary_path.exists()

    clean_dataframe = pd.read_parquet(
        clean_data_path,
        engine="pyarrow",
    )

    assert len(clean_dataframe) == 2