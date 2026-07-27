from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api import main as api_main


client = TestClient(
    api_main.app
)


def build_alert_record() -> dict[str, Any]:
    return {
        "alert_id": 101,
        "point_id": "HN_CENTER",
        "location_id": "HN",
        "alert_time": (
            "2026-07-22T08:00:00+07:00"
        ),
        "aqi_value": 175,
        "aqi_level": "Không tốt",
        "severity": "HIGH",
        "message": (
            "Cảnh báo chất lượng không khí: "
            "HN_CENTER (HN) có US AQI=175, "
            "mức 'Không tốt'."
        ),
        "status": "OPEN",
        "source": "open_meteo",
        "created_at": (
            "2026-07-22T01:05:00+00:00"
        ),
    }


def normalize_sql(
    query: str,
) -> str:
    return " ".join(
        query.split()
    ).lower()


def test_latest_alerts_returns_records(
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
            build_alert_record()
        ]

    monkeypatch.setattr(
        api_main,
        "execute_query",
        fake_execute_query,
    )

    response = client.get(
        "/api/v1/alerts/latest",
        params={
            "limit": 25,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "SUCCESS"
    assert payload["record_count"] == 1
    assert len(payload["data"]) == 1

    assert payload["data"][0][
        "point_id"
    ] == "HN_CENTER"

    assert payload["data"][0][
        "severity"
    ] == "HIGH"

    assert captured["parameters"] == (
        25,
    )

    normalized_query = normalize_sql(
        captured["query"]
    )

    assert (
        "from fact_air_quality_alerts"
        in normalized_query
    )

    assert (
        "order by created_at desc"
        in normalized_query
    )

    assert "limit %s" in normalized_query


def test_latest_alerts_returns_empty_list(
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
        "/api/v1/alerts/latest",
        params={
            "limit": 100,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload == {
        "status": "SUCCESS",
        "record_count": 0,
        "data": [],
    }


@pytest.mark.parametrize(
    "invalid_limit",
    [
        0,
        1001,
    ],
)
def test_latest_alerts_rejects_invalid_limit(
    invalid_limit: int,
) -> None:
    response = client.get(
        "/api/v1/alerts/latest",
        params={
            "limit": invalid_limit,
        },
    )

    assert response.status_code == 422


def test_latest_alerts_uses_default_limit(
    monkeypatch: pytest.MonkeyPatch,
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
        "/api/v1/alerts/latest"
    )

    assert response.status_code == 200

    assert captured["parameters"] == (
        100,
    )


def test_latest_alerts_returns_500_on_database_error(
    monkeypatch: pytest.MonkeyPatch,
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
        "/api/v1/alerts/latest"
    )

    assert response.status_code == 500

    payload = response.json()

    assert "alert" in payload[
        "detail"
    ].lower()