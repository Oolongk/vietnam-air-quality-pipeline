from __future__ import annotations

import pandas as pd
import pytest

from src.snapshot.minio_mart_snapshot_reader import (
    MartSnapshotValidationError,
    MinioMartSnapshotReader,
)
from src.utils.minio_client import MinioSettings

BATCH_ID = "20260801T134416Z_airflow"
SUMMARY_OBJECT = (
    "air_quality/build_summary/date=2026-08-01/hour=20/"
    f"batch_id={BATCH_ID}/mart_summary.json"
)


def _settings() -> MinioSettings:
    return MinioSettings(
        endpoint="minio:9000",
        access_key="access",
        secret_key="secret",
        secure=False,
        raw_bucket="air-quality-raw",
        clean_bucket="air-quality-clean",
        mart_bucket="air-quality-mart",
    )


def _summary() -> dict[str, object]:
    prefix = "air_quality"
    partition = f"date=2026-08-01/hour=20/batch_id={BATCH_ID}"
    return {
        "status": "SUCCESS",
        "batch_id": BATCH_ID,
        "current_aqi_rows": 1,
        "location_summary_rows": 1,
        "daily_summary_rows": 1,
        "finished_at": "2026-08-01T14:02:21+00:00",
        "outputs": {
            "current_aqi": f"{prefix}/current_aqi/{partition}/data.parquet",
            "location_summary": (f"{prefix}/location_summary/{partition}/data.parquet"),
            "daily_summary": f"{prefix}/daily_summary/{partition}/data.parquet",
            "mart_summary": SUMMARY_OBJECT,
        },
    }


def _current_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "point_id": "HN_CENTER",
                "location_id": "HN",
                "location_name": "Hà Nội",
                "region": "Miền Bắc",
                "point_name": "Trung tâm Hà Nội",
                "point_type": "urban_center",
                "latitude": 21.0,
                "longitude": 105.8,
                "forecast_time": pd.Timestamp("2026-08-01T21:00:00+07:00"),
                "us_aqi": 146,
                "aqi_level": "Unhealthy for Sensitive Groups",
                "aqi_severity": 3,
                "pm2_5": 54.7,
                "pm10": 54.9,
                "carbon_monoxide": 710.0,
                "nitrogen_dioxide": 49.0,
                "sulphur_dioxide": 38.1,
                "ozone": 52.0,
                "source": "open_meteo",
                "source_batch_id": BATCH_ID,
                "schema_version": "1.0",
                "source_ingested_at": pd.Timestamp("2026-08-01T14:00:16+00:00"),
                "mart_created_at": pd.Timestamp("2026-08-01T14:02:18+00:00"),
            }
        ]
    )


def _location_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "location_id": "HN",
                "location_name": "Hà Nội",
                "region": "Miền Bắc",
                "monitoring_point_count": 3,
                "forecast_time": pd.Timestamp("2026-08-01T21:00:00+07:00"),
                "average_us_aqi": 135.67,
                "minimum_us_aqi": 125,
                "maximum_us_aqi": 146,
                "average_pm2_5": 55.43,
                "maximum_pm2_5": 56.3,
                "average_pm10": 55.87,
                "maximum_pm10": 56.7,
                "average_ozone": 39.0,
                "maximum_ozone": 52.0,
                "latitude": 21.05,
                "longitude": 105.71,
                "source_batch_count": 1,
                "worst_point_id": "HN_SON_TAY",
                "worst_point_name": "Sơn Tây",
                "worst_point_us_aqi": 146,
                "aqi_level": "Unhealthy for Sensitive Groups",
                "aqi_severity": 3,
                "mart_created_at": pd.Timestamp("2026-08-01T14:02:18+00:00"),
            }
        ]
    )


def _daily_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "forecast_date": "2026-08-02",
                "point_id": "HN_CENTER",
                "location_id": "HN",
                "location_name": "Hà Nội",
                "region": "Miền Bắc",
                "point_name": "Trung tâm Hà Nội",
                "point_type": "urban_center",
                "latitude": 21.0,
                "longitude": 105.8,
                "first_forecast_time": pd.Timestamp("2026-08-02T00:00:00+07:00"),
                "last_forecast_time": pd.Timestamp("2026-08-02T20:00:00+07:00"),
                "available_hours": 21,
                "average_us_aqi": 135.43,
                "minimum_us_aqi": 114,
                "maximum_us_aqi": 199,
                "average_pm2_5": 45.67,
                "maximum_pm2_5": 81.7,
                "average_pm10": 46.74,
                "maximum_pm10": 81.7,
                "average_ozone": 106.62,
                "maximum_ozone": 257.0,
                "good_hours": 0,
                "moderate_hours": 0,
                "sensitive_group_hours": 17,
                "unhealthy_hours": 4,
                "very_unhealthy_hours": 0,
                "hazardous_hours": 0,
                "source_batch_count": 1,
                "latest_source_ingested_at": pd.Timestamp("2026-08-01T14:00:19+00:00"),
                "worst_forecast_time": pd.Timestamp("2026-08-02T20:00:00+07:00"),
                "worst_hour_source_batch_id": BATCH_ID,
                "aqi_level": "Unhealthy",
                "aqi_severity": 4,
                "coverage_status": "PARTIAL",
                "mart_created_at": pd.Timestamp("2026-08-01T14:02:18+00:00"),
            }
        ]
    )


def test_reader_uses_summary_outputs_and_adds_compatibility_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = _summary()
    dataframes = {
        summary["outputs"]["current_aqi"]: _current_dataframe(),
        summary["outputs"]["location_summary"]: _location_dataframe(),
        summary["outputs"]["daily_summary"]: _daily_dataframe(),
    }

    monkeypatch.setattr(
        "src.snapshot.minio_mart_snapshot_reader.list_object_names",
        lambda **_: [SUMMARY_OBJECT],
    )
    monkeypatch.setattr(
        "src.snapshot.minio_mart_snapshot_reader.get_json_object",
        lambda **_: summary,
    )
    monkeypatch.setattr(
        "src.snapshot.minio_mart_snapshot_reader.get_parquet_object",
        lambda object_name, **_: dataframes[object_name].copy(),
    )

    reader = MinioMartSnapshotReader(
        settings=_settings(),
        client=object(),
        expected_batch_id=BATCH_ID,
    )
    bundle = reader.read()

    assert bundle.batch_id == BATCH_ID
    assert bundle.current_aqi[0]["batch_id"] == BATCH_ID
    assert bundle.current_aqi[0]["ingested_at"].endswith("+00:00")
    assert bundle.daily_summary[0]["forecast_time"].endswith("+07:00")
    assert bundle.daily_summary[0]["us_aqi"] == 135.43


def test_reader_rejects_wrong_current_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = _summary()
    current = _current_dataframe()
    current.loc[0, "source_batch_id"] = "wrong_batch"
    dataframes = {
        summary["outputs"]["current_aqi"]: current,
        summary["outputs"]["location_summary"]: _location_dataframe(),
        summary["outputs"]["daily_summary"]: _daily_dataframe(),
    }

    monkeypatch.setattr(
        "src.snapshot.minio_mart_snapshot_reader.list_object_names",
        lambda **_: [SUMMARY_OBJECT],
    )
    monkeypatch.setattr(
        "src.snapshot.minio_mart_snapshot_reader.get_json_object",
        lambda **_: summary,
    )
    monkeypatch.setattr(
        "src.snapshot.minio_mart_snapshot_reader.get_parquet_object",
        lambda object_name, **_: dataframes[object_name].copy(),
    )

    reader = MinioMartSnapshotReader(
        settings=_settings(),
        client=object(),
        expected_batch_id=BATCH_ID,
    )

    with pytest.raises(
        MartSnapshotValidationError,
        match="source_batch_id",
    ):
        reader.read()
