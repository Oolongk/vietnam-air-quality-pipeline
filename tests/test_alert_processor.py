from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.alerts import alert_processor
from src.alerts.alert_processor import (
    AirQualityAlertProcessingError,
    UPSERT_ALERT_SQL,
    prepare_classified_records,
    process_clean_batch_alerts,
    update_aqi_and_alerts,
)


class FakeTransaction:
    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exception_type: Any,
        exception_value: Any,
        traceback: Any,
    ) -> bool:
        return False


class FakeCursor:
    def __init__(
        self,
        fact_exists: bool = True,
    ) -> None:
        self.fact_exists = fact_exists

        self.executions: list[
            tuple[str, dict[str, Any]]
        ] = []

        self.last_query = ""

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(
        self,
        exception_type: Any,
        exception_value: Any,
        traceback: Any,
    ) -> bool:
        return False

    def execute(
        self,
        query: str,
        parameters: dict[str, Any],
    ) -> None:
        normalized_query = " ".join(
            query.split()
        ).lower()

        self.last_query = normalized_query

        self.executions.append(
            (
                normalized_query,
                parameters.copy(),
            )
        )

    def fetchone(
        self,
    ) -> tuple[int] | None:
        if self.last_query.startswith(
            "update fact_air_quality_hourly"
        ):
            if self.fact_exists:
                return (1,)

            return None

        return None


class FakeConnection:
    def __init__(
        self,
        fact_exists: bool = True,
    ) -> None:
        self.cursor_instance = FakeCursor(
            fact_exists=fact_exists
        )

        self.closed = False

    def transaction(
        self,
    ) -> FakeTransaction:
        return FakeTransaction()

    def cursor(
        self,
    ) -> FakeCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


def build_alert_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "point_id": "HN_CENTER",
                "location_id": "HN",
                "forecast_time": (
                    "2026-07-22T08:00:00+07:00"
                ),
                "us_aqi": 100,
                "source": "open_meteo",
            },
            {
                "point_id": "HCM_CENTER",
                "location_id": "HCM",
                "forecast_time": (
                    "2026-07-22T08:00:00+07:00"
                ),
                "us_aqi": 101,
                "source": "open_meteo",
            },
            {
                "point_id": "DN_CENTER",
                "location_id": "DN",
                "forecast_time": (
                    "2026-07-22T08:00:00+07:00"
                ),
                "us_aqi": 151,
                "source": "open_meteo",
            },
            {
                "point_id": "HP_CENTER",
                "location_id": "HP",
                "forecast_time": (
                    "2026-07-22T08:00:00+07:00"
                ),
                "us_aqi": 201,
                "source": "open_meteo",
            },
        ]
    )


def test_prepare_classified_records_maps_alert_levels(
) -> None:
    records = prepare_classified_records(
        build_alert_dataframe()
    )

    assert len(records) == 4

    assert records[0]["aqi_severity"] == (
        "MODERATE"
    )

    assert records[0]["alert_severity"] is None

    assert records[1]["alert_severity"] == (
        "MEDIUM"
    )

    assert records[2]["alert_severity"] == (
        "HIGH"
    )

    assert records[3]["alert_severity"] == (
        "CRITICAL"
    )


def test_prepare_classified_records_rejects_duplicate_key(
) -> None:
    dataframe = build_alert_dataframe()

    duplicated_dataframe = pd.concat(
        [
            dataframe,
            dataframe.iloc[[0]],
        ],
        ignore_index=True,
    )

    with pytest.raises(
        AirQualityAlertProcessingError,
        match="duplicate",
    ):
        prepare_classified_records(
            duplicated_dataframe
        )


def test_update_aqi_and_alerts_executes_expected_flow(
) -> None:
    connection = FakeConnection()

    result = update_aqi_and_alerts(
        dataframe=build_alert_dataframe(),
        connection=connection,
    )

    assert result == {
        "input_records": 4,
        "facts_updated": 4,
        "classified_records": 4,
        "null_aqi_records": 0,
        "alerts_generated": 3,
        "medium_alerts": 1,
        "high_alerts": 1,
        "critical_alerts": 1,
    }

    executed_queries = [
        query
        for query, _ in (
            connection
            .cursor_instance
            .executions
        )
    ]

    update_queries = [
        query
        for query in executed_queries
        if query.startswith(
            "update fact_air_quality_hourly"
        )
    ]

    delete_all_queries = [
        query
        for query in executed_queries
        if query.startswith(
            "delete from fact_air_quality_alerts"
        )
        and "severity <>" not in query
    ]

    delete_stale_queries = [
        query
        for query in executed_queries
        if "severity <>" in query
    ]

    upsert_queries = [
        query
        for query in executed_queries
        if query.startswith(
            "insert into fact_air_quality_alerts"
        )
    ]

    assert len(update_queries) == 4
    assert len(delete_all_queries) == 1
    assert len(delete_stale_queries) == 3
    assert len(upsert_queries) == 3

    assert connection.closed is False


def test_update_rejects_missing_fact_record(
) -> None:
    connection = FakeConnection(
        fact_exists=False
    )

    dataframe = build_alert_dataframe().iloc[
        [1]
    ]

    with pytest.raises(
        AirQualityAlertProcessingError,
        match="Không tìm thấy fact record",
    ):
        update_aqi_and_alerts(
            dataframe=dataframe,
            connection=connection,
        )


def test_upsert_uses_idempotent_conflict_key(
) -> None:
    normalized_sql = " ".join(
        UPSERT_ALERT_SQL.split()
    ).lower()

    assert "on conflict" in normalized_sql

    assert (
        "point_id, alert_time, "
        "severity, source"
    ) in normalized_sql

    assert "do update set" in normalized_sql


def test_process_clean_batch_writes_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean_data_path = (
        tmp_path
        / "clean"
        / "data.parquet"
    )

    clean_data_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataframe = build_alert_dataframe()

    dataframe.to_parquet(
        clean_data_path,
        engine="pyarrow",
        compression="snappy",
        index=False,
    )

    fake_processing_result = {
        "input_records": 4,
        "facts_updated": 4,
        "classified_records": 4,
        "null_aqi_records": 0,
        "alerts_generated": 3,
        "medium_alerts": 1,
        "high_alerts": 1,
        "critical_alerts": 1,
    }

    monkeypatch.setattr(
        alert_processor,
        "update_aqi_and_alerts",
        lambda dataframe: (
            fake_processing_result
        ),
    )

    alert_root = (
        tmp_path
        / "alerts"
    )

    summary = process_clean_batch_alerts(
        clean_data_path=clean_data_path,
        alert_root=alert_root,
        batch_id=(
            "20260722T010000Z_test1234"
        ),
        partition_date="2026-07-22",
        partition_hour="08",
    )

    expected_summary_path = (
        alert_root
        / "air_quality"
        / "hourly"
        / "date=2026-07-22"
        / "hour=08"
        / (
            "batch_id="
            "20260722T010000Z_test1234"
        )
        / "alert_summary.json"
    )

    assert expected_summary_path.exists()

    saved_summary = json.loads(
        expected_summary_path.read_text(
            encoding="utf-8"
        )
    )

    assert summary["status"] == "SUCCESS"

    assert summary["batch_id"] == (
        "20260722T010000Z_test1234"
    )

    assert summary["alerts_generated"] == 3

    assert saved_summary["status"] == (
        "SUCCESS"
    )

    assert saved_summary[
        "alerts_generated"
    ] == 3