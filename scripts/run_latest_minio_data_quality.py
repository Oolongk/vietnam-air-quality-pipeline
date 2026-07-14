from __future__ import annotations

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


def main() -> None:
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

    print(
        "Data Quality trực tiếp trên "
        "MinIO hoàn tất."
    )

    print(
        "Status: "
        f"{quality_summary['status']}"
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
        "Clean bucket: "
        f"{quality_summary['clean_bucket']}"
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

    print()
    print("Kết quả từng Data Quality rule:")

    for check in quality_summary[
        "checks"
    ]:
        print(
            "- "
            f"{check['check_name']}: "
            f"{check['status']} "
            f"(bad records: "
            f"{check['bad_records_count']})"
        )


if __name__ == "__main__":
    main()