from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import pandas as pd
from minio import Minio
from minio.error import S3Error

from src.utils.minio_client import (
    MinioOperationError,
    MinioSettings,
    get_minio_client,
    normalize_object_name,
)


class MinioObjectIOError(RuntimeError):
    """Lỗi khi đọc hoặc ghi object trên MinIO."""


def serialize_json(
    data: Any,
) -> bytes:
    try:
        json_text = json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise MinioObjectIOError(
            "Không thể chuyển dữ liệu thành JSON."
        ) from error

    return json_text.encode("utf-8")


def deserialize_json(
    payload: bytes,
) -> Any:
    if not isinstance(payload, bytes):
        raise TypeError(
            "JSON payload phải có kiểu bytes."
        )

    try:
        json_text = payload.decode("utf-8")

        return json.loads(
            json_text
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise MinioObjectIOError(
            "Object không chứa JSON UTF-8 hợp lệ."
        ) from error


def serialize_dataframe_parquet(
    dataframe: pd.DataFrame,
) -> bytes:
    if not isinstance(
        dataframe,
        pd.DataFrame,
    ):
        raise TypeError(
            "dataframe phải là Pandas DataFrame."
        )

    buffer = BytesIO()

    try:
        dataframe.to_parquet(
            buffer,
            engine="pyarrow",
            compression="snappy",
            index=False,
        )
    except Exception as error:
        raise MinioObjectIOError(
            "Không thể chuyển DataFrame "
            "thành Parquet."
        ) from error

    return buffer.getvalue()


def deserialize_dataframe_parquet(
    payload: bytes,
) -> pd.DataFrame:
    if not isinstance(payload, bytes):
        raise TypeError(
            "Parquet payload phải có kiểu bytes."
        )

    buffer = BytesIO(payload)

    try:
        dataframe = pd.read_parquet(
            buffer,
            engine="pyarrow",
        )
    except Exception as error:
        raise MinioObjectIOError(
            "Object không chứa Parquet hợp lệ."
        ) from error

    return dataframe


def _resolve_client(
    settings: MinioSettings | None,
    client: Minio | None,
) -> tuple[MinioSettings, Minio]:
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

    return (
        resolved_settings,
        resolved_client,
    )


def put_bytes_object(
    bucket_name: str,
    object_name: str,
    payload: bytes,
    content_type: str = (
        "application/octet-stream"
    ),
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, bytes):
        raise TypeError(
            "payload phải có kiểu bytes."
        )

    if not payload:
        raise MinioObjectIOError(
            "Không upload object rỗng."
        )

    (
        _,
        resolved_client,
    ) = _resolve_client(
        settings=settings,
        client=client,
    )

    normalized_object_name = (
        normalize_object_name(
            object_name
        )
    )

    payload_stream = BytesIO(
        payload
    )

    try:
        result = resolved_client.put_object(
            bucket_name=bucket_name,
            object_name=(
                normalized_object_name
            ),
            data=payload_stream,
            length=len(payload),
            content_type=content_type,
        )
    except S3Error as error:
        raise MinioObjectIOError(
            "Không thể upload object: "
            f"{bucket_name}/"
            f"{normalized_object_name}. "
            f"MinIO error: {error}"
        ) from error
    except OSError as error:
        raise MinioObjectIOError(
            "Lỗi I/O khi upload object: "
            f"{bucket_name}/"
            f"{normalized_object_name}"
        ) from error
    finally:
        payload_stream.close()

    return {
        "bucket_name": (
            result.bucket_name
        ),
        "object_name": (
            result.object_name
        ),
        "etag": result.etag,
        "version_id": (
            result.version_id
        ),
        "size_bytes": len(payload),
        "content_type": content_type,
    }


def get_bytes_object(
    bucket_name: str,
    object_name: str,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> bytes:
    (
        _,
        resolved_client,
    ) = _resolve_client(
        settings=settings,
        client=client,
    )

    normalized_object_name = (
        normalize_object_name(
            object_name
        )
    )

    response = None

    try:
        response = (
            resolved_client.get_object(
                bucket_name=bucket_name,
                object_name=(
                    normalized_object_name
                ),
            )
        )

        return response.read()

    except S3Error as error:
        raise MinioObjectIOError(
            "Không thể đọc object: "
            f"{bucket_name}/"
            f"{normalized_object_name}. "
            f"MinIO error: {error}"
        ) from error
    except OSError as error:
        raise MinioObjectIOError(
            "Lỗi I/O khi đọc object: "
            f"{bucket_name}/"
            f"{normalized_object_name}"
        ) from error
    finally:
        if response is not None:
            response.close()
            response.release_conn()


def put_json_object(
    bucket_name: str,
    object_name: str,
    data: Any,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> dict[str, Any]:
    payload = serialize_json(
        data
    )

    return put_bytes_object(
        bucket_name=bucket_name,
        object_name=object_name,
        payload=payload,
        content_type=(
            "application/json; charset=utf-8"
        ),
        settings=settings,
        client=client,
    )


def get_json_object(
    bucket_name: str,
    object_name: str,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> Any:
    payload = get_bytes_object(
        bucket_name=bucket_name,
        object_name=object_name,
        settings=settings,
        client=client,
    )

    return deserialize_json(
        payload
    )


def put_parquet_object(
    bucket_name: str,
    object_name: str,
    dataframe: pd.DataFrame,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> dict[str, Any]:
    payload = (
        serialize_dataframe_parquet(
            dataframe
        )
    )

    return put_bytes_object(
        bucket_name=bucket_name,
        object_name=object_name,
        payload=payload,
        content_type=(
            "application/vnd.apache.parquet"
        ),
        settings=settings,
        client=client,
    )


def get_parquet_object(
    bucket_name: str,
    object_name: str,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> pd.DataFrame:
    payload = get_bytes_object(
        bucket_name=bucket_name,
        object_name=object_name,
        settings=settings,
        client=client,
    )

    return deserialize_dataframe_parquet(
        payload
    )


def object_exists(
    bucket_name: str,
    object_name: str,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> bool:
    (
        _,
        resolved_client,
    ) = _resolve_client(
        settings=settings,
        client=client,
    )

    normalized_object_name = (
        normalize_object_name(
            object_name
        )
    )

    try:
        resolved_client.stat_object(
            bucket_name=bucket_name,
            object_name=(
                normalized_object_name
            ),
        )

        return True

    except S3Error as error:
        if error.code in {
            "NoSuchKey",
            "NoSuchObject",
            "NoSuchBucket",
        }:
            return False

        raise MinioObjectIOError(
            "Không thể kiểm tra object: "
            f"{bucket_name}/"
            f"{normalized_object_name}. "
            f"MinIO error: {error}"
        ) from error


def delete_object(
    bucket_name: str,
    object_name: str,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> None:
    (
        _,
        resolved_client,
    ) = _resolve_client(
        settings=settings,
        client=client,
    )

    normalized_object_name = (
        normalize_object_name(
            object_name
        )
    )

    try:
        resolved_client.remove_object(
            bucket_name=bucket_name,
            object_name=(
                normalized_object_name
            ),
        )
    except S3Error as error:
        raise MinioObjectIOError(
            "Không thể xóa object: "
            f"{bucket_name}/"
            f"{normalized_object_name}. "
            f"MinIO error: {error}"
        ) from error


def list_object_names(
    bucket_name: str,
    prefix: str = "",
    recursive: bool = True,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> list[str]:
    (
        _,
        resolved_client,
    ) = _resolve_client(
        settings=settings,
        client=client,
    )

    normalized_prefix = (
        prefix
        .replace("\\", "/")
        .strip("/")
    )

    try:
        objects = (
            resolved_client.list_objects(
                bucket_name=bucket_name,
                prefix=normalized_prefix,
                recursive=recursive,
            )
        )

        return [
            object_item.object_name
            for object_item in objects
        ]
    except S3Error as error:
        raise MinioObjectIOError(
            "Không thể liệt kê object trong "
            f"bucket {bucket_name}: {error}"
        ) from error