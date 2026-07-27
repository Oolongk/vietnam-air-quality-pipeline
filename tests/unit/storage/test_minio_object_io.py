from __future__ import annotations

import pandas as pd
import pytest

from src.utils.minio_object_io import (
    MinioObjectIOError,
    deserialize_dataframe_parquet,
    deserialize_json,
    serialize_dataframe_parquet,
    serialize_json,
)


def test_json_round_trip_preserves_unicode() -> None:
    input_data = {
        "location_name": "Hà Nội",
        "aqi_level": "Trung bình",
        "us_aqi": 75,
    }

    payload = serialize_json(
        input_data
    )

    output_data = deserialize_json(
        payload
    )

    assert output_data == input_data

    assert (
        "Hà Nội".encode("utf-8")
        in payload
    )


def test_parquet_round_trip() -> None:
    input_dataframe = pd.DataFrame(
        [
            {
                "point_id": "HN_CENTER",
                "us_aqi": 75,
                "pm2_5": 18.5,
            },
            {
                "point_id": "HCM_CENTER",
                "us_aqi": 82,
                "pm2_5": 20.1,
            },
        ]
    )

    payload = (
        serialize_dataframe_parquet(
            input_dataframe
        )
    )

    output_dataframe = (
        deserialize_dataframe_parquet(
            payload
        )
    )

    pd.testing.assert_frame_equal(
        output_dataframe,
        input_dataframe,
        check_dtype=True,
    )


def test_rejects_invalid_json_bytes() -> None:
    with pytest.raises(
        MinioObjectIOError,
        match="JSON",
    ):
        deserialize_json(
            b"not valid json"
        )


def test_rejects_invalid_parquet_bytes() -> None:
    with pytest.raises(
        MinioObjectIOError,
        match="Parquet",
    ):
        deserialize_dataframe_parquet(
            b"not valid parquet"
        )


def test_rejects_non_dataframe() -> None:
    with pytest.raises(
        TypeError,
        match="DataFrame",
    ):
        serialize_dataframe_parquet(
            {"point_id": "HN_CENTER"}
        )