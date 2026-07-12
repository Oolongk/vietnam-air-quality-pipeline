from datetime import datetime

import pandas as pd
import pytest

from src.load.timescaledb_loader import (
    TimescaleDBLoadError,
    prepare_air_quality_records,
)


def build_valid_dataframe() -> pd.DataFrame:
    dataframe = pd.DataFrame(
        [
            {
                "schema_version": "1.0",
                "point_id": "HN_CENTER",
                "location_id": "HN",
                "forecast_time": pd.Timestamp(
                    "2026-07-12 12:00:00",
                    tz="Asia/Ho_Chi_Minh",
                ),
                "latitude": 21.0285,
                "longitude": 105.8542,
                "grid_latitude": 21.0,
                "grid_longitude": 105.75,
                "pm2_5": 18.5,
                "pm10": 27.4,
                "carbon_monoxide": 150.0,
                "nitrogen_dioxide": 8.5,
                "sulphur_dioxide": 2.1,
                "ozone": 70.0,
                "us_aqi": 61,
                "us_aqi_pm2_5": 59,
                "us_aqi_pm10": pd.NA,
                "timezone": (
                    "Asia/Ho_Chi_Minh"
                ),
                "utc_offset_seconds": 25200,
                "source": "open_meteo",
                "ingested_at": pd.Timestamp(
                    "2026-07-12 05:00:00",
                    tz="UTC",
                ),
            },
            {
                "schema_version": "1.0",
                "point_id": "HCM_CENTER",
                "location_id": "HCM",
                "forecast_time": pd.Timestamp(
                    "2026-07-12 12:00:00",
                    tz="Asia/Ho_Chi_Minh",
                ),
                "latitude": 10.7769,
                "longitude": 106.7009,
                "grid_latitude": 10.75,
                "grid_longitude": 106.75,
                "pm2_5": 20.1,
                "pm10": 30.2,
                "carbon_monoxide": 160.0,
                "nitrogen_dioxide": 9.0,
                "sulphur_dioxide": 2.4,
                "ozone": 75.0,
                "us_aqi": 65,
                "us_aqi_pm2_5": 63,
                "us_aqi_pm10": 31,
                "timezone": (
                    "Asia/Ho_Chi_Minh"
                ),
                "utc_offset_seconds": 25200,
                "source": "open_meteo",
                "ingested_at": pd.Timestamp(
                    "2026-07-12 05:00:00",
                    tz="UTC",
                ),
            },
        ]
    )

    dataframe["us_aqi"] = (
        dataframe["us_aqi"]
        .astype("Int64")
    )

    dataframe["us_aqi_pm2_5"] = (
        dataframe["us_aqi_pm2_5"]
        .astype("Int64")
    )

    dataframe["us_aqi_pm10"] = (
        dataframe["us_aqi_pm10"]
        .astype("Int64")
    )

    return dataframe


def test_prepare_records_converts_pandas_types() -> None:
    dataframe = build_valid_dataframe()

    records = prepare_air_quality_records(
        dataframe
    )

    assert len(records) == 2

    first_record = records[0]

    assert (
        first_record["point_id"]
        == "HN_CENTER"
    )

    assert isinstance(
        first_record["forecast_time"],
        datetime,
    )

    assert (
        first_record[
            "forecast_time"
        ].tzinfo
        is not None
    )

    assert isinstance(
        first_record["us_aqi"],
        int,
    )

    assert (
        first_record["us_aqi_pm10"]
        is None
    )


def test_prepare_records_rejects_duplicates() -> None:
    dataframe = build_valid_dataframe()

    duplicate = (
        dataframe.iloc[[0]].copy()
    )

    dataframe = pd.concat(
        [
            dataframe,
            duplicate,
        ],
        ignore_index=True,
    )

    with pytest.raises(
        TimescaleDBLoadError,
        match="duplicate",
    ):
        prepare_air_quality_records(
            dataframe
        )


def test_prepare_records_rejects_missing_column() -> None:
    dataframe = build_valid_dataframe()

    dataframe = dataframe.drop(
        columns=["pm2_5"]
    )

    with pytest.raises(
        TimescaleDBLoadError,
        match="pm2_5",
    ):
        prepare_air_quality_records(
            dataframe
        )


def test_prepare_records_requires_timezone() -> None:
    dataframe = build_valid_dataframe()

    dataframe.loc[
        0,
        "forecast_time",
    ] = pd.Timestamp(
        "2026-07-12 12:00:00"
    )

    with pytest.raises(
        TimescaleDBLoadError,
        match="timezone",
    ):
        prepare_air_quality_records(
            dataframe
        )