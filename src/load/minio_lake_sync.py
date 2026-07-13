from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from minio import Minio

from src.utils.minio_client import (
    MinioSettings,
    ensure_buckets,
    get_minio_client,
    upload_file,
)


@dataclass(frozen=True)
class MinioSyncEntry:
    local_path: Path
    bucket_name: str
    object_name: str
    size_bytes: int


SYNC_LAYOUT: tuple[
    tuple[str, str, str],
    ...,
] = (
    (
        "raw",
        "raw_bucket",
        "",
    ),
    (
        "transformed",
        "clean_bucket",
        "transformed",
    ),
    (
        "quality",
        "clean_bucket",
        "quality",
    ),
    (
        "clean",
        "clean_bucket",
        "clean",
    ),
    (
        "load",
        "mart_bucket",
        "load",
    ),
    (
        "alerts",
        "mart_bucket",
        "alerts",
    ),
    (
        "monitoring",
        "mart_bucket",
        "monitoring",
    ),
)


class MinioLakeSyncError(RuntimeError):
    """Lỗi khi đồng bộ Local Data Lake lên MinIO."""


def _join_object_name(
    prefix: str,
    relative_path: str,
) -> str:
    normalized_relative_path = (
        relative_path
        .replace("\\", "/")
        .strip("/")
    )

    normalized_prefix = (
        prefix
        .replace("\\", "/")
        .strip("/")
    )

    if not normalized_prefix:
        return normalized_relative_path

    return (
        f"{normalized_prefix}/"
        f"{normalized_relative_path}"
    )


def build_sync_plan(
    local_lake_root: Path,
    settings: MinioSettings,
) -> list[MinioSyncEntry]:
    resolved_root = (
        local_lake_root.resolve()
    )

    if not resolved_root.exists():
        raise MinioLakeSyncError(
            "Local Data Lake chưa tồn tại: "
            f"{resolved_root}"
        )

    if not resolved_root.is_dir():
        raise MinioLakeSyncError(
            "Local Data Lake root không phải "
            f"thư mục: {resolved_root}"
        )

    sync_entries: list[
        MinioSyncEntry
    ] = []

    for (
        local_zone,
        bucket_attribute,
        object_prefix,
    ) in SYNC_LAYOUT:
        zone_root = (
            resolved_root
            / local_zone
        )

        if not zone_root.exists():
            continue

        bucket_name = getattr(
            settings,
            bucket_attribute,
        )

        for file_path in sorted(
            zone_root.rglob("*")
        ):
            if not file_path.is_file():
                continue

            if file_path.name.endswith(
                ".tmp"
            ):
                continue

            relative_path = (
                file_path
                .relative_to(zone_root)
                .as_posix()
            )

            object_name = (
                _join_object_name(
                    prefix=object_prefix,
                    relative_path=(
                        relative_path
                    ),
                )
            )

            sync_entries.append(
                MinioSyncEntry(
                    local_path=(
                        file_path.resolve()
                    ),
                    bucket_name=(
                        bucket_name
                    ),
                    object_name=(
                        object_name
                    ),
                    size_bytes=(
                        file_path.stat().st_size
                    ),
                )
            )

    return sync_entries


def _guess_content_type(
    file_path: Path,
) -> str:
    guessed_type, _ = (
        mimetypes.guess_type(
            file_path.name
        )
    )

    if guessed_type is not None:
        return guessed_type

    if file_path.suffix.lower() == ".parquet":
        return "application/vnd.apache.parquet"

    return "application/octet-stream"


def _write_json_atomically(
    output_path: Path,
    data: dict[str, Any],
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = output_path.with_name(
        output_path.name + ".tmp"
    )

    try:
        with temporary_path.open(
            mode="w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                data,
                output_file,
                ensure_ascii=False,
                indent=2,
            )

        temporary_path.replace(
            output_path
        )
    except OSError as error:
        raise MinioLakeSyncError(
            "Không thể ghi MinIO sync summary: "
            f"{output_path}"
        ) from error


def sync_local_lake_to_minio(
    local_lake_root: Path,
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

    ensure_buckets(
        settings=resolved_settings,
        client=resolved_client,
    )

    sync_plan = build_sync_plan(
        local_lake_root=local_lake_root,
        settings=resolved_settings,
    )

    started_at = datetime.now(
        timezone.utc
    )

    uploaded_files = 0
    uploaded_bytes = 0

    bucket_counts = {
        resolved_settings.raw_bucket: 0,
        resolved_settings.clean_bucket: 0,
        resolved_settings.mart_bucket: 0,
    }

    failures: list[dict[str, str]] = []

    for entry in sync_plan:
        try:
            upload_file(
                bucket_name=(
                    entry.bucket_name
                ),
                object_name=(
                    entry.object_name
                ),
                file_path=(
                    entry.local_path
                ),
                content_type=(
                    _guess_content_type(
                        entry.local_path
                    )
                ),
                settings=resolved_settings,
                client=resolved_client,
            )
        except Exception as error:
            failures.append(
                {
                    "local_path": str(
                        entry.local_path
                    ),
                    "bucket_name": (
                        entry.bucket_name
                    ),
                    "object_name": (
                        entry.object_name
                    ),
                    "error": str(error),
                }
            )

            continue

        uploaded_files += 1
        uploaded_bytes += (
            entry.size_bytes
        )

        bucket_counts[
            entry.bucket_name
        ] += 1

    finished_at = datetime.now(
        timezone.utc
    )

    if not sync_plan:
        status = "SUCCESS"
    elif not failures:
        status = "SUCCESS"
    elif uploaded_files > 0:
        status = "PARTIAL_SUCCESS"
    else:
        status = "FAILED"

    local_time = finished_at.astimezone(
        ZoneInfo(
            "Asia/Ho_Chi_Minh"
        )
    )

    run_id = started_at.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    summary_directory = (
        local_lake_root.resolve()
        / "monitoring"
        / "minio_sync"
        / f"date={local_time:%Y-%m-%d}"
        / f"hour={local_time:%H}"
        / f"run_id={run_id}"
    )

    summary_path = (
        summary_directory
        / "minio_sync_summary.json"
    )

    summary_object_name = (
        "monitoring/minio_sync/"
        f"date={local_time:%Y-%m-%d}/"
        f"hour={local_time:%H}/"
        f"run_id={run_id}/"
        "minio_sync_summary.json"
    )

    summary = {
        "pipeline_name": (
            "local_data_lake_to_minio_sync"
        ),
        "status": status,
        "run_id": run_id,
        "started_at": (
            started_at.isoformat()
        ),
        "finished_at": (
            finished_at.isoformat()
        ),
        "duration_seconds": (
            finished_at - started_at
        ).total_seconds(),
        "planned_files": len(
            sync_plan
        ),
        "uploaded_files": (
            uploaded_files
        ),
        "failed_files": len(
            failures
        ),
        "uploaded_bytes": (
            uploaded_bytes
        ),
        "bucket_counts": (
            bucket_counts
        ),
        "failures": failures,
        "summary_path": str(
            summary_path
        ),
        "summary_bucket": (
            resolved_settings.mart_bucket
        ),
        "summary_object_name": (
            summary_object_name
        ),
    }

    _write_json_atomically(
        output_path=summary_path,
        data=summary,
    )

    try:
        upload_file(
            bucket_name=(
                resolved_settings.mart_bucket
            ),
            object_name=(
                summary_object_name
            ),
            file_path=summary_path,
            content_type=(
                "application/json"
            ),
            settings=resolved_settings,
            client=resolved_client,
        )
    except Exception as error:
        raise MinioLakeSyncError(
            "Dữ liệu đã được đồng bộ nhưng "
            "không thể upload sync summary: "
            f"{error}"
        ) from error

    return summary