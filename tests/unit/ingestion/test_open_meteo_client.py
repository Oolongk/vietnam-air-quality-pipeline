from __future__ import annotations

from typing import Any

import pytest

from src.ingestion.open_meteo_client import (
    InvalidOpenMeteoResponseError,
    OpenMeteoClient,
    OpenMeteoClientError,
)


TEST_VARIABLES = (
    "pm2_5",
    "us_aqi",
)


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self.payload = payload
        self.text = text

    def json(
        self,
    ) -> Any:
        return self.payload


def build_valid_response(
    *,
    pm2_5: float = 20.0,
    us_aqi: int = 50,
) -> dict[str, Any]:
    return {
        "latitude": 10.0,
        "longitude": 106.0,
        "hourly_units": {
            "time": "iso8601",
            "pm2_5": "μg/m³",
            "us_aqi": "",
        },
        "hourly": {
            "time": [
                "2026-07-25T00:00",
                "2026-07-25T01:00",
            ],
            "pm2_5": [
                pm2_5,
                pm2_5 + 1,
            ],
            "us_aqi": [
                us_aqi,
                us_aqi + 1,
            ],
        },
    }


def build_client(
    *,
    max_attempts: int = 1,
) -> OpenMeteoClient:
    return OpenMeteoClient(
        base_url=(
            "https://example.test/"
            "air-quality"
        ),
        hourly_variables=TEST_VARIABLES,
        max_attempts=max_attempts,
        connect_timeout_seconds=2,
        read_timeout_seconds=5,
        backoff_multiplier=0,
        backoff_min_seconds=0,
        backoff_max_seconds=0,
    )


def build_points() -> list[
    dict[str, object]
]:
    return [
        {
            "point_id": "POINT_A",
            "location_id": "LOC_A",
            "latitude": 10.0,
            "longitude": 106.0,
        },
        {
            "point_id": "POINT_B",
            "location_id": "LOC_B",
            "latitude": 11.0,
            "longitude": 107.0,
        },
    ]


def test_batch_request_preserves_point_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = build_client()

    captured: dict[str, Any] = {}

    responses = [
        build_valid_response(
            pm2_5=20.0,
            us_aqi=50,
        ),
        build_valid_response(
            pm2_5=30.0,
            us_aqi=60,
        ),
    ]

    def fake_get(
        url: str,
        *,
        params: dict[str, Any],
        timeout: tuple[float, float],
    ) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout

        return FakeResponse(
            status_code=200,
            payload=responses,
        )

    monkeypatch.setattr(
        client.session,
        "get",
        fake_get,
    )

    results = (
        client.fetch_hourly_air_quality_batch(
            monitoring_points=build_points(),
        )
    )

    assert captured["url"] == (
        "https://example.test/"
        "air-quality"
    )

    assert captured["params"][
        "latitude"
    ] == "10.0,11.0"

    assert captured["params"][
        "longitude"
    ] == "106.0,107.0"

    assert captured["timeout"] == (
        2.0,
        5.0,
    )

    assert len(results) == 2

    assert results[0]["request"][
        "point_id"
    ] == "POINT_A"

    assert results[1]["request"][
        "point_id"
    ] == "POINT_B"

    assert results[0]["response"] == (
        responses[0]
    )

    assert results[1]["response"] == (
        responses[1]
    )

    assert client.get_request_metrics() == {
        "total_http_attempts": 1,
        "last_request_attempts": 1,
    }


def test_retries_temporary_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = build_client(
        max_attempts=2,
    )

    responses = [
        FakeResponse(
            status_code=503,
            payload={
                "reason": (
                    "Temporary unavailable"
                ),
            },
        ),
        FakeResponse(
            status_code=200,
            payload=[
                build_valid_response(),
            ],
        ),
    ]

    call_count = 0

    def fake_get(
        url: str,
        *,
        params: dict[str, Any],
        timeout: tuple[float, float],
    ) -> FakeResponse:
        nonlocal call_count

        response = responses[
            call_count
        ]

        call_count += 1

        return response

    monkeypatch.setattr(
        client.session,
        "get",
        fake_get,
    )

    results = (
        client.fetch_hourly_air_quality_batch(
            monitoring_points=[
                build_points()[0],
            ]
        )
    )

    assert len(results) == 1
    assert call_count == 2

    assert client.get_request_metrics() == {
        "total_http_attempts": 2,
        "last_request_attempts": 2,
    }


def test_does_not_retry_non_retryable_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = build_client(
        max_attempts=3,
    )

    call_count = 0

    def fake_get(
        url: str,
        *,
        params: dict[str, Any],
        timeout: tuple[float, float],
    ) -> FakeResponse:
        nonlocal call_count

        call_count += 1

        return FakeResponse(
            status_code=400,
            payload={
                "reason": (
                    "Invalid coordinates"
                ),
            },
        )

    monkeypatch.setattr(
        client.session,
        "get",
        fake_get,
    )

    with pytest.raises(
        OpenMeteoClientError,
        match="HTTP 400",
    ):
        client.fetch_hourly_air_quality_batch(
            monitoring_points=[
                build_points()[0],
            ]
        )

    assert call_count == 1

    assert client.get_request_metrics() == {
        "total_http_attempts": 1,
        "last_request_attempts": 1,
    }


def test_rejects_response_count_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = build_client()

    def fake_get(
        url: str,
        *,
        params: dict[str, Any],
        timeout: tuple[float, float],
    ) -> FakeResponse:
        return FakeResponse(
            status_code=200,
            payload=[
                build_valid_response(),
            ],
        )

    monkeypatch.setattr(
        client.session,
        "get",
        fake_get,
    )

    with pytest.raises(
        InvalidOpenMeteoResponseError,
        match=(
            "không khớp số "
            "monitoring point"
        ),
    ):
        client.fetch_hourly_air_quality_batch(
            monitoring_points=build_points(),
        )


def test_rejects_mismatched_hourly_lengths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = build_client()

    invalid_response = (
        build_valid_response()
    )

    invalid_response["hourly"][
        "pm2_5"
    ] = [
        20.0,
    ]

    def fake_get(
        url: str,
        *,
        params: dict[str, Any],
        timeout: tuple[float, float],
    ) -> FakeResponse:
        return FakeResponse(
            status_code=200,
            payload=[
                invalid_response,
            ],
        )

    monkeypatch.setattr(
        client.session,
        "get",
        fake_get,
    )

    with pytest.raises(
        InvalidOpenMeteoResponseError,
        match="hourly.pm2_5",
    ):
        client.fetch_hourly_air_quality_batch(
            monitoring_points=[
                build_points()[0],
            ]
        )