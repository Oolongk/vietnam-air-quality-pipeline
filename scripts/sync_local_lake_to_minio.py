from __future__ import annotations

from pathlib import Path

from minio.error import S3Error

from src.load.minio_lake_sync import (
    MinioLakeSyncError,
    sync_local_lake_to_minio,
)
from src.utils.minio_client import (
    MinioConfigurationError,
    MinioOperationError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

LOCAL_LAKE_ROOT = PROJECT_ROOT / "data" / "local_lake"


def main() -> None:
    try:
        summary = sync_local_lake_to_minio(local_lake_root=(LOCAL_LAKE_ROOT))
    except (
        MinioConfigurationError,
        MinioOperationError,
        MinioLakeSyncError,
        S3Error,
    ) as error:
        print(f"Đồng bộ Local Data Lake lên MinIO thất bại: {error}")

        raise SystemExit(1) from error

    print("Đồng bộ Local Data Lake lên MinIO hoàn tất.")

    print(f"Status: {summary['status']}")

    print(f"Planned files: {summary['planned_files']}")

    print(f"Uploaded files: {summary['uploaded_files']}")

    print(f"Failed files: {summary['failed_files']}")

    print(f"Uploaded bytes: {summary['uploaded_bytes']}")

    print("Số file theo bucket:")

    for (
        bucket_name,
        file_count,
    ) in summary["bucket_counts"].items():
        print(f"- {bucket_name}: {file_count}")

    print(f"Thời gian đồng bộ: {summary['duration_seconds']:.2f} giây")

    print(f"Local summary: {summary['summary_path']}")

    print(
        f"MinIO summary: {summary['summary_bucket']}/{summary['summary_object_name']}"
    )


if __name__ == "__main__":
    main()
