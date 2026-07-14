from __future__ import annotations

import pandas as pd
import pytest

from src.load.minio_timescaledb_loader import (
    MinioTimescaleDBLoadError,
    prepare_fact_dataframe,
)

def build_valid_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "point_id": "HN_CENTER",
                "location_id": "HN",
                "forecast_time": (
                    "2026-07-13T21:00:00+07:00"
                ),
                "latitude": 21.0285,
                "longitude": 105.8542,
                "pm2_5": 62.6,
                "pm10": 63.1,
                "us_aqi": 181,
                "source": "open_meteo",
                "batch_id": "test_batch",
                "ingested_at": (
                    "2026-07-13T14:20:00+00:00"
                ),
            },
            {
                "point_id": "HCM_CENTER",
                "location_id": "HCM",
                "forecast_time": (
                    "2026-07-13T21:00:00+07:00"
                ),
                "latitude": 10.7769,
                "longitude": 106.7009,
                "pm2_5": 43.2,
                "pm10": 44.8,
                "us_aqi": 92,
                "source": "open_meteo",
                "batch_id": "test_batch",
                "ingested_at": (
                    "2026-07-13T14:20:00+00:00"
                ),
            },
        ]
    )


def test_prepare_fact_dataframe() -> None:
    dataframe = prepare_fact_dataframe(
        build_valid_dataframe()
    )

    assert len(dataframe) == 2

    assert str(
        dataframe[
            "forecast_time"
        ].dt.tz
    ) == "UTC"

    assert str(
        dataframe[
            "ingested_at"
        ].dt.tz
    ) == "UTC"

    assert dataframe[
        "latitude"
    ].tolist() == [
        21.0285,
        10.7769,
    ]

    assert dataframe[
        "longitude"
    ].tolist() == [
        105.8542,
        106.7009,
    ]

def test_rejects_duplicate_logical_key() -> None:
    dataframe = (
        build_valid_dataframe()
        .iloc[
            [0, 0]
        ]
        .reset_index(drop=True)
    )

    with pytest.raises(
        MinioTimescaleDBLoadError,
        match="duplicate",
    ):
        prepare_fact_dataframe(
            dataframe
        )


def test_rejects_missing_required_column() -> None:
    dataframe = (
        build_valid_dataframe()
        .drop(
            columns=[
                "point_id"
            ]
        )
    )

    with pytest.raises(
        MinioTimescaleDBLoadError,
        match="thiếu",
    ):
        prepare_fact_dataframe(
            dataframe
        )