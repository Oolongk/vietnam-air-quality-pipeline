from __future__ import annotations

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


def build_location_record() -> dict[str, Any]:
    return {
        "location_id": "HN",
        "location_name": "Hà Nội",
        "region": "Miền Bắc",
        "admin_type": "Thành phố",
        "is_active": True,
        "created_at": (
            "2026-07-01T00:00:00+00:00"
        ),
        "updated_at": (
            "2026-07-01T00:00:00+00:00"
        ),
    }


def build_monitoring_point_record(
) -> dict[str, Any]:
    return {
        "point_id": "HN_CENTER",
        "location_id": "HN",
        "point_name": "Trung tâm Hà Nội",
        "point_type": "urban_center",
        "latitude": 21.0285,
        "longitude": 105.8542,
        "is_active": True,
        "created_at": (
            "2026-07-01T00:00:00+00:00"
        ),
        "updated_at": (
            "2026-07-01T00:00:00+00:00"
        ),
        "location_name": "Hà Nội",
        "region": "Miền Bắc",
        "admin_type": "Thành phố",
    }


def test_locations_returns_active_records(
    monkeypatch: pytest.MonkeyPatch,
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
            build_location_record()
        ]

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/locations"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "SUCCESS"
    assert payload["record_count"] == 1

    assert payload["data"][0][
        "location_id"
    ] == "HN"

    normalized_query = normalize_sql(
        captured["query"]
    )

    assert "from dim_location" in (
        normalized_query
    )

    assert "where is_active is true" in (
        normalized_query
    )

    assert captured["parameters"] is None


def test_locations_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
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
        "/api/v1/locations"
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "SUCCESS",
        "record_count": 0,
        "data": [],
    }


def test_locations_returns_500_on_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        raise api_main.DatabaseConfigurationError(
            "Test database error"
        )

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/locations"
    )

    assert response.status_code == 500

    assert "tỉnh/thành" in (
        response.json()["detail"]
    )


def test_monitoring_points_returns_records(
    monkeypatch: pytest.MonkeyPatch,
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
            build_monitoring_point_record()
        ]

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/monitoring-points"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "SUCCESS"
    assert payload["record_count"] == 1

    assert payload["data"][0][
        "point_id"
    ] == "HN_CENTER"

    assert payload["data"][0][
        "location_name"
    ] == "Hà Nội"

    normalized_query = normalize_sql(
        captured["query"]
    )

    assert (
        "from dim_monitoring_point as p"
        in normalized_query
    )

    assert (
        "inner join dim_location as l"
        in normalized_query
    )

    assert (
        "p.is_active is true"
        in normalized_query
    )

    assert (
        "l.is_active is true"
        in normalized_query
    )

    assert captured["parameters"] is None


def test_monitoring_points_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
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
        "/api/v1/monitoring-points"
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "SUCCESS",
        "record_count": 0,
        "data": [],
    }


def test_monitoring_points_returns_500_on_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_query(
        *,
        query: str,
        parameters: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        raise api_main.DatabaseConfigurationError(
            "Test database error"
        )

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/monitoring-points"
    )

    assert response.status_code == 500

    assert "monitoring point" in (
        response.json()["detail"]
    )