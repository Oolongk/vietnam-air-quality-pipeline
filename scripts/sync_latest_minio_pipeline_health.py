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
from src.operations.batch_context import (
    PipelineBatchContext,
    PipelineBatchContextError,
)
from src.utils.minio_client import (
    MinioConfigurationError,
    MinioOperationError,
)
from src.utils.minio_object_io import (
    MinioObjectIOError,
)


def main() -> None:
    batch_context = None

    try:
        batch_context = PipelineBatchContext.from_environment()
        result = sync_latest_minio_pipeline_health(batch_context=batch_context)

        if batch_context is not None:
            result_batch_id = str(result.get("batch_id", "")).strip()
            if result_batch_id != batch_context.batch_id:
                raise PipelineBatchContextError(
                    "Pipeline Health result không khớp batch_id. "
                    f"Expected={batch_context.batch_id}; "
                    f"actual={result_batch_id or 'EMPTY'}."
                )

    except (
        MinioPipelineLogSyncError,
        PipelineBatchContextError,
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

    execution_mode = "AIRFLOW_BATCH" if batch_context is not None else "LATEST_MANUAL"
    print(f"Execution mode: {execution_mode}")
    print(f"Status: {status}")

    print(f"Batch ID: {batch_id}")

    print(f"Pipeline logs upserted: {pipeline_logs_upserted}")

    print(f"Data Quality logs upserted: {data_quality_logs_upserted}")

    print(f"Stages: {stages_text}")


if __name__ == "__main__":
    main()
