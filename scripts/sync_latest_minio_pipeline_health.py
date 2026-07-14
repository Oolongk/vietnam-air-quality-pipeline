from __future__ import annotations

import psycopg
from minio.error import S3Error

from src.load.minio_pipeline_log_sync import (
    MinioPipelineLogSyncError,
    sync_latest_minio_pipeline_health,
)
from src.load.minio_timescaledb_loader import (
    MinioTimescaleDBLoadError,
)
from src.utils.minio_client import (
    MinioConfigurationError,
    MinioOperationError,
)
from src.utils.minio_object_io import (
    MinioObjectIOError,
)


def main() -> None:
    try:
        result = (
            sync_latest_minio_pipeline_health()
        )

    except (
        MinioPipelineLogSyncError,
        MinioTimescaleDBLoadError,
        MinioConfigurationError,
        MinioOperationError,
        MinioObjectIOError,
        S3Error,
        psycopg.Error,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
    ) as error:
        print(
            "Đồng bộ Pipeline Health "
            f"thất bại: {error}"
        )

        raise SystemExit(1) from error

    print(
        "Đồng bộ Pipeline Health "
        "hoàn tất."
    )

    print(
        "Status: "
        f"{result['status']}"
    )

    print(
        "Batch ID: "
        f"{result['batch_id']}"
    )

    print(
        "Pipeline logs upserted: "
        f"{result[
            'pipeline_logs_upserted'
        ]}"
    )

    print(
        "Data Quality logs upserted: "
        f"{result[
            'data_quality_logs_upserted'
        ]}"
    )

    print(
        "Stages: "
        + ", ".join(
            result["stages"]
        )
    )


if __name__ == "__main__":
    main()