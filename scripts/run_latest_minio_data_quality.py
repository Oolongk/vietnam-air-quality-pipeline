from __future__ import annotations

import sys

from minio.error import S3Error

from src.quality.minio_quality_processor import (
    MinioDataQualityError,
    find_latest_quality_candidate,
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

    try:
        (
            transform_summary_object_name,
            transform_summary,
        ) = find_latest_quality_candidate()

        quality_summary = (
            process_transformed_batch_on_minio(
                transform_summary=(
                    transform_summary
                ),
                transform_summary_object_name=(
                    transform_summary_object_name
                ),
            )
        )

    except (
        MinioDataQualityError,
        MinioConfigurationError,
        MinioOperationError,
        MinioObjectIOError,
        S3Error,
        ValueError,
        TypeError,
    ) as error:
        print(
            "Data Quality trực tiếp trên "
            f"MinIO thất bại: {error}"
        )

        raise SystemExit(1) from error

    print()

    print(
        "Pipeline status: "
        f"{quality_summary['status']}"
    )

    print(
        "Quality status: "
        f"{quality_summary['quality_status']}"
    )

    print(
        "Quality score: "
        f"{quality_summary['quality_score']}"
    )

    print(
        "Batch ID: "
        f"{quality_summary['batch_id']}"
    )

    print(
        "Input records: "
        f"{quality_summary['input_records']}"
    )

    print(
        "Expected records: "
        f"{quality_summary['expected_records']}"
    )

    print(
        "Valid records: "
        f"{quality_summary['valid_records']}"
    )

    print(
        "Bad records: "
        f"{quality_summary['bad_records']}"
    )

    print(
        "Valid percentage: "
        f"{quality_summary['valid_percentage']}%"
    )

    print(
        "Expected active points: "
        f"{quality_summary['expected_active_points']}"
    )

    print(
        "Actual active points: "
        f"{quality_summary['actual_active_points']}"
    )

    print(
        "Expected forecast hours: "
        f"{quality_summary['expected_forecast_hours']}"
    )

    print(
        "Checks passed: "
        f"{quality_summary['passed_checks']}"
    )

    print(
        "Checks warned: "
        f"{quality_summary['warning_checks']}"
    )

    print(
        "Checks failed: "
        f"{quality_summary['failed_checks']}"
    )

    print(
        "Clean object: "
        f"{quality_summary['clean_object_name']}"
    )

    print(
        "Bad records object: "
        f"{quality_summary['bad_records_object_name']}"
    )

    print(
        "Summary object: "
        f"{quality_summary['summary_object_name']}"
    )

    print(
        "Quality snapshot history: "
        f"{quality_summary['quality_snapshot_object_name']}"
    )

    print(
        "Latest quality snapshot: "
        f"{quality_summary['latest_quality_snapshot_object_name']}"
    )

    print()
    print(
        "Kết quả các rule không PASSED:"
    )

    non_passed_checks = [
        check
        for check in quality_summary[
            "checks"
        ]
        if check.get(
            "status"
        )
        != "PASSED"
    ]

    if not non_passed_checks:
        print(
            "- Tất cả rule đều PASSED."
        )
    else:
        for check in (
            non_passed_checks
        ):
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
