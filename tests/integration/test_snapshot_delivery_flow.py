from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.snapshot import (
    S3SnapshotUploader,
    S3SnapshotUploadSettings,
    SnapshotPublisher,
    SnapshotSettings,
)
from tests.unit.publishing.test_s3_snapshot_uploader import (
    BUCKET_NAME,
    FakeS3Client,
)
from tests.unit.publishing.test_snapshot_publisher import (
    FakeSession,
    build_api_payloads,
)


@pytest.mark.integration
def test_snapshot_publish_and_s3_upload_flow(
    tmp_path: Path,
) -> None:
    snapshot_directory = tmp_path / "public_snapshots"

    api_session = FakeSession(payloads=build_api_payloads())

    snapshot_settings = SnapshotSettings(
        api_base_url=("https://api.example.test"),
        output_directory=(snapshot_directory),
        request_timeout_seconds=5.0,
        latest_limit=5000,
        top_polluted_limit=100,
        location_limit=5000,
        point_limit=168,
        history_hours=168,
        alerts_limit=1000,
    )

    publisher = SnapshotPublisher(
        settings=snapshot_settings,
        session=api_session,
    )

    publish_result = publisher.publish()

    assert publish_result["status"] == "SUCCESS"

    assert snapshot_directory.is_dir()

    assert (snapshot_directory / "manifest.json").is_file()

    assert (snapshot_directory / "air_quality" / "latest.json").is_file()

    s3_client = FakeS3Client()

    upload_settings = S3SnapshotUploadSettings(
        bucket_name=BUCKET_NAME,
        region_name=("ap-southeast-2"),
        profile_name=None,
        input_directory=(snapshot_directory),
        release_root_prefix=("releases"),
        pointer_key="current.json",
    )

    uploader = S3SnapshotUploader(
        settings=upload_settings,
        client=s3_client,
    )

    upload_result = uploader.upload()

    assert upload_result["status"] == "SUCCESS"

    assert upload_result["snapshot_id"] == publish_result["snapshot_id"]

    assert upload_result["local_file_count"] == publish_result["file_count"]

    release_prefix = upload_result["release_prefix"]

    manifest_key = f"{release_prefix}/manifest.json"

    latest_key = f"{release_prefix}/air_quality/latest.json"

    assert manifest_key in (s3_client.objects)

    assert latest_key in (s3_client.objects)

    assert "current.json" in (s3_client.objects)

    # Pointer phải được ghi sau toàn bộ release.
    assert s3_client.put_calls[-1] == ("current.json")

    pointer_payload = json.loads(
        s3_client.objects["current.json"]["Body"].decode("utf-8")
    )

    assert pointer_payload["snapshot_id"] == publish_result["snapshot_id"]

    assert pointer_payload["latest_batch_id"] == publish_result["latest_batch_id"]

    assert pointer_payload["release_prefix"] == release_prefix

    assert pointer_payload["manifest_key"] == manifest_key

    latest_payload = json.loads(s3_client.objects[latest_key]["Body"].decode("utf-8"))

    assert latest_payload["status"] == "SUCCESS"

    assert latest_payload["batch_id"] == publish_result["latest_batch_id"]

    assert latest_payload["record_count"] == 1
