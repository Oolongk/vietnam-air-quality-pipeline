from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from src.ingestion.air_quality_extractor import (
    extract_active_monitoring_points,
)


TEST_TIMEZONE = timezone(
    timedelta(hours=7),
    name="Asia/Ho_Chi_Minh",
)


class FakeOpenMeteoClient:
    def fetch_hourly_air_quality(
        self,
        point_id: str,
        location_id: str,
        latitude: float,
        longitude: float,
        forecast_hours: int = 24,
        timezone_name: str = "Asia/Ho_Chi_Minh",
        domain: str = "cams_global",
    ) -> dict:
        return {
            "schema_version": "1.0",
            "source": "open_meteo",
            "ingested_at": (
                "2026-07-11T05:00:00+00:00"
            ),
            "request": {
                "point_id": point_id,
                "location_id": location_id,
                "latitude": latitude,
                "longitude": longitude,
                "forecast_hours": (
                    forecast_hours
                ),
                "timezone": timezone_name,
                "domain": domain,
                "hourly_variables": [
                    "pm2_5",
                    "pm10",
                ],
            },
            "response": {
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone_name,
                "utc_offset_seconds": 25200,
                "hourly_units": {
                    "time": "iso8601",
                    "pm2_5": "μg/m³",
                    "pm10": "μg/m³",
                },
                "hourly": {
                    "time": [
                        "2026-07-11T12:00",
                        "2026-07-11T13:00",
                    ],
                    "pm2_5": [
                        18.5,
                        19.2,
                    ],
                    "pm10": [
                        27.4,
                        28.1,
                    ],
                },
            },
        }


class PartiallyFailingClient(
    FakeOpenMeteoClient
):
    def fetch_hourly_air_quality(
        self,
        point_id: str,
        location_id: str,
        latitude: float,
        longitude: float,
        forecast_hours: int = 24,
        timezone_name: str = "Asia/Ho_Chi_Minh",
        domain: str = "cams_global",
    ) -> dict:
        if point_id == "HCM_CENTER":
            raise ValueError(
                "Lỗi giả lập cho HCM_CENTER."
            )

        return super().fetch_hourly_air_quality(
            point_id=point_id,
            location_id=location_id,
            latitude=latitude,
            longitude=longitude,
            forecast_hours=forecast_hours,
            timezone_name=timezone_name,
            domain=domain,
        )


def build_monitoring_points() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "point_id": "HN_CENTER",
                "location_id": "HN",
                "latitude": 21.0285,
                "longitude": 105.8542,
                "is_active": True,
            },
            {
                "point_id": "HCM_CENTER",
                "location_id": "HCM",
                "latitude": 10.7769,
                "longitude": 106.7009,
                "is_active": True,
            },
            {
                "point_id": "DN_DISABLED",
                "location_id": "DN",
                "latitude": 16.0544,
                "longitude": 108.2022,
                "is_active": False,
            },
        ]
    )


def test_extract_writes_one_raw_file_per_active_point(
    tmp_path: Path,
) -> None:
    summary = extract_active_monitoring_points(
        monitoring_points=(
            build_monitoring_points()
        ),
        client=FakeOpenMeteoClient(),
        raw_root=tmp_path,
        forecast_hours=2,
        run_time=datetime(
            2026,
            7,
            11,
            12,
            30,
            tzinfo=TEST_TIMEZONE,
        ),
        batch_id="test_batch",
    )

    assert summary["status"] == "SUCCESS"
    assert summary["total_active_points"] == 2
    assert summary["succeeded_points"] == 2
    assert summary["failed_points"] == 0
    assert summary["records_extracted"] == 4

    batch_directory = (
        tmp_path
        / "open_meteo"
        / "air_quality"
        / "date=2026-07-11"
        / "hour=12"
        / "batch_id=test_batch"
    )

    assert (
        batch_directory
        / "point_id=HN_CENTER"
        / "data.json"
    ).exists()

    assert (
        batch_directory
        / "point_id=HCM_CENTER"
        / "data.json"
    ).exists()

    assert not (
        batch_directory
        / "point_id=DN_DISABLED"
        / "data.json"
    ).exists()

    assert (
        batch_directory
        / "run_summary.json"
    ).exists()


def test_extract_reports_partial_success(
    tmp_path: Path,
) -> None:
    summary = extract_active_monitoring_points(
        monitoring_points=(
            build_monitoring_points()
        ),
        client=PartiallyFailingClient(),
        raw_root=tmp_path,
        forecast_hours=2,
        run_time=datetime(
            2026,
            7,
            11,
            12,
            30,
            tzinfo=TEST_TIMEZONE,
        ),
        batch_id="partial_batch",
    )

    assert (
        summary["status"]
        == "PARTIAL_SUCCESS"
    )
    assert summary["succeeded_points"] == 1
    assert summary["failed_points"] == 1
    assert summary["records_extracted"] == 2
    assert (
        summary["failures"][0]["point_id"]
        == "HCM_CENTER"
    )