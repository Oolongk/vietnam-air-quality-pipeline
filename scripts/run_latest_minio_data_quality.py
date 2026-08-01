from __future__ import annotations

import sys

from minio.error import S3Error

from src.operations.batch_context import (
    PipelineBatchContext,
    PipelineBatchContextError,
)
from src.quality.minio_quality_processor import (
    MinioDataQualityError,
    find_latest_quality_candidate,
    load_quality_candidate_for_context,
    process_transformed_batch_on_minio,
)
from src.utils.minio_client import (
    MinioConfigurationError,
    MinioOperationError,
)
from src.utils.minio_object_io import (
    MinioObjectIOError,
)


def configure_console_encoding() -> None:
    if hasattr(
        sys.stdout,
        "reconfigure",
    ):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    if hasattr(
        sys.stderr,
        "reconfigure",
    ):
        sys.stderr.reconfigure(
            encoding="utf-8",
            errors="replace",
        )


def main() -> None:
    configure_console_encoding()

    batch_context = None

    try:
        batch_context = PipelineBatchContext.from_environment()

        if batch_context is None:
            (
                transform_summary_object_name,
                transform_summary,
            ) = find_latest_quality_candidate()
        else:
            (
                transform_summary_object_name,
                transform_summary,
            ) = load_quality_candidate_for_context(batch_context)

        quality_summary = process_transformed_batch_on_minio(
            transform_summary=transform_summary,
            transform_summary_object_name=transform_summary_object_name,
        )

        if batch_context is not None:
            batch_context.validate_summary(quality_summary, "Data Quality summary")

    except (
        MinioDataQualityError,
        PipelineBatchContextError,
        MinioConfigurationError,
        MinioOperationError,
        MinioObjectIOError,
        S3Error,
        ValueError,
        TypeError,
    ) as error:
        print(f"Data Quality trực tiếp trên MinIO thất bại: {error}")

        raise SystemExit(1) from error

    print()

    execution_mode = "AIRFLOW_BATCH" if batch_context is not None else "LATEST_MANUAL"
    print(f"Execution mode: {execution_mode}")
    print(f"Pipeline status: {quality_summary['status']}")

    print(f"Quality status: {quality_summary['quality_status']}")

    print(f"Quality score: {quality_summary['quality_score']}")

    print(f"Batch ID: {quality_summary['batch_id']}")

    print(f"Input records: {quality_summary['input_records']}")

    print(f"Expected records: {quality_summary['expected_records']}")

    print(f"Valid records: {quality_summary['valid_records']}")

    print(f"Bad records: {quality_summary['bad_records']}")

    print(f"Valid percentage: {quality_summary['valid_percentage']}%")

    print(f"Expected active points: {quality_summary['expected_active_points']}")

    print(f"Actual active points: {quality_summary['actual_active_points']}")

    print(f"Expected forecast hours: {quality_summary['expected_forecast_hours']}")

    print(f"Checks passed: {quality_summary['passed_checks']}")

    print(f"Checks warned: {quality_summary['warning_checks']}")

    print(f"Checks failed: {quality_summary['failed_checks']}")

    print(f"Clean object: {quality_summary['clean_object_name']}")

    print(f"Bad records object: {quality_summary['bad_records_object_name']}")

    print(f"Summary object: {quality_summary['summary_object_name']}")

    print(
        f"Quality snapshot history: {quality_summary['quality_snapshot_object_name']}"
    )

    print(
        "Latest quality snapshot: "
        f"{quality_summary['latest_quality_snapshot_object_name']}"
    )

    print()
    print("Kết quả các rule không PASSED:")

    non_passed_checks = [
        check for check in quality_summary["checks"] if check.get("status") != "PASSED"
    ]

    if not non_passed_checks:
        print("- Tất cả rule đều PASSED.")
    else:
        for check in non_passed_checks:
            print(
                "- "
                f"{check['check_name']}: "
                f"{check['status']} "
                f"(scope="
                f"{check.get('check_scope')}, "
                f"bad="
                f"{check['bad_records_count']})"
            )


if __name__ == "__main__":
    main()
