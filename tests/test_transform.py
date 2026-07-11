import pandas as pd
import pytest

from src.transform.air_quality_transform import (
    AirQualityTransformError,
    transform_open_meteo_payload,
)


def build_sample_payload() -> dict:
    return {
        "schema_version": "1.0",
        "source": "open_meteo",
        "ingested_at": (
            "2026-07-11T05:00:00+00:00"
        ),
        "request": {
            "point_id": "HN_CENTER",
            "location_id": "HN",
            "latitude": 21.0285,
            "longitude": 105.8542,
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "response": {
            "latitude": 21.0,
            "longitude": 105.75,
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


def test_transform_returns_one_row_per_time() -> None:
    payload = build_sample_payload()

    dataframe = transform_open_meteo_payload(
        payload
    )

    assert len(dataframe) == 2
    assert dataframe["point_id"].tolist() == [
        "HN_CENTER",
        "HN_CENTER",
    ]
    assert dataframe["location_id"].tolist() == [
        "HN",
        "HN",
    ]
    assert dataframe["source"].tolist() == [
        "open_meteo",
        "open_meteo",
    ]

    assert dataframe["pm2_5"].tolist() == [
        18.5,
        19.2,
    ]

    assert dataframe["us_aqi"].tolist() == [
        61,
        63,
    ]


def test_forecast_time_has_timezone() -> None:
    payload = build_sample_payload()

    dataframe = transform_open_meteo_payload(
        payload
    )

    assert pd.api.types.is_datetime64tz_dtype(
        dataframe["forecast_time"].dtype
    )

    assert (
        str(dataframe["forecast_time"].dt.tz)
        == "Asia/Ho_Chi_Minh"
    )


def test_transform_rejects_unequal_array_lengths() -> None:
    payload = build_sample_payload()

    payload["response"]["hourly"]["pm10"] = [
        27.4
    ]

    with pytest.raises(
        AirQualityTransformError,
        match="pm10",
    ):
        transform_open_meteo_payload(
            payload
        )


def test_transform_rejects_wrong_source() -> None:
    payload = build_sample_payload()

    payload["source"] = "unknown_source"

    with pytest.raises(
        AirQualityTransformError,
        match="open_meteo",
    ):
        transform_open_meteo_payload(
            payload
        )