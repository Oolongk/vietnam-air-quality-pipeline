from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

import src.load.minio_timescaledb_loader as loader


QUALITY_SUMMARY_OBJECT = (
    "quality/air_quality/hourly/"
    "date=2026-07-25/"
    "hour=02/"
    "batch_id=BATCH_1/"
    "data_quality_summary.json"
)

CLEAN_OBJECT = (
    "clean/air_quality/hourly/"
    "date=2026-07-25/"
    "hour=02/"
    "batch_id=BATCH_1/"
    "data.parquet"
)


class FakeConnection:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        self.close_count += 1


class FakeDatabaseSettings:
    def __init__(
        self,
        connection: FakeConnection,
    ) -> None:
        self.connection = connection
        self.connect_count = 0

    def connect(
        self,
    ) -> FakeConnection:
        self.connect_count += 1
        return self.connection


def build_minio_settings() -> SimpleNamespace:
    return SimpleNamespace(
        clean_bucket="air-quality-clean",
        mart_bucket="air-quality-mart",
    )


def build_quality_summary() -> dict[str, Any]:
    return {
        "status": "SUCCESS",
        "quality_status": "PASSED",
        "batch_id": "BATCH_1",
        "partition_date": "2026-07-25",
        "partition_hour": "02",
        "valid_records": 2,
        "clean_object_name": CLEAN_OBJECT,
        "finished_at": (
            "2026-07-25T02:30:00+00:00"
        ),
    }


def build_clean_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "point_id": "HN_CENTER",
                "location_id": "HN",
                "forecast_time": (
                    "2026-07-25T09:00:00+07:00"
                ),
                "latitude": 21.0285,
                "longitude": 105.8542,
                "source": "open_meteo",
                "batch_id": "BATCH_1",
                "ingested_at": (
                    "2026-07-25T02:15:00+00:00"
                ),
            },
            {
                "point_id": "HCM_CENTER",
                "location_id": "HCM",
                "forecast_time": (
                    "2026-07-25T09:00:00+07:00"
                ),
                "latitude": 10.7769,
                "longitude": 106.7009,
                "source": "open_meteo",
                "batch_id": "BATCH_1",
                "ingested_at": (
                    "2026-07-25T02:15:00+00:00"
                ),
            },
        ]
    )


def test_load_latest_clean_batch_commits_and_writes_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minio_settings = (
        build_minio_settings()
    )

    minio_client = object()

    connection = FakeConnection()

    database_settings = (
        FakeDatabaseSettings(
            connection
        )
    )

    clean_dataframe = (
        build_clean_dataframe()
    )

    ensure_calls: list[
        dict[str, Any]
    ] = []

    parquet_calls: list[
        dict[str, Any]
    ] = []

    upsert_calls: list[
        dict[str, Any]
    ] = []

    json_writes: list[
        dict[str, Any]
    ] = []

    monkeypatch.setattr(
        loader,
        "ensure_buckets",
        lambda **kwargs: (
            ensure_calls.append(
                kwargs
            )
        ),
    )

    monkeypatch.setattr(
        loader,
        "find_latest_loadable_quality_batch",
        lambda **kwargs: (
            QUALITY_SUMMARY_OBJECT,
            build_quality_summary(),
        ),
    )

    def fake_get_parquet_object(
        **kwargs: Any,
    ) -> pd.DataFrame:
        parquet_calls.append(
            kwargs
        )

        return clean_dataframe.copy()

    monkeypatch.setattr(
        loader,
        "get_parquet_object",
        fake_get_parquet_object,
    )

    def fake_upsert_fact_dataframe(
        **kwargs: Any,
    ) -> dict[str, Any]:
        upsert_calls.append(
            kwargs
        )

        return {
            "processed_rows": 2,
            "inserted_rows": 1,
            "updated_rows": 1,
            "database_columns": [
                "point_id",
                "location_id",
                "forecast_time",
                "source",
                "batch_id",
            ],
            "time_column": (
                "forecast_time"
            ),
        }

    monkeypatch.setattr(
        loader,
        "upsert_fact_dataframe",
        fake_upsert_fact_dataframe,
    )

    def fake_put_json_object(
        **kwargs: Any,
    ) -> dict[str, Any]:
        json_writes.append(
            kwargs
        )

        return {
            "size_bytes": 800,
        }

    monkeypatch.setattr(
        loader,
        "put_json_object",
        fake_put_json_object,
    )

    summary = (
        loader
        .load_latest_minio_clean_batch(
            minio_settings=(
                minio_settings
            ),
            minio_client=(
                minio_client
            ),
            database_settings=(
                database_settings
            ),
        )
    )

    assert len(ensure_calls) == 1

    assert ensure_calls[0][
        "settings"
    ] is minio_settings

    assert ensure_calls[0][
        "client"
    ] is minio_client

    assert len(parquet_calls) == 1

    assert parquet_calls[0][
        "bucket_name"
    ] == "air-quality-clean"

    assert parquet_calls[0][
        "object_name"
    ] == CLEAN_OBJECT

    assert len(upsert_calls) == 1

    assert upsert_calls[0][
        "connection"
    ] is connection

    assert upsert_calls[0][
        "expected_batch_id"
    ] == "BATCH_1"

    assert len(
        upsert_calls[0]["dataframe"]
    ) == 2

    assert (
        database_settings
        .connect_count
    ) == 1

    assert connection.commit_count == 1
    assert connection.rollback_count == 0
    assert connection.close_count == 1

    assert summary["status"] == "SUCCESS"
    assert summary["batch_id"] == "BATCH_1"

    assert summary[
        "partition_date"
    ] == "2026-07-25"

    assert summary[
        "partition_hour"
    ] == "02"

    assert summary["input_rows"] == 2

    assert summary[
        "processed_rows"
    ] == 2

    assert summary[
        "inserted_rows"
    ] == 1

    assert summary[
        "updated_rows"
    ] == 1

    assert summary[
        "database_time_column"
    ] == "forecast_time"

    assert summary[
        "quality_summary_object_name"
    ] == QUALITY_SUMMARY_OBJECT

    assert summary[
        "clean_object_name"
    ] == CLEAN_OBJECT

    expected_summary_object = (
        "pipeline/load/timescaledb/"
        "date=2026-07-25/"
        "hour=02/"
        "batch_id=BATCH_1/"
        "load_summary.json"
    )

    assert summary[
        "summary_object_name"
    ] == expected_summary_object

    assert len(json_writes) == 1

    assert json_writes[0][
        "bucket_name"
    ] == "air-quality-mart"

    assert json_writes[0][
        "object_name"
    ] == expected_summary_object

    assert json_writes[0][
        "data"
    ] == summary


def test_load_latest_clean_batch_rolls_back_and_closes_on_upsert_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minio_settings = (
        build_minio_settings()
    )

    minio_client = object()

    connection = FakeConnection()

    database_settings = (
        FakeDatabaseSettings(
            connection
        )
    )

    json_writes: list[
        dict[str, Any]
    ] = []

    monkeypatch.setattr(
        loader,
        "ensure_buckets",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        loader,
        "find_latest_loadable_quality_batch",
        lambda **kwargs: (
            QUALITY_SUMMARY_OBJECT,
            build_quality_summary(),
        ),
    )

    monkeypatch.setattr(
        loader,
        "get_parquet_object",
        lambda **kwargs: (
            build_clean_dataframe()
        ),
    )

    def failing_upsert(
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise loader.MinioTimescaleDBLoadError(
            "Upsert test failure"
        )

    monkeypatch.setattr(
        loader,
        "upsert_fact_dataframe",
        failing_upsert,
    )

    monkeypatch.setattr(
        loader,
        "put_json_object",
        lambda **kwargs: (
            json_writes.append(
                kwargs
            )
        ),
    )

    with pytest.raises(
        loader.MinioTimescaleDBLoadError,
        match="Upsert test failure",
    ):
        (
            loader
            .load_latest_minio_clean_batch(
                minio_settings=(
                    minio_settings
                ),
                minio_client=(
                    minio_client
                ),
                database_settings=(
                    database_settings
                ),
            )
        )

    assert connection.commit_count == 0
    assert connection.rollback_count == 1
    assert connection.close_count == 1

    assert json_writes == []


def test_load_latest_clean_batch_rejects_missing_clean_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minio_settings = (
        build_minio_settings()
    )

    minio_client = object()

    connection = FakeConnection()

    database_settings = (
        FakeDatabaseSettings(
            connection
        )
    )

    monkeypatch.setattr(
        loader,
        "ensure_buckets",
        lambda **kwargs: None,
    )

    invalid_quality_summary = (
        build_quality_summary()
    )

    invalid_quality_summary[
        "clean_object_name"
    ] = "   "

    monkeypatch.setattr(
        loader,
        "find_latest_loadable_quality_batch",
        lambda **kwargs: (
            QUALITY_SUMMARY_OBJECT,
            invalid_quality_summary,
        ),
    )

    with pytest.raises(
        loader.MinioTimescaleDBLoadError,
        match="clean_object_name",
    ):
        (
            loader
            .load_latest_minio_clean_batch(
                minio_settings=(
                    minio_settings
                ),
                minio_client=(
                    minio_client
                ),
                database_settings=(
                    database_settings
                ),
            )
        )

    assert (
        database_settings
        .connect_count
    ) == 0

    assert connection.commit_count == 0
    assert connection.rollback_count == 0
    assert connection.close_count == 0