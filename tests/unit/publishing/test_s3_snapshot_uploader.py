from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError
import pytest

from src.snapshot import (
    S3SnapshotUploader,
    S3SnapshotUploadError,
    S3SnapshotUploadSettings,
    S3SnapshotValidationError,
)
import src.snapshot.s3_uploader as s3_uploader_module

SNAPSHOT_ID = "20260723T090000Z_s3test01"

BUCKET_NAME = "vietnam-air-quality-snapshots-test"


class FakeS3Client:
    """
    S3 client giả lập dùng cho unit test.

    objects lưu object theo S3 key cùng body,
    metadata, content type và cache control.
    """

    def __init__(
        self,
        *,
        fail_on_key: str | None = None,
    ) -> None:
        self.fail_on_key = fail_on_key

        self.objects: dict[
            str,
            dict[str, Any],
        ] = {}

        self.put_calls: list[str] = []
        self.head_calls: list[str] = []

    def head_object(
        self,
        *,
        Bucket: str,
        Key: str,
    ) -> dict[str, Any]:
        assert Bucket == BUCKET_NAME

        self.head_calls.append(Key)

        if Key not in self.objects:
            raise ClientError(
                {
                    "Error": {
                        "Code": "404",
                        "Message": ("Object not found"),
                    }
                },
                "HeadObject",
            )

        stored_object = self.objects[Key]

        return {
            "Metadata": dict(stored_object["Metadata"]),
            "ContentType": (stored_object["ContentType"]),
            "CacheControl": (stored_object["CacheControl"]),
        }

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: Any,
        ContentType: str,
        CacheControl: str,
        Metadata: dict[str, str],
    ) -> dict[str, Any]:
        assert Bucket == BUCKET_NAME

        self.put_calls.append(Key)

        if Key == self.fail_on_key:
            raise ClientError(
                {
                    "Error": {
                        "Code": "AccessDenied",
                        "Message": ("Fake upload failure"),
                    }
                },
                "PutObject",
            )

        if isinstance(
            Body,
            bytes,
        ):
            body_bytes = Body

        elif isinstance(
            Body,
            bytearray,
        ):
            body_bytes = bytes(Body)

        elif hasattr(
            Body,
            "read",
        ):
            body_bytes = Body.read()

        else:
            raise TypeError("Unsupported fake S3 body.")

        self.objects[Key] = {
            "Body": body_bytes,
            "ContentType": ContentType,
            "CacheControl": CacheControl,
            "Metadata": dict(Metadata),
        }

        return {
            "ETag": '"fake-etag"',
            "VersionId": ("fake-version-id"),
        }


def write_json(
    file_path: Path,
    payload: dict[str, Any],
) -> None:
    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with file_path.open(
        mode="w",
        encoding="utf-8",
        newline="\n",
    ) as file_handle:
        json.dump(
            payload,
            file_handle,
            ensure_ascii=False,
            indent=2,
        )

        file_handle.write("\n")


def create_snapshot_tree(
    root_directory: Path,
    *,
    snapshot_id: str = SNAPSHOT_ID,
) -> Path:
    snapshot_directory = root_directory / "public_snapshots"

    write_json(
        snapshot_directory / "health.json",
        {
            "status": "HEALTHY",
            "service": ("vietnam-air-quality-api"),
        },
    )

    write_json(
        snapshot_directory / "air_quality" / "latest.json",
        {
            "status": "SUCCESS",
            "batch_id": ("20260723T085500Z_batch"),
            "record_count": 1,
            "data": [
                {
                    "point_id": ("HN_CENTER"),
                    "location_id": "HN",
                    "location_name": ("Hà Nội"),
                    "us_aqi": 105,
                }
            ],
        },
    )

    manifest_files = [
        "air_quality/latest.json",
        "health.json",
        "manifest.json",
    ]

    write_json(
        snapshot_directory / "manifest.json",
        {
            "schema_version": "1.0",
            "snapshot_id": snapshot_id,
            "generated_at": ("2026-07-23T09:00:00+00:00"),
            "latest_batch_id": ("20260723T085500Z_batch"),
            "files": manifest_files,
        },
    )

    return snapshot_directory


def build_settings(
    input_directory: Path,
) -> S3SnapshotUploadSettings:
    return S3SnapshotUploadSettings(
        bucket_name=BUCKET_NAME,
        region_name="ap-southeast-2",
        profile_name=None,
        input_directory=(input_directory),
        release_root_prefix=("releases"),
        pointer_key="current.json",
    )


def test_upload_creates_release_and_pointer(
    tmp_path: Path,
) -> None:
    snapshot_directory = create_snapshot_tree(tmp_path)

    client = FakeS3Client()

    uploader = S3SnapshotUploader(
        settings=build_settings(snapshot_directory),
        client=client,
    )

    result = uploader.upload()

    release_prefix = f"releases/{SNAPSHOT_ID}"

    expected_release_keys = {
        (f"{release_prefix}/air_quality/latest.json"),
        (f"{release_prefix}/health.json"),
        (f"{release_prefix}/manifest.json"),
    }

    assert result["status"] == "SUCCESS"
    assert result["snapshot_id"] == SNAPSHOT_ID

    assert result["region_name"] == ("ap-southeast-2")

    assert result["local_file_count"] == 3

    assert result["uploaded_file_count"] == 3

    assert result["skipped_file_count"] == 0

    assert result["pointer_uploaded"] is True

    assert set(client.objects) == {
        *expected_release_keys,
        "current.json",
    }

    assert client.put_calls[-1] == ("current.json")

    assert client.put_calls[-2] == (f"{release_prefix}/manifest.json")


def test_release_and_pointer_use_correct_metadata(
    tmp_path: Path,
) -> None:
    snapshot_directory = create_snapshot_tree(tmp_path)

    client = FakeS3Client()

    uploader = S3SnapshotUploader(
        settings=build_settings(snapshot_directory),
        client=client,
    )

    uploader.upload()

    release_manifest_key = f"releases/{SNAPSHOT_ID}/manifest.json"

    release_object = client.objects[release_manifest_key]

    pointer_object = client.objects["current.json"]

    assert release_object["ContentType"] == ("application/json; charset=utf-8")

    assert release_object["CacheControl"] == ("public, max-age=31536000, immutable")

    assert release_object["Metadata"]["snapshot-id"] == SNAPSHOT_ID

    assert release_object["Metadata"]["sha256"]

    assert pointer_object["ContentType"] == ("application/json; charset=utf-8")

    assert pointer_object["CacheControl"] == (
        "max-age=0, no-cache, no-store, must-revalidate"
    )

    pointer_payload = json.loads(pointer_object["Body"].decode("utf-8"))

    assert pointer_payload["snapshot_id"] == SNAPSHOT_ID

    assert pointer_payload["release_prefix"] == (f"releases/{SNAPSHOT_ID}")

    assert pointer_payload["manifest_key"] == (f"releases/{SNAPSHOT_ID}/manifest.json")


def test_same_snapshot_is_idempotent(
    tmp_path: Path,
) -> None:
    snapshot_directory = create_snapshot_tree(tmp_path)

    client = FakeS3Client()

    uploader = S3SnapshotUploader(
        settings=build_settings(snapshot_directory),
        client=client,
    )

    first_result = uploader.upload()

    first_put_count = len(client.put_calls)

    second_result = uploader.upload()

    assert first_result["uploaded_file_count"] == 3

    assert first_result["pointer_uploaded"] is True

    assert second_result["uploaded_file_count"] == 0

    assert second_result["skipped_file_count"] == 3

    assert second_result["pointer_uploaded"] is False

    assert len(client.put_calls) == first_put_count


def test_pointer_is_not_updated_when_release_upload_fails(
    tmp_path: Path,
) -> None:
    snapshot_directory = create_snapshot_tree(tmp_path)

    failing_key = f"releases/{SNAPSHOT_ID}/manifest.json"

    client = FakeS3Client(fail_on_key=failing_key)

    uploader = S3SnapshotUploader(
        settings=build_settings(snapshot_directory),
        client=client,
    )

    with pytest.raises(
        S3SnapshotUploadError,
        match=("Không thể hoàn tất S3 snapshot upload"),
    ):
        uploader.upload()

    assert "current.json" not in (client.objects)

    assert "current.json" not in (client.put_calls)


def test_missing_manifest_is_rejected(
    tmp_path: Path,
) -> None:
    snapshot_directory = tmp_path / "public_snapshots"

    write_json(
        snapshot_directory / "health.json",
        {
            "status": "HEALTHY",
        },
    )

    uploader = S3SnapshotUploader(
        settings=build_settings(snapshot_directory),
        client=FakeS3Client(),
    )

    with pytest.raises(
        S3SnapshotValidationError,
        match=("Không tìm thấy manifest.json"),
    ):
        uploader.upload()


def test_unlisted_json_file_is_rejected(
    tmp_path: Path,
) -> None:
    snapshot_directory = create_snapshot_tree(tmp_path)

    write_json(
        snapshot_directory / "unexpected.json",
        {
            "unexpected": True,
        },
    )

    uploader = S3SnapshotUploader(
        settings=build_settings(snapshot_directory),
        client=FakeS3Client(),
    )

    with pytest.raises(
        S3SnapshotValidationError,
        match=("file không có trong manifest"),
    ):
        uploader.upload()


def test_unsafe_snapshot_id_is_rejected(
    tmp_path: Path,
) -> None:
    snapshot_directory = create_snapshot_tree(
        tmp_path,
        snapshot_id="../unsafe",
    )

    uploader = S3SnapshotUploader(
        settings=build_settings(snapshot_directory),
        client=FakeS3Client(),
    )

    with pytest.raises(
        S3SnapshotValidationError,
        match=("snapshot_id không an toàn"),
    ):
        uploader.upload()


def test_settings_default_to_sydney_region(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        s3_uploader_module,
        "load_dotenv",
        lambda: None,
    )
    monkeypatch.setenv(
        "AWS_SNAPSHOT_BUCKET",
        BUCKET_NAME,
    )
    monkeypatch.delenv(
        "AWS_SNAPSHOT_REGION",
        raising=False,
    )
    monkeypatch.setenv(
        "AWS_SNAPSHOT_INPUT_DIRECTORY",
        str(tmp_path / "public_snapshots"),
    )

    settings = S3SnapshotUploadSettings.from_environment()

    assert settings.region_name == "ap-southeast-2"


def test_settings_read_sydney_region(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AWS_SNAPSHOT_BUCKET",
        BUCKET_NAME,
    )

    monkeypatch.setenv(
        "AWS_SNAPSHOT_REGION",
        "ap-southeast-2",
    )

    monkeypatch.setenv(
        "AWS_SNAPSHOT_PROFILE",
        "air-quality-uploader",
    )

    monkeypatch.setenv(
        "AWS_SNAPSHOT_INPUT_DIRECTORY",
        str(tmp_path / "public_snapshots"),
    )

    monkeypatch.setenv(
        "AWS_SNAPSHOT_RELEASE_PREFIX",
        "releases",
    )

    monkeypatch.setenv(
        "AWS_SNAPSHOT_POINTER_KEY",
        "current.json",
    )

    settings = S3SnapshotUploadSettings.from_environment()

    assert settings.region_name == ("ap-southeast-2")

    assert settings.profile_name == ("air-quality-uploader")

    assert settings.bucket_name == (BUCKET_NAME)

    assert settings.release_root_prefix == ("releases")

    assert settings.pointer_key == ("current.json")


def test_upload_rejects_manifest_batch_that_differs_from_expected(
    tmp_path: Path,
) -> None:
    snapshot_directory = create_snapshot_tree(tmp_path)
    uploader = S3SnapshotUploader(
        settings=build_settings(snapshot_directory),
        client=FakeS3Client(),
        expected_batch_id="ANOTHER_BATCH",
    )

    with pytest.raises(
        S3SnapshotValidationError,
        match="không khớp batch_id",
    ):
        uploader.upload()
