from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.snapshot.minio_mart_snapshot_reader import MartSnapshotBundle
from src.snapshot.snapshot_publisher import SnapshotPublisher, SnapshotSettings

BATCH_ID = "20260801T134416Z_airflow"


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.ok = True
        self.status_code = 200
        self.text = ""
        self.reason = "OK"

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeSession:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> FakeResponse:
        del params, timeout
        path = url.removeprefix("http://api:8000")
        self.paths.append(path)
        payloads: dict[str, dict[str, Any]] = {
            "/health": {
                "status": "healthy",
                "service": "air-quality-api",
                "database": "timescaledb",
                "database_time": "2026-08-01T14:02:21+00:00",
            },
            "/api/v1/locations": {
                "status": "SUCCESS",
                "record_count": 1,
                "data": [{"location_id": "HN", "location_name": "Hà Nội"}],
            },
            "/api/v1/monitoring-points": {
                "status": "SUCCESS",
                "record_count": 1,
                "data": [{"point_id": "HN_CENTER", "location_id": "HN"}],
            },
            "/api/v1/alerts/latest": {
                "status": "SUCCESS",
                "record_count": 0,
                "data": [],
            },
            "/api/v1/pipeline/health/latest": {
                "status": "SUCCESS",
                "batch_id": BATCH_ID,
                "stage_count": 1,
                "data": [{"stage_name": "mart", "status": "SUCCESS"}],
            },
            "/api/v1/data-quality/latest": {
                "status": "SUCCESS",
                "check_count": 1,
                "failed_check_count": 0,
                "data": [{"check_name": "schema", "status": "PASS"}],
            },
        }
        return FakeResponse(payloads[path])


class FakeReader:
    settings = SimpleNamespace(mart_bucket="air-quality-mart")

    def read(self) -> MartSnapshotBundle:
        current = {
            "point_id": "HN_CENTER",
            "location_id": "HN",
            "location_name": "Hà Nội",
            "point_name": "Trung tâm Hà Nội",
            "forecast_time": "2026-08-01T21:00:00+07:00",
            "us_aqi": 146,
            "pm2_5": 54.7,
            "pm10": 54.9,
            "ozone": 52.0,
            "source_batch_id": BATCH_ID,
            "batch_id": BATCH_ID,
        }
        location = {
            "location_id": "HN",
            "location_name": "Hà Nội",
            "average_us_aqi": 135.67,
            "maximum_us_aqi": 146,
            "forecast_time": "2026-08-01T21:00:00+07:00",
        }
        daily = {
            "forecast_date": "2026-08-02",
            "point_id": "HN_CENTER",
            "location_id": "HN",
            "point_name": "Trung tâm Hà Nội",
            "average_us_aqi": 135.43,
            "forecast_time": "2026-08-02T20:00:00+07:00",
            "us_aqi": 135.43,
        }
        summary = {
            "batch_id": BATCH_ID,
            "finished_at": "2026-08-01T14:02:21+00:00",
            "outputs": {
                "current_aqi": "current.parquet",
                "location_summary": "location.parquet",
                "daily_summary": "daily.parquet",
                "mart_summary": "mart_summary.json",
            },
        }
        return MartSnapshotBundle(
            summary_object_name="mart_summary.json",
            summary=summary,
            current_aqi=[current],
            location_summary=[location],
            daily_summary=[daily],
        )


def _settings(output_directory: Path) -> SnapshotSettings:
    return SnapshotSettings(
        api_base_url="http://api:8000",
        output_directory=output_directory,
        request_timeout_seconds=5.0,
        latest_limit=5000,
        top_polluted_limit=100,
        location_limit=5000,
        point_limit=168,
        history_hours=168,
        alerts_limit=1000,
    )


def test_mart_publisher_avoids_air_quality_api_and_writes_mart_files(
    tmp_path: Path,
) -> None:
    session = FakeSession()
    output_directory = tmp_path / "snapshots"
    publisher = SnapshotPublisher(
        settings=_settings(output_directory),
        session=session,
        expected_batch_id=BATCH_ID,
        mart_reader=FakeReader(),
    )

    result = publisher.publish()

    assert result["status"] == "SUCCESS"
    assert result["latest_batch_id"] == BATCH_ID
    assert "/api/v1/air-quality/latest" not in session.paths
    assert (output_directory / "air_quality/latest.json").is_file()
    assert (output_directory / "air_quality/location_summary.json").is_file()
    assert (output_directory / "air_quality/daily_summary.json").is_file()
    assert (output_directory / "air_quality/history/HN_CENTER.json").is_file()
