from datetime import datetime, timezone
from pathlib import Path

import pytest

import src.ingestion.minio_air_quality_extractor as extractor_module
from src.ingestion.minio_air_quality_extractor import (
    MonitoringPoint,
    build_batch_prefix,
    build_point_object_name,
    build_summary_object_name,
    extract_monitoring_points_to_minio,
    load_active_monitoring_points,
)
from src.utils.minio_client import (
    MinioSettings,
)


def build_test_settings() -> MinioSettings:
    return MinioSettings(
        endpoint="localhost:9000",
        access_key="testaccess",
        secret_key="testsecret",
        secure=False,
        raw_bucket="air-quality-raw",
        clean_bucket="air-quality-clean",
        mart_bucket="air-quality-mart",
    )


def build_test_point() -> MonitoringPoint:
    return MonitoringPoint(
        point_id="HN_CENTER",
        location_id="HN",
        point_name="Trung tâm Hà Nội",
        point_type="urban_center",
        latitude=21.0285,
        longitude=105.8542,
        is_active=True,
    )


def test_builds_expected_object_names() -> None:
    prefix = build_batch_prefix(
        partition_date="2026-07-13",
        partition_hour="21",
        batch_id="test_batch",
    )

    assert prefix == (
        "open_meteo/air_quality/"
        "date=2026-07-13/"
        "hour=21/"
        "batch_id=test_batch"
    )

    assert build_point_object_name(
        batch_prefix=prefix,
        point_id="HN_CENTER",
    ) == (
        f"{prefix}/"
        "point_id=HN_CENTER/"
        "data.json"
    )

    assert build_summary_object_name(
        prefix
    ) == (
        f"{prefix}/run_summary.json"
    )


def test_loads_only_active_points(
    tmp_path: Path,
) -> None:
    csv_path = (
        tmp_path
        / "monitoring_points.csv"
    )

    csv_path.write_text(
        (
            "point_id,location_id,point_name,"
            "point_type,latitude,longitude,"
            "is_active\n"
            "HN_CENTER,HN,Trung tâm Hà Nội,"
            "urban_center,21.0285,105.8542,"
            "true\n"
            "HCM_CENTER,HCM,Trung tâm TP.HCM,"
            "urban_center,10.7769,106.7009,"
            "false\n"
        ),
        encoding="utf-8",
    )

    points = (
        load_active_monitoring_points(
            csv_path
        )
    )

    assert len(points) == 1

    assert (
        points[0].point_id
        == "HN_CENTER"
    )


def test_extracts_and_writes_minio_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploaded_objects = []

    monkeypatch.setattr(
        extractor_module,
        "ensure_buckets",
        lambda **kwargs: {
            "created_buckets": [],
            "existing_buckets": [],
        },
    )

    def fake_put_json_object(
        bucket_name,
        object_name,
        data,
        **kwargs,
    ):
        uploaded_objects.append(
            {
                "bucket_name": bucket_name,
                "object_name": object_name,
                "data": data,
            }
        )

        return {
            "bucket_name": bucket_name,
            "object_name": object_name,
            "etag": "test-etag",
            "version_id": None,
            "size_bytes": 100,
            "content_type": (
                "application/json"
            ),
        }

    monkeypatch.setattr(
        extractor_module,
        "put_json_object",
        fake_put_json_object,
    )

    def fake_fetch_air_quality(
        point: MonitoringPoint,
    ):
        assert (
            point.point_id
            == "HN_CENTER"
        )

        return {
            "hourly": {
                "time": [
                    "2026-07-13T21:00",
                    "2026-07-13T22:00",
                ],
                "pm2_5": [
                    18.5,
                    19.2,
                ],
            }
        }

    summary = (
        extract_monitoring_points_to_minio(
            monitoring_points=[
                build_test_point()
            ],
            fetch_air_quality=(
                fake_fetch_air_quality
            ),
            settings=(
                build_test_settings()
            ),
            client=object(),
            batch_id="test_batch",
            started_at=datetime(
                2026,
                7,
                13,
                14,
                0,
                tzinfo=timezone.utc,
            ),
        )
    )

    assert summary["status"] == "SUCCESS"

    assert (
        summary["records_extracted"]
        == 2
    )

    assert (
        summary["successful_points"]
        == 1
    )

    assert (
        summary["failed_points"]
        == 0
    )

    assert len(uploaded_objects) == 2

    raw_object = uploaded_objects[0]
    summary_object = uploaded_objects[1]

    assert raw_object[
        "object_name"
    ].endswith(
        "point_id=HN_CENTER/data.json"
    )

    assert (
        raw_object["data"]["point"][
            "location_id"
        ]
        == "HN"
    )

    assert (
        raw_object["data"][
            "api_response"
        ]["hourly"]["time"]
        == [
            "2026-07-13T21:00",
            "2026-07-13T22:00",
        ]
    )

    assert summary_object[
        "object_name"
    ].endswith(
        "run_summary.json"
    )