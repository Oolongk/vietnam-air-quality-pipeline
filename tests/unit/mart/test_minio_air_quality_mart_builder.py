from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

import src.mart.minio_air_quality_mart_builder as mart


OBJECT_NAME = (
    "clean/air_quality/hourly/"
    "date=2026-07-25/"
    "hour=02/"
    "batch_id=BATCH_1/"
    "data.parquet"
)


def make_clean_row(
    *,
    point_id: str = "HN_POINT_1",
    location_id: str = "HN",
    point_name: str = "Hà Nội Point 1",
    forecast_time: str = (
        "2026-07-25T09:00:00+07:00"
    ),
    ingested_at: str = (
        "2026-07-25T02:15:00+00:00"
    ),
    us_aqi: int = 50,
    batch_id: str = "BATCH_1",
    latitude: float = 21.0285,
    longitude: float = 105.8542,
    pm2_5: float = 15.0,
    pm10: float = 25.0,
    ozone: float = 30.0,
) -> dict[str, Any]:
    return {
        "point_id": point_id,
        "location_id": location_id,
        "point_name": point_name,
        "point_type": "urban_center",
        "latitude": latitude,
        "longitude": longitude,
        "forecast_time": forecast_time,
        "pm2_5": pm2_5,
        "pm10": pm10,
        "carbon_monoxide": 100.0,
        "nitrogen_dioxide": 10.0,
        "sulphur_dioxide": 5.0,
        "ozone": ozone,
        "us_aqi": us_aqi,
        "source": "open_meteo",
        "batch_id": batch_id,
        "schema_version": "1.0",
        "ingested_at": ingested_at,
    }


def prepare_enriched_dataframe(
    rows: list[dict[str, Any]],
) -> pd.DataFrame:
    normalized = mart._normalize_clean(
        pd.DataFrame(rows),
        OBJECT_NAME,
    )

    location_dimension = pd.DataFrame(
        [
            {
                "location_id": "HN",
                "location_name": "Hà Nội",
                "region": "Northern Vietnam",
            }
        ]
    )

    return mart._enrich_locations(
        normalized,
        location_dimension,
    )


def test_partition_parts_parses_clean_object() -> None:
    result = mart._partition_parts(
        OBJECT_NAME
    )

    assert result == (
        "2026-07-25",
        "02",
        "BATCH_1",
    )


def test_partition_parts_rejects_invalid_object() -> None:
    with pytest.raises(
        mart.MinioMartBuildError,
        match="không đúng partition Clean",
    ):
        mart._partition_parts(
            "clean/invalid/data.parquet"
        )


def test_normalize_clean_converts_timezones() -> None:
    dataframe = pd.DataFrame(
        [
            make_clean_row(),
        ]
    )

    result = mart._normalize_clean(
        dataframe,
        OBJECT_NAME,
    )

    assert str(
        result["forecast_time"].dt.tz
    ) == "Asia/Ho_Chi_Minh"

    assert str(
        result["ingested_at"].dt.tz
    ) == "UTC"


def test_normalize_clean_rejects_logical_duplicate() -> None:
    duplicate_row = make_clean_row()

    dataframe = pd.DataFrame(
        [
            duplicate_row,
            duplicate_row.copy(),
        ]
    )

    with pytest.raises(
        mart.MinioMartBuildError,
        match="logical duplicate",
    ):
        mart._normalize_clean(
            dataframe,
            OBJECT_NAME,
        )


def test_load_location_dimension_preserves_na_id(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    location_path = (
        tmp_path
        / "locations.csv"
    )

    pd.DataFrame(
        [
            {
                "location_id": "HN",
                "location_name": "Hà Nội",
                "region": "Northern Vietnam",
                "is_active": True,
            },
            {
                "location_id": "NA",
                "location_name": "Nghệ An",
                "region": (
                    "North Central Vietnam"
                ),
                "is_active": True,
            },
        ]
    ).to_csv(
        location_path,
        index=False,
        encoding="utf-8-sig",
    )

    monkeypatch.setattr(
        mart,
        "LOCATION_CONFIG",
        location_path,
    )

    result = (
        mart._load_location_dimension()
    )

    assert "NA" in set(
        result["location_id"]
    )

    nghe_an = result.loc[
        result["location_id"] == "NA"
    ].iloc[0]

    assert nghe_an[
        "location_name"
    ] == "Nghệ An"


def test_current_aqi_prefers_future_when_tied() -> None:
    dataframe = prepare_enriched_dataframe(
        [
            make_clean_row(
                forecast_time=(
                    "2026-07-25T08:00:00"
                    "+07:00"
                ),
                us_aqi=40,
            ),
            make_clean_row(
                forecast_time=(
                    "2026-07-25T10:00:00"
                    "+07:00"
                ),
                us_aqi=80,
            ),
        ]
    )

    result = mart.build_current_aqi(
        dataframe,
        datetime(
            2026,
            7,
            25,
            3,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert len(result) == 1

    assert result.iloc[0][
        "forecast_time"
    ] == pd.Timestamp(
        "2026-07-25T10:00:00+07:00"
    )

    assert result.iloc[0][
        "us_aqi"
    ] == 80

    assert result.iloc[0][
        "aqi_level"
    ] == "Moderate"


def test_location_summary_aggregates_three_points() -> None:
    dataframe = prepare_enriched_dataframe(
        [
            make_clean_row(
                point_id="HN_POINT_1",
                point_name="Point 1",
                us_aqi=40,
                pm2_5=10.0,
            ),
            make_clean_row(
                point_id="HN_POINT_2",
                point_name="Point 2",
                us_aqi=70,
                latitude=21.05,
                longitude=105.82,
                pm2_5=20.0,
            ),
            make_clean_row(
                point_id="HN_POINT_3",
                point_name="Point 3",
                us_aqi=120,
                latitude=21.08,
                longitude=105.80,
                pm2_5=30.0,
            ),
        ]
    )

    mart_created_at = datetime(
        2026,
        7,
        25,
        3,
        0,
        tzinfo=timezone.utc,
    )

    current_aqi = mart.build_current_aqi(
        dataframe,
        mart_created_at,
    )

    result = mart.build_location_summary(
        current_aqi,
        mart_created_at,
    )

    assert len(result) == 1

    summary = result.iloc[0]

    assert summary[
        "monitoring_point_count"
    ] == 3

    assert float(
        summary["average_us_aqi"]
    ) == pytest.approx(
        76.67
    )

    assert summary[
        "maximum_us_aqi"
    ] == 120

    assert summary[
        "worst_point_id"
    ] == "HN_POINT_3"

    assert summary[
        "aqi_level"
    ] == (
        "Unhealthy for Sensitive Groups"
    )


def test_daily_summary_keeps_latest_duplicate_hour() -> None:
    dataframe = prepare_enriched_dataframe(
        [
            make_clean_row(
                batch_id="BATCH_OLD",
                ingested_at=(
                    "2026-07-25T01:00:00"
                    "+00:00"
                ),
                us_aqi=40,
            ),
            make_clean_row(
                batch_id="BATCH_NEW",
                ingested_at=(
                    "2026-07-25T02:00:00"
                    "+00:00"
                ),
                us_aqi=80,
            ),
        ]
    )

    result = mart.build_daily_summary(
        dataframe,
        datetime(
            2026,
            7,
            25,
            3,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert len(result) == 1

    summary = result.iloc[0]

    assert summary[
        "available_hours"
    ] == 1

    assert summary[
        "average_us_aqi"
    ] == 80

    assert summary[
        "maximum_us_aqi"
    ] == 80

    assert summary[
        "source_batch_count"
    ] == 1

    assert summary[
        "worst_hour_source_batch_id"
    ] == "BATCH_NEW"

    assert summary[
        "coverage_status"
    ] == "PARTIAL"


def test_build_latest_mart_writes_expected_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean_dataframe = pd.DataFrame(
        [
            make_clean_row(
                point_id="HN_POINT_1",
                point_name="Point 1",
                us_aqi=50,
            ),
            make_clean_row(
                point_id="HN_POINT_2",
                point_name="Point 2",
                us_aqi=90,
                latitude=21.05,
                longitude=105.82,
            ),
        ]
    )

    location_dimension = pd.DataFrame(
        [
            {
                "location_id": "HN",
                "location_name": "Hà Nội",
                "region": "Northern Vietnam",
            }
        ]
    )

    parquet_writes: dict[
        str,
        pd.DataFrame,
    ] = {}

    json_writes: dict[
        str,
        dict[str, Any],
    ] = {}

    monkeypatch.setattr(
        mart,
        "_find_clean_objects",
        lambda settings, client: [
            OBJECT_NAME,
        ],
    )

    monkeypatch.setattr(
        mart,
        "_read_parquet",
        lambda client, bucket, name: (
            clean_dataframe.copy()
        ),
    )

    monkeypatch.setattr(
        mart,
        "_load_location_dimension",
        lambda: (
            location_dimension.copy()
        ),
    )

    def fake_put_parquet(
        client,
        bucket_name: str,
        object_name: str,
        dataframe: pd.DataFrame,
    ) -> None:
        assert bucket_name == "mart-bucket"

        parquet_writes[
            object_name
        ] = dataframe.copy()

    def fake_put_json(
        client,
        bucket_name: str,
        object_name: str,
        value: dict[str, Any],
    ) -> None:
        assert bucket_name == "mart-bucket"

        json_writes[
            object_name
        ] = value.copy()

    monkeypatch.setattr(
        mart,
        "_put_parquet",
        fake_put_parquet,
    )

    monkeypatch.setattr(
        mart,
        "_put_json",
        fake_put_json,
    )

    fixed_time = datetime(
        2026,
        7,
        25,
        3,
        0,
        tzinfo=timezone.utc,
    )

    monkeypatch.setattr(
        mart,
        "_utc_now",
        lambda: fixed_time,
    )

    settings = SimpleNamespace(
        clean_bucket="clean-bucket",
        mart_bucket="mart-bucket",
    )

    summary = mart.build_latest_minio_mart(
        settings=settings,
        client=object(),
    )

    assert summary["status"] == "SUCCESS"
    assert summary["batch_id"] == "BATCH_1"

    assert summary[
        "latest_clean_records"
    ] == 2

    assert summary[
        "history_input_records"
    ] == 2

    assert summary[
        "current_aqi_rows"
    ] == 2

    assert summary[
        "location_summary_rows"
    ] == 1

    assert summary[
        "daily_summary_rows"
    ] == 2

    assert summary[
        "output_records"
    ] == 5

    assert set(
        parquet_writes
    ) == {
        summary["outputs"][
            "current_aqi"
        ],
        summary["outputs"][
            "location_summary"
        ],
        summary["outputs"][
            "daily_summary"
        ],
    }

    mart_summary_key = (
        summary["outputs"][
            "mart_summary"
        ]
    )

    assert mart_summary_key in (
        json_writes
    )

    assert json_writes[
        mart_summary_key
    ]["status"] == "SUCCESS"