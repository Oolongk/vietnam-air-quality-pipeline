from __future__ import annotations

from minio.error import S3Error

from src.alerts.minio_alert_processor import (
    MinioAlertProcessingError,
    process_minio_quality_batch_alerts,
)
from src.operations.batch_context import (
    PipelineBatchContext,
    PipelineBatchContextError,
)
from src.quality.minio_quality_processor import (
    MinioDataQualityError,
    find_latest_loadable_quality_batch,
    load_loadable_quality_batch_for_context,
)
from src.utils.minio_client import (
    MinioConfigurationError,
    MinioOperationError,
    MinioSettings,
    get_minio_client,
)
from src.utils.minio_object_io import MinioObjectIOError


def main() -> None:
    try:
        batch_context = PipelineBatchContext.from_environment()
        minio_settings = MinioSettings.from_environment()
        minio_client = get_minio_client(minio_settings)

        if batch_context is None:
            quality_summary_object_name, quality_summary = (
                find_latest_loadable_quality_batch(
                    settings=minio_settings,
                    client=minio_client,
                )
            )
        else:
            quality_summary_object_name, quality_summary = (
                load_loadable_quality_batch_for_context(
                    batch_context,
                    settings=minio_settings,
                    client=minio_client,
                )
            )

        alert_summary = process_minio_quality_batch_alerts(
            quality_summary=quality_summary,
            quality_summary_object_name=quality_summary_object_name,
            settings=minio_settings,
            client=minio_client,
        )

        if batch_context is not None:
            batch_context.validate_summary(alert_summary, "Alert summary")

    except (
        MinioAlertProcessingError,
        MinioDataQualityError,
        PipelineBatchContextError,
        MinioConfigurationError,
        MinioOperationError,
        MinioObjectIOError,
        S3Error,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
    ) as error:
        print(f"Xử lý AQI và alert thất bại: {error}")
        raise SystemExit(1) from error

    execution_mode = "AIRFLOW_BATCH" if batch_context is not None else "LATEST_MANUAL"
    print("Xử lý AQI và alert hoàn tất.")
    print(f"Execution mode: {execution_mode}")
    print(f"Batch ID đã xử lý: {alert_summary['batch_id']}")
    print(f"Status: {alert_summary.get('status', 'UNKNOWN')}")
    print(f"Input records: {alert_summary.get('input_records', 0)}")
    print(f"Số file đã upload lên MinIO: {alert_summary['uploaded_object_count']}")
    print(
        "Alert summary: "
        f"{alert_summary['summary_bucket']}/{alert_summary['summary_object_name']}"
    )


if __name__ == "__main__":
    main()
