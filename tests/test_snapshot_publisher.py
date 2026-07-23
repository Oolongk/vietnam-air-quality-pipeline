from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
import requests

from src.snapshot import (
    SnapshotAPIError,
    SnapshotConfigurationError,
    SnapshotPublisher,
    SnapshotSettings,
    SnapshotValidationError,
)


BATCH_ID = (
    "20260723T010000Z_snapshot_test"
)


class FakeResponse:
    def __init__(
        self,
        payload: Any,
        status_code: int = 200,
    ) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(
        self,
    ) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(
                "Fake HTTP error",
                response=self,
            )

    def json(
        self,
    ) -> Any:
        return copy.deepcopy(
            self._payload
        )


class FakeSession:
    def __init__(
        self,
        payloads: dict[str, Any],
        failing_paths: set[str]
        | None = None,
    ) -> None:
        self.payloads = payloads
        self.failing_paths = (
            failing_paths
            or set()
        )

        self.calls: list[
            dict[str, Any]
        ] = []

    def get(
        self,
        *,
        url: str,
        params: dict[str, Any]
        | None = None,
        timeout: float
        | None = None,
    ) -> FakeResponse:
        path = urlparse(
            url
        ).path

        self.calls.append(
            {
                "path": path,
                "params": copy.deepcopy(
                    params
                ),
                "timeout": timeout,
            }
        )

        if path in self.failing_paths:
            raise requests.ConnectionError(
                "Fake API connection failure"
            )

        if path not in self.payloads:
            raise AssertionError(
                "Test chưa cấu hình payload "
                f"cho endpoint: {path}"
            )

        return FakeResponse(
            payload=self.payloads[
                path
            ]
        )


def build_air_quality_record(
) -> dict[str, Any]:
    return {
        "point_id": "HN_CENTER",
        "location_id": "HN",
        "point_name": "Hà Nội Center",
        "point_type": "urban_center",
        "location_name": "Hà Nội",
        "region": "Miền Bắc",
        "admin_type": (
            "Thành phố trực thuộc "
            "Trung ương"
        ),
        "latitude": 21.0285,
        "longitude": 105.8542,
        "forecast_time": (
            "2026-07-23T08:00:00+07:00"
        ),
        "pm2_5": 35.5,
        "pm10": 48.0,
        "carbon_monoxide": 250.0,
        "nitrogen_dioxide": 18.0,
        "sulphur_dioxide": 4.0,
        "ozone": 72.0,
        "us_aqi": 105,
        "aqi_level": (
            "Không tốt cho nhóm nhạy cảm"
        ),
        "aqi_severity": (
            "UNHEALTHY_SENSITIVE"
        ),
        "source": "open_meteo",
        "batch_id": BATCH_ID,
        "schema_version": "1.0",
        "ingested_at": (
            "2026-07-23T01:05:00+00:00"
        ),
    }


def build_api_payloads(
) -> dict[str, Any]:
    air_quality_record = (
        build_air_quality_record()
    )

    return {
        "/health": {
            "status": "HEALTHY",
            "service": (
                "vietnam-air-quality-api"
            ),
            "database": (
                "air_quality_db"
            ),
            "database_time": (
                "2026-07-23T01:05:00+00:00"
            ),
        },
        "/api/v1/locations": {
            "status": "SUCCESS",
            "record_count": 1,
            "data": [
                {
                    "location_id": "HN",
                    "location_name": (
                        "Hà Nội"
                    ),
                    "region": (
                        "Miền Bắc"
                    ),
                    "admin_type": (
                        "Thành phố trực thuộc "
                        "Trung ương"
                    ),
                    "is_active": True,
                    "created_at": (
                        "2026-07-01T00:00:00"
                        "+00:00"
                    ),
                    "updated_at": (
                        "2026-07-01T00:00:00"
                        "+00:00"
                    ),
                }
            ],
        },
        "/api/v1/monitoring-points": {
            "status": "SUCCESS",
            "record_count": 1,
            "data": [
                {
                    "point_id": (
                        "HN_CENTER"
                    ),
                    "location_id": "HN",
                    "point_name": (
                        "Hà Nội Center"
                    ),
                    "point_type": (
                        "urban_center"
                    ),
                    "latitude": 21.0285,
                    "longitude": 105.8542,
                    "is_active": True,
                    "location_name": (
                        "Hà Nội"
                    ),
                    "region": (
                        "Miền Bắc"
                    ),
                    "admin_type": (
                        "Thành phố trực thuộc "
                        "Trung ương"
                    ),
                }
            ],
        },
        "/api/v1/air-quality/latest": {
            "status": "SUCCESS",
            "batch_id": BATCH_ID,
            "record_count": 1,
            "data": [
                air_quality_record
            ],
        },
        (
            "/api/v1/air-quality/"
            "top-polluted"
        ): {
            "status": "SUCCESS",
            "batch_id": BATCH_ID,
            "reference_time": (
                air_quality_record[
                    "forecast_time"
                ]
            ),
            "record_count": 1,
            "data": [
                air_quality_record
            ],
        },
        "/api/v1/alerts/latest": {
            "status": "SUCCESS",
            "record_count": 1,
            "data": [
                {
                    "alert_id": 1,
                    "point_id": (
                        "HN_CENTER"
                    ),
                    "location_id": "HN",
                    "alert_time": (
                        air_quality_record[
                            "forecast_time"
                        ]
                    ),
                    "aqi_value": 105,
                    "aqi_level": (
                        "Không tốt cho "
                        "nhóm nhạy cảm"
                    ),
                    "severity": "MEDIUM",
                    "message": (
                        "AQI vượt ngưỡng "
                        "cảnh báo."
                    ),
                    "status": "ACTIVE",
                    "source": (
                        "open_meteo"
                    ),
                    "created_at": (
                        "2026-07-23T01:05:00"
                        "+00:00"
                    ),
                }
            ],
        },
        (
            "/api/v1/pipeline/"
            "health/latest"
        ): {
            "status": "SUCCESS",
            "batch_id": BATCH_ID,
            "stage_count": 1,
            "data": [
                {
                    "run_id": (
                        f"{BATCH_ID}:extract"
                    ),
                    "batch_id": BATCH_ID,
                    "stage_name": (
                        "extract"
                    ),
                    "status": "SUCCESS",
                }
            ],
        },
        (
            "/api/v1/data-quality/"
            "latest"
        ): {
            "status": "PASSED",
            "check_count": 1,
            "failed_check_count": 0,
            "data": [
                {
                    "run_id": (
                        f"{BATCH_ID}:"
                        "data_quality"
                    ),
                    "batch_id": BATCH_ID,
                    "check_name": (
                        "required_columns_check"
                    ),
                    "status": "PASSED",
                    "bad_records_count": 0,
                }
            ],
        },
        (
            "/api/v1/air-quality/"
            "locations/HN"
        ): {
            "status": "SUCCESS",
            "location_id": "HN",
            "location_name": (
                "Hà Nội"
            ),
            "batch_id": BATCH_ID,
            "record_count": 1,
            "data": [
                air_quality_record
            ],
        },
        (
            "/api/v1/air-quality/"
            "points/HN_CENTER"
        ): {
            "status": "SUCCESS",
            "point_id": "HN_CENTER",
            "batch_id": BATCH_ID,
            "record_count": 1,
            "data": [
                air_quality_record
            ],
        },
        (
            "/api/v1/air-quality/"
            "history"
        ): {
            "status": "SUCCESS",
            "point_id": "HN_CENTER",
            "point_name": (
                "Hà Nội Center"
            ),
            "location_id": "HN",
            "location_name": (
                "Hà Nội"
            ),
            "requested_hours": 168,
            "record_count": 1,
            "first_forecast_time": (
                air_quality_record[
                    "forecast_time"
                ]
            ),
            "last_forecast_time": (
                air_quality_record[
                    "forecast_time"
                ]
            ),
            "data": [
                air_quality_record
            ],
        },
    }


def build_settings(
    output_directory: Path,
) -> SnapshotSettings:
    return SnapshotSettings(
        api_base_url=(
            "http://fake-api:8000"
        ),
        output_directory=(
            output_directory
        ),
        request_timeout_seconds=5.0,
        latest_limit=2000,
        top_polluted_limit=100,
        location_limit=2000,
        point_limit=168,
        history_hours=168,
        alerts_limit=1000,
    )


def read_json_file(
    file_path: Path,
) -> dict[str, Any]:
    with file_path.open(
        mode="r",
        encoding="utf-8",
    ) as file_handle:
        payload = json.load(
            file_handle
        )

    assert isinstance(
        payload,
        dict,
    )

    return payload


def test_publish_creates_complete_snapshot_tree(
    tmp_path: Path,
) -> None:
    output_directory = (
        tmp_path
        / "public_snapshots"
    )

    session = FakeSession(
        build_api_payloads()
    )

    publisher = SnapshotPublisher(
        settings=build_settings(
            output_directory
        ),
        session=session,
    )

    result = publisher.publish()

    assert result["status"] == "SUCCESS"
    assert result["latest_batch_id"] == BATCH_ID
    assert result["location_count"] == 1
    assert result["point_count"] == 1
    assert result["file_count"] == 12

    expected_files = {
        "health.json",
        "locations.json",
        "monitoring_points.json",
        "manifest.json",
        "air_quality/latest.json",
        "air_quality/top_polluted.json",
        "air_quality/locations/HN.json",
        (
            "air_quality/points/"
            "HN_CENTER.json"
        ),
        (
            "air_quality/history/"
            "HN_CENTER.json"
        ),
        "alerts/latest.json",
        "pipeline/health.json",
        "data_quality/latest.json",
    }

    actual_files = {
        file_path
        .relative_to(
            output_directory
        )
        .as_posix()
        for file_path in (
            output_directory.rglob(
                "*.json"
            )
        )
    }

    assert actual_files == expected_files

    manifest = read_json_file(
        output_directory
        / "manifest.json"
    )

    assert manifest[
        "schema_version"
    ] == "1.0"

    assert manifest[
        "latest_batch_id"
    ] == BATCH_ID

    assert manifest[
        "source"
    ][
        "base_url"
    ] == "http://fake-api:8000"

    assert manifest[
        "counts"
    ][
        "locations"
    ] == 1

    assert manifest[
        "counts"
    ][
        "monitoring_points"
    ] == 1

    assert manifest[
        "counts"
    ][
        "location_snapshots"
    ] == 1

    assert manifest[
        "counts"
    ][
        "point_snapshots"
    ] == 1

    assert manifest[
        "counts"
    ][
        "history_snapshots"
    ] == 1

    assert len(
        manifest["files"]
    ) == 12

    locations_payload = read_json_file(
        output_directory
        / "locations.json"
    )

    assert locations_payload[
        "data"
    ][0][
        "location_name"
    ] == "Hà Nội"

    assert len(
        session.calls
    ) == 11

    history_call = next(
        call
        for call in session.calls
        if call["path"] == (
            "/api/v1/"
            "air-quality/history"
        )
    )

    assert history_call["params"] == {
        "point_id": "HN_CENTER",
        "hours": 168,
    }

    assert history_call[
        "timeout"
    ] == 5.0


def test_publish_replaces_existing_snapshot(
    tmp_path: Path,
) -> None:
    output_directory = (
        tmp_path
        / "public_snapshots"
    )

    output_directory.mkdir(
        parents=True
    )

    old_marker = (
        output_directory
        / "old_snapshot.txt"
    )

    old_marker.write_text(
        "old snapshot",
        encoding="utf-8",
    )

    publisher = SnapshotPublisher(
        settings=build_settings(
            output_directory
        ),
        session=FakeSession(
            build_api_payloads()
        ),
    )

    publisher.publish()

    assert not old_marker.exists()

    assert (
        output_directory
        / "manifest.json"
    ).is_file()

    assert (
        output_directory
        / "air_quality"
        / "latest.json"
    ).is_file()


def test_api_failure_preserves_existing_snapshot(
    tmp_path: Path,
) -> None:
    output_directory = (
        tmp_path
        / "public_snapshots"
    )

    output_directory.mkdir(
        parents=True
    )

    old_manifest = (
        output_directory
        / "manifest.json"
    )

    old_manifest.write_text(
        (
            '{\n'
            '  "snapshot_id": '
            '"old_snapshot"\n'
            '}\n'
        ),
        encoding="utf-8",
    )

    old_content = old_manifest.read_text(
        encoding="utf-8"
    )

    session = FakeSession(
        payloads=build_api_payloads(),
        failing_paths={
            (
                "/api/v1/air-quality/"
                "top-polluted"
            ),
        },
    )

    publisher = SnapshotPublisher(
        settings=build_settings(
            output_directory
        ),
        session=session,
    )

    with pytest.raises(
        SnapshotAPIError,
        match="top-polluted",
    ):
        publisher.publish()

    assert old_manifest.is_file()

    assert (
        old_manifest.read_text(
            encoding="utf-8"
        )
        == old_content
    )

    staging_directories = list(
        tmp_path.glob(
            ".public_snapshots."
            "staging-*"
        )
    )

    assert staging_directories == []


def test_missing_required_field_is_rejected(
    tmp_path: Path,
) -> None:
    payloads = build_api_payloads()

    del payloads[
        "/api/v1/locations"
    ][
        "data"
    ]

    output_directory = (
        tmp_path
        / "public_snapshots"
    )

    publisher = SnapshotPublisher(
        settings=build_settings(
            output_directory
        ),
        session=FakeSession(
            payloads
        ),
    )

    with pytest.raises(
        SnapshotValidationError,
        match="thiếu field: data",
    ):
        publisher.publish()

    assert not output_directory.exists()

    assert list(
        tmp_path.glob(
            ".public_snapshots."
            "staging-*"
        )
    ) == []


def test_unsafe_identifier_is_rejected(
    tmp_path: Path,
) -> None:
    payloads = build_api_payloads()

    payloads[
        "/api/v1/locations"
    ][
        "data"
    ][0][
        "location_id"
    ] = "../HN"

    output_directory = (
        tmp_path
        / "public_snapshots"
    )

    publisher = SnapshotPublisher(
        settings=build_settings(
            output_directory
        ),
        session=FakeSession(
            payloads
        ),
    )

    with pytest.raises(
        SnapshotValidationError,
        match=(
            "không an toàn để dùng "
            "làm tên file"
        ),
    ):
        publisher.publish()

    assert not output_directory.exists()


def test_settings_reject_invalid_api_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "SNAPSHOT_API_BASE_URL",
        "localhost:8000",
    )

    with pytest.raises(
        SnapshotConfigurationError,
        match="http:// hoặc https://",
    ):
        SnapshotSettings.from_environment()


def test_settings_reject_invalid_history_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "SNAPSHOT_API_BASE_URL",
        "http://127.0.0.1:8000",
    )

    monkeypatch.setenv(
        "SNAPSHOT_HISTORY_HOURS",
        "0",
    )

    with pytest.raises(
        SnapshotConfigurationError,
        match=(
            "SNAPSHOT_HISTORY_HOURS "
            "phải nằm trong khoảng"
        ),
    ):
        SnapshotSettings.from_environment()