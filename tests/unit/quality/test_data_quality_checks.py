from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.quality.data_quality_checks import (
    DataQualityConfigurationError,
    DataQualitySchemaError,
    run_air_quality_data_quality,
)


BATCH_ID = "20260720T120000Z_test"


def _monitoring_points() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "point_id": "P1",
                "location_id": "L1",
                "point_name": "Point 1",
                "point_type": "urban_center",
                "latitude": 21.0,
                "longitude": 105.0,
                "is_active": True,
            },
            {
                "point_id": "P2",
                "location_id": "L2",
                "point_name": "Point 2",
                "point_type": "urban_center",
                "latitude": 10.0,
                "longitude": 106.0,
                "is_active": True,
            },
        ]
    )


def _locations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "location_id": "L1",
                "location_name": "Location 1",
                "region": "North",
                "admin_type": "City",
                "is_active": True,
            },
            {
                "location_id": "L2",
                "location_name": "Location 2",
                "region": "South",
                "admin_type": "City",
                "is_active": True,
            },
        ]
    )


def _valid_dataframe(
    forecast_hours: int = 3,
    freshness_offset_hours: int = 0,
) -> pd.DataFrame:
    forecast_start = datetime(
        2026,
        7,
        20,
        12,
        0,
        tzinfo=timezone.utc,
    )

    ingested_at = (
        forecast_start
        + timedelta(
            hours=freshness_offset_hours
        )
    )

    point_rows = [
        (
            "P1",
            "L1",
            "Point 1",
            21.0,
            105.0,
        ),
        (
            "P2",
            "L2",
            "Point 2",
            10.0,
            106.0,
        ),
    ]

    rows: list[dict[str, object]] = []

    for (
        point_id,
        location_id,
        point_name,
        latitude,
        longitude,
    ) in point_rows:
        for hour_index in range(
            forecast_hours
        ):
            rows.append(
                {
                    "point_id": point_id,
                    "location_id": location_id,
                    "point_name": point_name,
                    "point_type": "urban_center",
                    "latitude": latitude,
                    "longitude": longitude,
                    "forecast_time": (
                        forecast_start
                        + timedelta(
                            hours=hour_index
                        )
                    ).isoformat(),
                    "pm2_5": 10.0,
                    "pm10": 20.0,
                    "carbon_monoxide": 100.0,
                    "nitrogen_dioxide": 5.0,
                    "sulphur_dioxide": 3.0,
                    "ozone": 30.0,
                    "us_aqi": 42.0,
                    "us_aqi_pm2_5": 42.0,
                    "us_aqi_pm10": 20.0,
                    "us_aqi_nitrogen_dioxide": 5.0,
                    "us_aqi_carbon_monoxide": 3.0,
                    "us_aqi_ozone": 15.0,
                    "us_aqi_sulphur_dioxide": 2.0,
                    "source": "open_meteo",
                    "batch_id": BATCH_ID,
                    "schema_version": "1.0",
                    "ingested_at": (
                        ingested_at.isoformat()
                    ),
                }
            )

    return pd.DataFrame(rows)


def _check_by_name(
    checks: list[dict[str, object]],
    check_name: str,
) -> dict[str, object]:
    return next(
        check
        for check in checks
        if check["check_name"]
        == check_name
    )


def test_valid_batch_passes_with_score_100() -> None:
    result = run_air_quality_data_quality(
        dataframe=_valid_dataframe(),
        monitoring_points=(
            _monitoring_points()
        ),
        locations=_locations(),
        expected_forecast_hours=3,
        expected_batch_id=BATCH_ID,
    )

    assert result.quality_status == "PASS"
    assert result.pipeline_status == "SUCCESS"
    assert result.quality_score == 100.0
    assert result.total_records == 6
    assert result.valid_count == 6
    assert result.bad_count == 0
    assert result.expected_records == 6
    assert result.expected_active_points == 2
    assert result.actual_active_points == 2
    assert result.warning_check_count == 0
    assert result.failed_check_count == 0


def test_negative_pollutant_creates_bad_record_and_warn() -> None:
    dataframe = _valid_dataframe()
    dataframe.loc[0, "pm2_5"] = -1.0

    result = run_air_quality_data_quality(
        dataframe=dataframe,
        monitoring_points=(
            _monitoring_points()
        ),
        locations=_locations(),
        expected_forecast_hours=3,
        expected_batch_id=BATCH_ID,
    )

    check = _check_by_name(
        result.row_checks,
        "PM2_5_NON_NEGATIVE",
    )

    assert result.quality_status == "WARN"
    assert (
        result.pipeline_status
        == "PARTIAL_SUCCESS"
    )
    assert result.valid_count == 5
    assert result.bad_count == 1
    assert check["status"] == "FAILED"
    assert check["bad_records_count"] == 1
    assert (
        "PM2_5_NON_NEGATIVE"
        in result.bad_records.loc[
            0,
            "dq_error_codes",
        ]
    )


def test_missing_forecast_hour_fails_batch() -> None:
    dataframe = (
        _valid_dataframe()
        .iloc[:-1]
        .reset_index(drop=True)
    )

    result = run_air_quality_data_quality(
        dataframe=dataframe,
        monitoring_points=(
            _monitoring_points()
        ),
        locations=_locations(),
        expected_forecast_hours=3,
        expected_batch_id=BATCH_ID,
    )

    record_count_check = _check_by_name(
        result.batch_checks,
        "EXPECTED_RECORD_COUNT",
    )

    hours_check = _check_by_name(
        result.batch_checks,
        "EXPECTED_FORECAST_HOURS_PER_POINT",
    )

    assert result.quality_status == "FAIL"
    assert result.pipeline_status == "FAILED"
    assert result.quality_score <= 69.99
    assert record_count_check["status"] == "FAILED"
    assert hours_check["status"] == "FAILED"


def test_duplicate_logical_key_marks_both_rows_bad() -> None:
    dataframe = _valid_dataframe()
    dataframe = pd.concat(
        [
            dataframe,
            dataframe.iloc[[0]],
        ],
        ignore_index=True,
    )

    result = run_air_quality_data_quality(
        dataframe=dataframe,
        monitoring_points=(
            _monitoring_points()
        ),
        locations=_locations(),
        expected_forecast_hours=3,
        expected_batch_id=BATCH_ID,
    )

    duplicate_check = _check_by_name(
        result.row_checks,
        "UNIQUE_LOGICAL_KEY",
    )

    assert duplicate_check["status"] == "FAILED"
    assert duplicate_check["bad_records_count"] == 2
    assert result.bad_count == 2
    assert result.quality_status == "FAIL"


def test_freshness_issue_is_warning_not_row_rejection() -> None:
    result = run_air_quality_data_quality(
        dataframe=_valid_dataframe(
            freshness_offset_hours=5
        ),
        monitoring_points=(
            _monitoring_points()
        ),
        locations=_locations(),
        expected_forecast_hours=3,
        freshness_minutes=90,
        expected_batch_id=BATCH_ID,
    )

    freshness_check = _check_by_name(
        result.batch_checks,
        "DATA_FRESHNESS",
    )

    assert freshness_check["status"] == "WARNED"
    assert result.bad_count == 0
    assert result.valid_count == 6
    assert result.quality_status == "WARN"
    assert (
        result.pipeline_status
        == "PARTIAL_SUCCESS"
    )
    assert result.quality_score < 100.0


def test_missing_required_column_raises_schema_error() -> None:
    dataframe = _valid_dataframe().drop(
        columns=["pm2_5"]
    )

    with pytest.raises(
        DataQualitySchemaError,
        match="pm2_5",
    ):
        run_air_quality_data_quality(
            dataframe=dataframe,
            monitoring_points=(
                _monitoring_points()
            ),
            locations=_locations(),
            expected_forecast_hours=3,
        )


def test_orphan_active_point_raises_config_error() -> None:
    monitoring_points = (
        _monitoring_points()
    )
    monitoring_points.loc[
        0,
        "location_id",
    ] = "UNKNOWN"

    with pytest.raises(
        DataQualityConfigurationError,
        match="không active hoặc không tồn tại",
    ):
        run_air_quality_data_quality(
            dataframe=_valid_dataframe(),
            monitoring_points=(
                monitoring_points
            ),
            locations=_locations(),
            expected_forecast_hours=3,
        )
