from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    ProfileNotFound,
)
from dotenv import load_dotenv

BUCKET_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")

SAFE_SNAPSHOT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"

POINTER_CACHE_CONTROL = "max-age=0, no-cache, no-store, must-revalidate"


class S3SnapshotConfigurationError(ValueError):
    """Cấu hình S3 Snapshot Uploader không hợp lệ."""


class S3SnapshotValidationError(RuntimeError):
    """Bộ snapshot local không đúng contract."""


class S3SnapshotUploadError(RuntimeError):
    """Không thể upload snapshot lên Amazon S3."""


@dataclass(frozen=True)
class S3SnapshotUploadSettings:
    bucket_name: str
    region_name: str
    profile_name: str | None

    input_directory: Path
    release_root_prefix: str
    pointer_key: str

    @classmethod
    def from_environment(
        cls,
    ) -> "S3SnapshotUploadSettings":
        load_dotenv()

        bucket_name = _required_environment("AWS_SNAPSHOT_BUCKET")

        region_name = os.getenv(
            "AWS_SNAPSHOT_REGION",
            "ap-southeast-2",
        ).strip()

        if not region_name:
            raise S3SnapshotConfigurationError("AWS_SNAPSHOT_REGION không được rỗng.")

        profile_value = (
            os.getenv("AWS_SNAPSHOT_PROFILE")
            or os.getenv("AWS_PROFILE")
            or "air-quality-uploader"
        )

        profile_name = profile_value.strip() if profile_value else None

        input_directory_value = os.getenv(
            "AWS_SNAPSHOT_INPUT_DIRECTORY",
            "data/public_snapshots",
        )

        input_directory = Path(input_directory_value).expanduser()

        if not input_directory.is_absolute():
            input_directory = Path.cwd() / input_directory

        release_root_prefix = _normalize_s3_key(
            os.getenv(
                "AWS_SNAPSHOT_RELEASE_PREFIX",
                "releases",
            ),
            field_name=("AWS_SNAPSHOT_RELEASE_PREFIX"),
        )

        pointer_key = _normalize_s3_key(
            os.getenv(
                "AWS_SNAPSHOT_POINTER_KEY",
                "current.json",
            ),
            field_name=("AWS_SNAPSHOT_POINTER_KEY"),
        )

        if not pointer_key.endswith(".json"):
            raise S3SnapshotConfigurationError(
                "AWS_SNAPSHOT_POINTER_KEY phải kết thúc bằng .json."
            )

        return cls(
            bucket_name=bucket_name,
            region_name=region_name,
            profile_name=profile_name,
            input_directory=(input_directory.resolve()),
            release_root_prefix=(release_root_prefix),
            pointer_key=pointer_key,
        )


def _required_environment(
    name: str,
) -> str:
    raw_value = os.getenv(name)

    if raw_value is None:
        raise S3SnapshotConfigurationError(f"Thiếu biến môi trường: {name}")

    cleaned_value = raw_value.strip()

    if not cleaned_value:
        raise S3SnapshotConfigurationError(f"{name} không được rỗng.")

    return cleaned_value


def _validate_bucket_name(
    bucket_name: str,
) -> None:
    if not BUCKET_NAME_PATTERN.fullmatch(bucket_name):
        raise S3SnapshotConfigurationError(
            "AWS_SNAPSHOT_BUCKET không phải tên S3 bucket hợp lệ."
        )

    if ".." in bucket_name or ".-" in bucket_name or "-." in bucket_name:
        raise S3SnapshotConfigurationError(
            "AWS_SNAPSHOT_BUCKET chứa chuỗi dấu không hợp lệ."
        )


def _normalize_s3_key(
    value: str,
    field_name: str,
) -> str:
    normalized_value = value.replace("\\", "/").strip("/").strip()

    if not normalized_value:
        raise S3SnapshotConfigurationError(f"{field_name} không được rỗng.")

    if "/../" in (f"/{normalized_value}/"):
        raise S3SnapshotConfigurationError(f"{field_name} không được chứa '..'.")

    return normalized_value


def build_s3_client(
    settings: S3SnapshotUploadSettings,
) -> BaseClient:
    try:
        session = boto3.Session(
            profile_name=(settings.profile_name),
            region_name=(settings.region_name),
        )

        return session.client("s3")

    except ProfileNotFound as error:
        raise S3SnapshotConfigurationError(
            f"Không tìm thấy AWS profile: {settings.profile_name!r}."
        ) from error

    except (
        BotoCoreError,
        NoCredentialsError,
    ) as error:
        raise S3SnapshotConfigurationError(
            f"Không thể khởi tạo AWS session: {error}"
        ) from error


class S3SnapshotUploader:
    def __init__(
        self,
        settings: S3SnapshotUploadSettings,
        client: BaseClient | None = None,
        expected_batch_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or build_s3_client(settings)

        if expected_batch_id is None:
            self.expected_batch_id = None
        else:
            normalized_expected_batch_id = str(expected_batch_id).strip()
            if not normalized_expected_batch_id:
                raise S3SnapshotConfigurationError("expected_batch_id không được rỗng.")
            self.expected_batch_id = normalized_expected_batch_id

    def upload(
        self,
    ) -> dict[str, Any]:
        manifest, snapshot_files = self._load_and_validate_snapshot()

        snapshot_id = str(manifest["snapshot_id"])

        release_prefix = f"{self.settings.release_root_prefix}/{snapshot_id}"

        uploaded_keys: list[str] = []
        skipped_keys: list[str] = []

        ordered_relative_paths = sorted(
            relative_path
            for relative_path in snapshot_files
            if relative_path != "manifest.json"
        )

        ordered_relative_paths.append("manifest.json")

        try:
            for relative_path in ordered_relative_paths:
                source_path = self.settings.input_directory / Path(relative_path)

                object_key = f"{release_prefix}/{relative_path}"

                file_digest = _calculate_sha256(source_path)

                if self._remote_object_matches(
                    object_key=object_key,
                    expected_sha256=(file_digest),
                ):
                    skipped_keys.append(object_key)

                    continue

                self._put_json_file(
                    source_path=source_path,
                    object_key=object_key,
                    snapshot_id=snapshot_id,
                    sha256_digest=(file_digest),
                    cache_control=(IMMUTABLE_CACHE_CONTROL),
                )

                uploaded_keys.append(object_key)

            pointer_payload = {
                "schema_version": "1.0",
                "snapshot_id": snapshot_id,
                "generated_at": (manifest.get("generated_at")),
                "latest_batch_id": (manifest.get("latest_batch_id")),
                "release_prefix": (release_prefix),
                "manifest_key": (f"{release_prefix}/manifest.json"),
            }

            pointer_body = (
                json.dumps(
                    pointer_payload,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")

            pointer_sha256 = hashlib.sha256(pointer_body).hexdigest()

            pointer_uploaded = False

            if not self._remote_object_matches(
                object_key=(self.settings.pointer_key),
                expected_sha256=(pointer_sha256),
            ):
                self._put_json_bytes(
                    body=pointer_body,
                    object_key=(self.settings.pointer_key),
                    snapshot_id=snapshot_id,
                    sha256_digest=(pointer_sha256),
                    cache_control=(POINTER_CACHE_CONTROL),
                )

                pointer_uploaded = True

        except (
            ClientError,
            BotoCoreError,
            OSError,
        ) as error:
            raise S3SnapshotUploadError(
                f"Không thể hoàn tất S3 snapshot upload: {error}"
            ) from error

        return {
            "status": "SUCCESS",
            "bucket_name": (self.settings.bucket_name),
            "region_name": (self.settings.region_name),
            "snapshot_id": snapshot_id,
            "latest_batch_id": manifest.get("latest_batch_id"),
            "release_prefix": (release_prefix),
            "pointer_key": (self.settings.pointer_key),
            "local_file_count": len(snapshot_files),
            "uploaded_file_count": len(uploaded_keys),
            "skipped_file_count": len(skipped_keys),
            "pointer_uploaded": (pointer_uploaded),
            "uploaded_keys": (uploaded_keys),
            "skipped_keys": (skipped_keys),
        }

    def _load_and_validate_snapshot(
        self,
    ) -> tuple[
        dict[str, Any],
        list[str],
    ]:
        input_directory = self.settings.input_directory

        if not input_directory.exists():
            raise S3SnapshotValidationError(
                f"Không tìm thấy snapshot directory: {input_directory}"
            )

        if not input_directory.is_dir():
            raise S3SnapshotValidationError(
                f"Snapshot input path không phải directory: {input_directory}"
            )

        manifest_path = input_directory / "manifest.json"

        if not manifest_path.is_file():
            raise S3SnapshotValidationError(
                "Không tìm thấy manifest.json trong snapshot directory."
            )

        try:
            with manifest_path.open(
                mode="r",
                encoding="utf-8",
            ) as file_handle:
                manifest = json.load(file_handle)

        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            raise S3SnapshotValidationError(
                f"Không đọc được manifest.json: {error}"
            ) from error

        if not isinstance(
            manifest,
            dict,
        ):
            raise S3SnapshotValidationError("manifest.json phải là một JSON object.")

        required_fields = {
            "schema_version",
            "snapshot_id",
            "generated_at",
            "latest_batch_id",
            "files",
        }

        missing_fields = sorted(required_fields - set(manifest))

        if missing_fields:
            raise S3SnapshotValidationError(
                "manifest.json thiếu field: " + ", ".join(missing_fields)
            )

        manifest_batch_id = str(manifest.get("latest_batch_id", "")).strip()
        if not manifest_batch_id:
            raise S3SnapshotValidationError("manifest.json có latest_batch_id rỗng.")

        if (
            self.expected_batch_id is not None
            and manifest_batch_id != self.expected_batch_id
        ):
            raise S3SnapshotValidationError(
                "manifest.json không khớp batch_id. "
                f"Expected={self.expected_batch_id}; "
                f"actual={manifest_batch_id}."
            )

        snapshot_id = manifest["snapshot_id"]

        if not isinstance(
            snapshot_id,
            str,
        ):
            raise S3SnapshotValidationError("snapshot_id phải là string.")

        snapshot_id = snapshot_id.strip()

        if not SAFE_SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id):
            raise S3SnapshotValidationError(
                "snapshot_id không an toàn để dùng trong S3 key."
            )

        manifest_files = manifest["files"]

        if not isinstance(
            manifest_files,
            list,
        ):
            raise S3SnapshotValidationError("Field files trong manifest phải là list.")

        normalized_files: list[str] = []
        seen_files: set[str] = set()

        for index, raw_path in enumerate(manifest_files):
            if not isinstance(
                raw_path,
                str,
            ):
                raise S3SnapshotValidationError(
                    f"Mỗi phần tử trong files phải là string; index={index}."
                )

            relative_path = raw_path.replace("\\", "/").strip("/")

            if not relative_path or "/../" in (f"/{relative_path}/"):
                raise S3SnapshotValidationError(
                    f"Đường dẫn snapshot không hợp lệ: {raw_path!r}."
                )

            if not relative_path.endswith(".json"):
                raise S3SnapshotValidationError(
                    f"Snapshot chỉ được chứa file JSON: {relative_path!r}."
                )

            if relative_path in seen_files:
                raise S3SnapshotValidationError(
                    f"Trùng file trong manifest: {relative_path!r}."
                )

            file_path = input_directory / Path(relative_path)

            resolved_file_path = file_path.resolve()

            try:
                resolved_file_path.relative_to(input_directory.resolve())

            except ValueError as error:
                raise S3SnapshotValidationError(
                    f"File nằm ngoài snapshot directory: {relative_path}"
                ) from error

            if not resolved_file_path.is_file():
                raise S3SnapshotValidationError(
                    f"File được khai báo trong manifest không tồn tại: {relative_path}"
                )

            seen_files.add(relative_path)

            normalized_files.append(relative_path)

        if "manifest.json" not in (seen_files):
            raise S3SnapshotValidationError("Field files phải chứa manifest.json.")

        actual_json_files = {
            file_path.relative_to(input_directory).as_posix()
            for file_path in (input_directory.rglob("*.json"))
        }

        if actual_json_files != (seen_files):
            unlisted_files = sorted(actual_json_files - seen_files)

            missing_files = sorted(seen_files - actual_json_files)

            details: list[str] = []

            if unlisted_files:
                details.append(
                    "file không có trong manifest: " + ", ".join(unlisted_files)
                )

            if missing_files:
                details.append("file bị thiếu: " + ", ".join(missing_files))

            raise S3SnapshotValidationError(
                "Snapshot tree không khớp manifest; " + "; ".join(details)
            )

        return (
            manifest,
            sorted(normalized_files),
        )

    def _remote_object_matches(
        self,
        object_key: str,
        expected_sha256: str,
    ) -> bool:
        try:
            response = self.client.head_object(
                Bucket=(self.settings.bucket_name),
                Key=object_key,
            )

        except ClientError as error:
            error_code = str(
                error.response.get(
                    "Error",
                    {},
                ).get(
                    "Code",
                    "",
                )
            )

            if error_code in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                return False

            raise

        metadata = response.get(
            "Metadata",
            {},
        )

        return metadata.get("sha256") == expected_sha256

    def _put_json_file(
        self,
        source_path: Path,
        object_key: str,
        snapshot_id: str,
        sha256_digest: str,
        cache_control: str,
    ) -> None:
        with source_path.open(mode="rb") as file_handle:
            self.client.put_object(
                Bucket=(self.settings.bucket_name),
                Key=object_key,
                Body=file_handle,
                ContentType=("application/json; charset=utf-8"),
                CacheControl=(cache_control),
                Metadata={
                    "snapshot-id": (snapshot_id),
                    "sha256": (sha256_digest),
                },
            )

    def _put_json_bytes(
        self,
        body: bytes,
        object_key: str,
        snapshot_id: str,
        sha256_digest: str,
        cache_control: str,
    ) -> None:
        self.client.put_object(
            Bucket=(self.settings.bucket_name),
            Key=object_key,
            Body=body,
            ContentType=("application/json; charset=utf-8"),
            CacheControl=(cache_control),
            Metadata={
                "snapshot-id": (snapshot_id),
                "sha256": (sha256_digest),
            },
        )


def _calculate_sha256(
    file_path: Path,
) -> str:
    digest = hashlib.sha256()

    with file_path.open(mode="rb") as file_handle:
        while True:
            chunk = file_handle.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def upload_public_snapshots_to_s3(
    settings: S3SnapshotUploadSettings | None = None,
    client: BaseClient | None = None,
    expected_batch_id: str | None = None,
) -> dict[str, Any]:
    resolved_settings = settings or S3SnapshotUploadSettings.from_environment()

    uploader = S3SnapshotUploader(
        settings=resolved_settings,
        client=client,
        expected_batch_id=expected_batch_id,
    )

    return uploader.upload()
