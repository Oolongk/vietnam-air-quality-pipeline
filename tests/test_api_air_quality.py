from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import api.main as api_main


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