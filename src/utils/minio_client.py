from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error


BUCKET_NAME_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$"
)


class MinioConfigurationError(ValueError):
    """Cấu hình kết nối MinIO không hợp lệ."""


class MinioOperationError(RuntimeError):
    """MinIO từ chối hoặc không thể hoàn thành thao tác."""


@dataclass(frozen=True)
class MinioSettings:
    endpoint: str
    access_key: str
    secret_key: str
    secure: bool
    raw_bucket: str
    clean_bucket: str
    mart_bucket: str

    @classmethod
    def from_environment(
        cls,
    ) -> "MinioSettings":
        load_dotenv()

        endpoint = _get_required_environment(
            "MINIO_ENDPOINT"
        )

        if endpoint.startswith(
            ("http://", "https://")
        ):
            raise MinioConfigurationError(
                "MINIO_ENDPOINT không được chứa "
                "http:// hoặc https://. "
                "Ví dụ đúng: localhost:9000"
            )

        if "/" in endpoint:
            raise MinioConfigurationError(
                "MINIO_ENDPOINT không được chứa path."
            )

        settings = cls(
            endpoint=endpoint,
            access_key=_get_required_environment(
                "MINIO_ACCESS_KEY"
            ),
            secret_key=_get_required_environment(
                "MINIO_SECRET_KEY"
            ),
            secure=_get_boolean_environment(
                "MINIO_SECURE",
                default=False,
            ),
            raw_bucket=_get_required_environment(
                "MINIO_RAW_BUCKET"
            ),
            clean_bucket=_get_required_environment(
                "MINIO_CLEAN_BUCKET"
            ),
            mart_bucket=_get_required_environment(
                "MINIO_MART_BUCKET"
            ),
        )

        for bucket_name in settings.bucket_names:
            _validate_bucket_name(
                bucket_name
            )

        return settings

    @property
    def bucket_names(
        self,
    ) -> tuple[str, str, str]:
        return (
            self.raw_bucket,
            self.clean_bucket,
            self.mart_bucket,
        )


def _get_required_environment(
    name: str,
) -> str:
    value = os.getenv(name)

    if value is None:
        raise MinioConfigurationError(
            f"Thiếu biến môi trường: {name}"
        )

    cleaned_value = value.strip()

    if not cleaned_value:
        raise MinioConfigurationError(
            f"Biến {name} không được rỗng."
        )

    return cleaned_value


def _get_boolean_environment(
    name: str,
    default: bool,
) -> bool:
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    normalized_value = (
        raw_value.strip().lower()
    )

    true_values = {
        "true",
        "1",
        "yes",
        "y",
    }

    false_values = {
        "false",
        "0",
        "no",
        "n",
    }

    if normalized_value in true_values:
        return True

    if normalized_value in false_values:
        return False

    raise MinioConfigurationError(
        f"{name} phải là true hoặc false."
    )


def _validate_bucket_name(
    bucket_name: str,
) -> None:
    if not BUCKET_NAME_PATTERN.fullmatch(
        bucket_name
    ):
        raise MinioConfigurationError(
            "Bucket name không hợp lệ: "
            f"{bucket_name!r}. "
            "Chỉ dùng chữ thường, số, dấu chấm "
            "và dấu gạch ngang; độ dài 3-63."
        )

    if (
        ".." in bucket_name
        or ".-" in bucket_name
        or "-." in bucket_name
    ):
        raise MinioConfigurationError(
            "Bucket name có chuỗi dấu không hợp lệ: "
            f"{bucket_name!r}"
        )


def get_minio_client(
    settings: MinioSettings | None = None,
) -> Minio:
    resolved_settings = (
        settings
        or MinioSettings.from_environment()
    )

    return Minio(
        endpoint=resolved_settings.endpoint,
        access_key=resolved_settings.access_key,
        secret_key=resolved_settings.secret_key,
        secure=resolved_settings.secure,
    )


def ensure_buckets(
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> dict[str, list[str]]:
    resolved_settings = (
        settings
        or MinioSettings.from_environment()
    )

    resolved_client = (
        client
        or get_minio_client(
            resolved_settings
        )
    )

    created_buckets: list[str] = []
    existing_buckets: list[str] = []

    try:
        for bucket_name in (
            resolved_settings.bucket_names
        ):
            if resolved_client.bucket_exists(
                bucket_name
            ):
                existing_buckets.append(
                    bucket_name
                )
                continue

            resolved_client.make_bucket(
                bucket_name
            )

            created_buckets.append(
                bucket_name
            )

    except S3Error as error:
        raise MinioOperationError(
            "Không thể kiểm tra hoặc tạo "
            f"MinIO buckets: {error}"
        ) from error

    return {
        "created_buckets": created_buckets,
        "existing_buckets": existing_buckets,
    }


def normalize_object_name(
    object_name: str,
) -> str:
    normalized_name = (
        object_name
        .replace("\\", "/")
        .strip("/")
    )

    if not normalized_name:
        raise MinioOperationError(
            "Object name không được rỗng."
        )

    if "/../" in f"/{normalized_name}/":
        raise MinioOperationError(
            "Object name không được chứa '..'."
        )

    return normalized_name


def upload_file(
    bucket_name: str,
    object_name: str,
    file_path: Path,
    content_type: str = (
        "application/octet-stream"
    ),
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> dict[str, Any]:
    resolved_settings = (
        settings
        or MinioSettings.from_environment()
    )

    resolved_client = (
        client
        or get_minio_client(
            resolved_settings
        )
    )

    resolved_file_path = (
        file_path.resolve()
    )

    if not resolved_file_path.exists():
        raise MinioOperationError(
            f"Không tìm thấy file: "
            f"{resolved_file_path}"
        )

    if not resolved_file_path.is_file():
        raise MinioOperationError(
            f"Đường dẫn không phải file: "
            f"{resolved_file_path}"
        )

    normalized_object_name = (
        normalize_object_name(
            object_name
        )
    )

    try:
        result = resolved_client.fput_object(
            bucket_name=bucket_name,
            object_name=normalized_object_name,
            file_path=str(
                resolved_file_path
            ),
            content_type=content_type,
        )
    except (
        S3Error,
        OSError,
    ) as error:
        raise MinioOperationError(
            "Không thể upload object "
            f"{bucket_name}/"
            f"{normalized_object_name}: {error}"
        ) from error

    return {
        "bucket_name": bucket_name,
        "object_name": (
            normalized_object_name
        ),
        "etag": result.etag,
        "version_id": result.version_id,
        "size_bytes": (
            resolved_file_path.stat().st_size
        ),
    }


def list_bucket_objects(
    bucket_name: str,
    recursive: bool = True,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> list[dict[str, Any]]:
    resolved_settings = (
        settings
        or MinioSettings.from_environment()
    )

    resolved_client = (
        client
        or get_minio_client(
            resolved_settings
        )
    )

    try:
        objects = (
            resolved_client.list_objects(
                bucket_name=bucket_name,
                recursive=recursive,
            )
        )

        return [
            {
                "object_name": (
                    object_item.object_name
                ),
                "size_bytes": (
                    object_item.size
                ),
                "last_modified": (
                    object_item.last_modified
                ),
                "etag": object_item.etag,
            }
            for object_item in objects
        ]
    except S3Error as error:
        raise MinioOperationError(
            "Không thể liệt kê objects trong "
            f"bucket {bucket_name}: {error}"
        ) from error


def check_minio_connection(
) -> dict[str, Any]:
    settings = (
        MinioSettings.from_environment()
    )

    client = get_minio_client(
        settings
    )

    try:
        buckets = client.list_buckets()
    except S3Error as error:
        raise MinioOperationError(
            "Không thể kết nối MinIO: "
            f"{error}"
        ) from error

    return {
        "endpoint": settings.endpoint,
        "secure": settings.secure,
        "configured_buckets": list(
            settings.bucket_names
        ),
        "existing_buckets": [
            bucket.name
            for bucket in buckets
        ],
    }