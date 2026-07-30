from __future__ import annotations

from minio.error import S3Error
import psycopg

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
        result = sync_latest_minio_pipeline_health()

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
        print(f"Đồng bộ Pipeline Health thất bại: {error}")

        raise SystemExit(1) from error

    status = result.get(
        "status",
        "UNKNOWN",
    )

    batch_id = result.get(
        "batch_id",
        "UNKNOWN",
    )

    pipeline_logs_upserted = result.get(
        "pipeline_logs_upserted",
        0,
    )

    data_quality_logs_upserted = result.get(
        "data_quality_logs_upserted",
        0,
    )

    stages = result.get(
        "stages",
        [],
    )

    if isinstance(
        stages,
        list,
    ):
        stages_text = ", ".join(str(stage) for stage in stages)
    else:
        stages_text = str(stages)

    print("Đồng bộ Pipeline Health hoàn tất.")

    print(f"Status: {status}")

    print(f"Batch ID: {batch_id}")

    print(f"Pipeline logs upserted: {pipeline_logs_upserted}")

    print(f"Data Quality logs upserted: {data_quality_logs_upserted}")

    print(f"Stages: {stages_text}")


if __name__ == "__main__":
    main()
