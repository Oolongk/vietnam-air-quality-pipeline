from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import api.main as api_main

from typing import Any

import pytest


BATCH_ID = "20260721T123008Z_3d7a0d3b"

client = TestClient(
    api_main.app
)


def build_air_quality_record() -> dict[str, Any]:
    """
    Tạo một record giả giống dữ liệu API nhận từ database.

    Test không cần mở kết nối TimescaleDB thật. execute_query sẽ được
    monkeypatch để trả record này.
    """
    return {
        "point_id": "HN_CENTER",
        "location_id": "HN",
        "point_name": "Hà Nội Center",
        "point_type": "urban_center",
        "location_name": "Hà Nội",
        "region": "Miền Bắc",
        "admin_type": "Thành phố",
        "latitude": 21.0285,
        "longitude": 105.8542,
        "forecast_time": "2026-07-21T19:00:00+07:00",
        "pm2_5": 15.5,
        "pm10": 25.3,
        "carbon_monoxide": 120.0,
        "nitrogen_dioxide": 8.0,
        "sulphur_dioxide": 4.0,
        "ozone": 35.0,
        "us_aqi": 55,
        "us_aqi_pm2_5": 55,
        "us_aqi_pm10": 25,
        "us_aqi_nitrogen_dioxide": 8,
        "us_aqi_carbon_monoxide": 4,
        "us_aqi_ozone": 18,
        "us_aqi_sulphur_dioxide": 3,
        "source": "open_meteo",
        "batch_id": BATCH_ID,
        "schema_version": "1.0",
        "ingested_at": "2026-07-21T19:30:12+07:00",
    }


def normalize_sql(query: str) -> str:
    """
    Gộp khoảng trắng và chuyển SQL thành chữ thường.

    Nhờ vậy test không phụ thuộc vào cách xuống dòng hoặc indent
    trong chuỗi SQL của api/main.py.
    """
    return " ".join(
        query.lower().split()
    )


def assert_optimized_latest_batch_query(
    query: str,
) -> None:
    """
    Kiểm tra query đang dùng cách tìm latest batch đã tối ưu.
    """
    normalized_query = normalize_sql(
        query
    )

    assert (
        "from fact_air_quality_hourly "
        "order by ingested_at desc, "
        "batch_id desc limit 1"
        in normalized_query
    )

    assert (
        "group by batch_id"
        not in normalized_query
    )

    assert (
        "max(ingested_at)"
        not in normalized_query
    )

    assert (
        "btrim(batch_id)"
        not in normalized_query
    )


def test_latest_air_quality_uses_optimized_query(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        captured["query"] = query
        captured["parameters"] = parameters

        return [
            build_air_quality_record()
        ]

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/latest",
        params={
            "limit": 25,
        },
    )

    assert response.status_code == 200

    assert_optimized_latest_batch_query(
        captured["query"]
    )

    assert captured["parameters"] == (
        25,
    )


def test_air_quality_by_point_uses_optimized_query(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        captured["query"] = query
        captured["parameters"] = parameters

        return [
            build_air_quality_record()
        ]

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/points/hn_center",
        params={
            "limit": 24,
        },
    )

    assert response.status_code == 200

    assert_optimized_latest_batch_query(
        captured["query"]
    )

    normalized_query = normalize_sql(
        captured["query"]
    )

    assert (
        "and f.point_id = %s"
        in normalized_query
    )

    assert (
        "order by f.forecast_time"
        in normalized_query
    )

    assert captured["parameters"] == (
        "HN_CENTER",
        24,
    )


def test_air_quality_by_point_returns_404_when_empty(
    monkeypatch,
) -> None:
    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/points/HN_CENTER",
        params={
            "limit": 24,
        },
    )

    assert response.status_code == 404
    
def test_air_quality_by_location_uses_optimized_query(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    location_record = build_air_quality_record()

    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        captured["query"] = query
        captured["parameters"] = parameters

        return [
            location_record
        ]

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/locations/hn"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "SUCCESS"

    assert payload["location_id"] == "HN"

    assert payload["location_name"] == (
        "Hà Nội"
    )

    assert payload["batch_id"] == BATCH_ID

    assert payload["record_count"] == 1

    assert payload["data"][0][
        "location_id"
    ] == "HN"

    assert_optimized_latest_batch_query(
        captured["query"]
    )

    normalized_query = normalize_sql(
        captured["query"]
    )

    assert (
        "and f.location_id = %s"
        in normalized_query
    )

    assert (
        "order by f.forecast_time, "
        "f.point_id"
        in normalized_query
    )

    assert captured["parameters"] == (
        "HN",
        72,
    )


def test_air_quality_by_location_returns_404_when_empty(
    monkeypatch,
) -> None:
    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/locations/HN",
        params={
            "limit": 72,
        },
    )

    assert response.status_code == 404

    payload = response.json()

    assert "HN" in payload["detail"]


def test_air_quality_by_location_returns_500_on_database_error(
    monkeypatch,
) -> None:
    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        raise api_main.DatabaseConfigurationError(
            "Test database configuration error"
        )

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/locations/HN"
    )

    assert response.status_code == 500

    payload = response.json()

    assert "tỉnh/thành" in (
        payload["detail"]
    )
    
def test_top_polluted_uses_latest_batch_and_reference_time(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    first_record = build_air_quality_record()

    first_record["point_id"] = "HN_CENTER"
    first_record["location_id"] = "HN"
    first_record["location_name"] = "Hà Nội"
    first_record["us_aqi"] = 175
    first_record["aqi_level"] = "Không tốt"
    first_record["aqi_severity"] = "UNHEALTHY"

    second_record = build_air_quality_record()

    second_record["point_id"] = "HCM_CENTER"
    second_record["location_id"] = "HCM"
    second_record["location_name"] = (
        "Thành phố Hồ Chí Minh"
    )
    second_record["us_aqi"] = 125
    second_record["aqi_level"] = (
        "Không tốt cho nhóm nhạy cảm"
    )
    second_record["aqi_severity"] = (
        "UNHEALTHY_SENSITIVE"
    )

    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        captured["query"] = query
        captured["parameters"] = parameters

        return [
            first_record,
            second_record,
        ]

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/top-polluted",
        params={
            "limit": 5,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "SUCCESS"
    assert payload["batch_id"] == BATCH_ID

    assert payload["reference_time"] == (
        first_record["forecast_time"]
    )

    assert payload["record_count"] == 2
    assert len(payload["data"]) == 2

    assert payload["data"][0][
        "point_id"
    ] == "HN_CENTER"

    assert payload["data"][0][
        "us_aqi"
    ] == 175

    assert captured["parameters"] == (
        5,
    )

    assert_optimized_latest_batch_query(
        captured["query"]
    )

    normalized_query = normalize_sql(
        captured["query"]
    )

    assert (
        "min(forecast_time) as forecast_time"
        in normalized_query
    )

    assert (
        "and f.forecast_time = "
        "( select forecast_time "
        "from reference_time )"
        in normalized_query
    )

    assert (
        "and f.us_aqi is not null"
        in normalized_query
    )

    assert (
        "order by f.us_aqi desc"
        in normalized_query
    )

    assert "limit %s" in normalized_query


def test_top_polluted_returns_empty_result(
    monkeypatch,
) -> None:
    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/top-polluted"
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "SUCCESS",
        "batch_id": None,
        "reference_time": None,
        "record_count": 0,
        "data": [],
    }


@pytest.mark.parametrize(
    "invalid_limit",
    [
        0,
        101,
    ],
)
def test_top_polluted_rejects_invalid_limit(
    invalid_limit: int,
) -> None:
    response = client.get(
        "/api/v1/air-quality/top-polluted",
        params={
            "limit": invalid_limit,
        },
    )

    assert response.status_code == 422


def test_top_polluted_uses_default_limit(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        captured["parameters"] = parameters

        return []

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/top-polluted"
    )

    assert response.status_code == 200

    assert captured["parameters"] == (
        10,
    )


def test_top_polluted_returns_500_on_database_error(
    monkeypatch,
) -> None:
    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        raise api_main.DatabaseConfigurationError(
            "Test database configuration error"
        )

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/top-polluted"
    )

    assert response.status_code == 500

    payload = response.json()

    assert "ô nhiễm nhất" in (
        payload["detail"]
    )
    
def test_air_quality_history_returns_recent_records(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    first_record = build_air_quality_record()
    first_record["forecast_time"] = (
        "2026-07-21T18:00:00+07:00"
    )
    first_record["aqi_level"] = "Tốt"
    first_record["aqi_severity"] = "GOOD"

    second_record = build_air_quality_record()
    second_record["forecast_time"] = (
        "2026-07-21T19:00:00+07:00"
    )
    second_record["aqi_level"] = "Trung bình"
    second_record["aqi_severity"] = "MODERATE"

    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        captured["query"] = query
        captured["parameters"] = parameters

        return [
            first_record,
            second_record,
        ]

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/history",
        params={
            "point_id": "hn_center",
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "SUCCESS"
    assert payload["point_id"] == "HN_CENTER"

    assert payload["point_name"] == (
        "Hà Nội Center"
    )

    assert payload["location_id"] == "HN"
    assert payload["location_name"] == "Hà Nội"

    assert payload["requested_hours"] == 168
    assert payload["record_count"] == 2

    assert payload["first_forecast_time"] == (
        first_record["forecast_time"]
    )

    assert payload["last_forecast_time"] == (
        second_record["forecast_time"]
    )

    assert captured["parameters"] == (
        "HN_CENTER",
        168,
    )

    normalized_query = normalize_sql(
        captured["query"]
    )

    assert (
        "with recent_history as"
        in normalized_query
    )

    assert (
        "where f.point_id = %s"
        in normalized_query
    )

    assert (
        "order by f.forecast_time desc"
        in normalized_query
    )

    assert "limit %s" in normalized_query

    assert (
        "order by history.forecast_time"
        in normalized_query
    )


def test_air_quality_history_uses_custom_hours(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        captured["parameters"] = parameters

        return [
            build_air_quality_record()
        ]

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/history",
        params={
            "point_id": "HN_CENTER",
            "hours": 24,
        },
    )

    assert response.status_code == 200

    assert captured["parameters"] == (
        "HN_CENTER",
        24,
    )

    assert response.json()[
        "requested_hours"
    ] == 24


def test_air_quality_history_returns_404_when_empty(
    monkeypatch,
) -> None:
    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/history",
        params={
            "point_id": "NOT_EXIST",
            "hours": 168,
        },
    )

    assert response.status_code == 404

    assert "NOT_EXIST" in (
        response.json()["detail"]
    )


def test_air_quality_history_requires_point_id(
) -> None:
    response = client.get(
        "/api/v1/air-quality/history"
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "invalid_hours",
    [
        0,
        2161,
    ],
)
def test_air_quality_history_rejects_invalid_hours(
    invalid_hours: int,
) -> None:
    response = client.get(
        "/api/v1/air-quality/history",
        params={
            "point_id": "HN_CENTER",
            "hours": invalid_hours,
        },
    )

    assert response.status_code == 422


def test_air_quality_history_returns_500_on_database_error(
    monkeypatch,
) -> None:
    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        raise api_main.DatabaseConfigurationError(
            "Test database configuration error"
        )

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/air-quality/history",
        params={
            "point_id": "HN_CENTER",
        },
    )

    assert response.status_code == 500

    assert "lịch sử" in (
        response.json()["detail"]
    )