from __future__ import annotations

from typing import Any

from dashboard.snapshot_client import AirQualitySnapshotClient


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.ok = True
        self.status_code = 200
        self.text = ""
        self.reason = "OK"

    def json(self) -> dict[str, Any]:
        return self._payload


def test_client_reads_location_and_daily_mart_snapshots(monkeypatch) -> None:
    requested_urls: list[str] = []

    def fake_get(*, url: str, headers: dict[str, str], timeout: int) -> FakeResponse:
        del headers, timeout
        requested_urls.append(url)
        if url.endswith("/current.json"):
            return FakeResponse(
                {
                    "schema_version": "1.0",
                    "snapshot_id": "snapshot-1",
                    "release_prefix": "releases/snapshot-1",
                    "manifest_key": "releases/snapshot-1/manifest.json",
                }
            )
        if url.endswith("/air_quality/location_summary.json"):
            return FakeResponse({"record_count": 2, "data": [{}, {}]})
        if url.endswith("/air_quality/daily_summary.json"):
            return FakeResponse({"record_count": 2, "data": [{}, {}]})
        raise AssertionError(url)

    monkeypatch.setattr("dashboard.snapshot_client.requests.get", fake_get)
    client = AirQualitySnapshotClient("https://example.test")

    assert client.get_location_summary(limit=1)["record_count"] == 1
    assert client.get_daily_summary(limit=1)["record_count"] == 1
    assert any("location_summary.json" in url for url in requested_urls)
    assert any("daily_summary.json" in url for url in requested_urls)
