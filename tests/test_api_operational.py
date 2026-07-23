from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api import main as api_main


client = TestClient(
    api_main.app
)


def normalize_sql(
    query: str,
) -> str:
    return " ".join(
        query.lower().split()
    )


def build_pipeline_record(
    *,
    stage_name: str = "extract",
    status: str = "SUCCESS",
) -> dict[str, Any]:
    return {
        "run_id": (
            "20260722T010000Z_test:"
            f"{stage_name}"
        ),
        "batch_id": (
            "20260722T010000Z_test"
        ),
        "pipeline_name": (
            "open_meteo_air_quality"
        ),
        "source": "open_meteo",
        "stage_name": stage_name,
        "status": status,
        "started_at": (
            "2026-07-22T01:00:00+00:00"
        ),
        "finished_at": (
            "2026-07-22T01:01:00+00:00"
        ),
        "duration_seconds": 60.0,
        "input_records": 240,
        "output_records": 240,
        "failed_records": 0,
        "error_message": None,
        "summary_bucket": (
            "air-quality-mart"
        ),
        "summary_object_name": (
            "pipeline/summary.json"
        ),
        "updated_at": (
            "2026-07-22T01:01:00+00:00"
        ),
    }


def build_quality_record(
    *,
    check_name: str = (
        "required_columns_check"
    ),
    status: str = "PASSED",
) -> dict[str, Any]:
    return {
        "run_id": (
            "20260722T010000Z_test:"
            "data_quality"
        ),
        "batch_id": (
            "20260722T010000Z_test"
        ),
        "check_name": check_name,
        "status": status,
        "bad_records_count": (
            0
            if status == "PASSED"
            else 1
        ),
        "message": (
            "Data Quality test result"
        ),
        "checked_at": (
            "2026-07-22T01:00:30+00:00"
        ),
        "summary_bucket": (
            "air-quality-mart"
        ),
        "summary_object_name": (
            "quality/quality_summary.json"
        ),
        "updated_at": (
            "2026-07-22T01:00:30+00:00"
        ),
    }


def test_health_returns_healthy_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_time = datetime(
        2026,
        7,
        22,
        1,
        0,
        tzinfo=timezone.utc,
    )

    monkeypatch.setattr(
        api_main,
        "check_database_connection",
        lambda: {
            "database_name": (
                "air_quality_db"
            ),
            "database_time": database_time,
        },
    )

    response = client.get(
        "/health"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "HEALTHY"

    assert payload["service"] == (
        "vietnam-air-quality-api"
    )

    assert payload["database"] == (
        "air_quality_db"
    )

    assert payload[
        "database_time"
    ].startswith(
        "2026-07-22T01:00:00"
    )


def test_health_returns_503_when_database_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_check_database_connection(
    ) -> dict[str, Any]:
        raise (
            api_main
            .DatabaseConfigurationError(
                "Test database unavailable"
            )
        )

    monkeypatch.setattr(
        api_main,
        "check_database_connection",
        fake_check_database_connection,
    )

    response = client.get(
        "/health"
    )

    assert response.status_code == 503

    assert "TimescaleDB" in (
        response.json()["detail"]
    )


def test_pipeline_health_returns_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    records = [
        build_pipeline_record(
            stage_name="extract"
        ),
        build_pipeline_record(
            stage_name="transform"
        ),
        build_pipeline_record(
            stage_name="data_quality"
        ),
        build_pipeline_record(
            stage_name="load_timescaledb"
        ),
        build_pipeline_record(
            stage_name="alerts"
        ),
    ]

    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[
            Any,
            ...,
        ] = (),
    ) -> list[dict[str, Any]]:
        captured["query"] = query
        captured["parameters"] = parameters

        return records

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/pipeline/health/latest"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "SUCCESS"

    assert payload["batch_id"] == (
        "20260722T010000Z_test"
    )

    assert payload["stage_count"] == 5

    normalized_query = normalize_sql(
        captured["query"]
    )

    assert (
        "from pipeline_run_logs"
        in normalized_query
    )

    assert (
        "case stage_name"
        in normalized_query
    )

    assert captured["parameters"] == ()


def test_pipeline_health_returns_failed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [
        build_pipeline_record(
            stage_name="extract",
            status="SUCCESS",
        ),
        build_pipeline_record(
            stage_name="transform",
            status="FAILED",
        ),
    ]

    monkeypatch.setattr(
        api_main,
        "execute_query",
        lambda **kwargs: records,
    )

    response = client.get(
        "/api/v1/pipeline/health/latest"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "FAILED"
    assert payload["stage_count"] == 2


def test_pipeline_health_returns_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_main,
        "execute_query",
        lambda **kwargs: [],
    )

    response = client.get(
        "/api/v1/pipeline/health/latest"
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "EMPTY",
        "batch_id": None,
        "stage_count": 0,
        "data": [],
    }


def test_pipeline_health_returns_500_on_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_query(
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        raise (
            api_main
            .DatabaseConfigurationError(
                "Test database error"
            )
        )

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/pipeline/health/latest"
    )

    assert response.status_code == 500

    assert "Pipeline Health" in (
        response.json()["detail"]
    )


def test_data_quality_returns_passed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    records = [
        build_quality_record(
            check_name=(
                "required_columns_check"
            ),
            status="PASSED",
        ),
        build_quality_record(
            check_name=(
                "duplicate_key_check"
            ),
            status="SUCCESS",
        ),
    ]

    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[
            Any,
            ...,
        ] = (),
    ) -> list[dict[str, Any]]:
        captured["query"] = query
        captured["parameters"] = parameters

        return records

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/data-quality/latest"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "PASSED"
    assert payload["check_count"] == 2

    assert (
        payload["failed_check_count"]
        == 0
    )

    normalized_query = normalize_sql(
        captured["query"]
    )

    assert (
        "from data_quality_logs"
        in normalized_query
    )

    assert (
        "order by check_name"
        in normalized_query
    )

    assert captured["parameters"] == ()


def test_data_quality_returns_failed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [
        build_quality_record(
            check_name=(
                "required_columns_check"
            ),
            status="PASSED",
        ),
        build_quality_record(
            check_name=(
                "freshness_check"
            ),
            status="WARNED",
        ),
    ]

    monkeypatch.setattr(
        api_main,
        "execute_query",
        lambda **kwargs: records,
    )

    response = client.get(
        "/api/v1/data-quality/latest"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "FAILED"
    assert payload["check_count"] == 2

    assert (
        payload["failed_check_count"]
        == 1
    )


def test_data_quality_returns_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_main,
        "execute_query",
        lambda **kwargs: [],
    )

    response = client.get(
        "/api/v1/data-quality/latest"
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "PASSED",
        "check_count": 0,
        "failed_check_count": 0,
        "data": [],
    }


def test_data_quality_returns_500_on_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_query(
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        raise (
            api_main
            .DatabaseConfigurationError(
                "Test database error"
            )
        )

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/data-quality/latest"
    )

    assert response.status_code == 500

    assert "Data Quality" in (
        response.json()["detail"]
    )