from __future__ import annotations

from minio.error import S3Error

from src.transform.minio_batch_transformer import (
    MinioBatchTransformError,
    find_latest_transformable_raw_batch,
    transform_raw_batch_to_minio,
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
            raw_summary_object_name,
            raw_summary,
        ) = find_latest_transformable_raw_batch()

        transform_summary = transform_raw_batch_to_minio(
            raw_summary=raw_summary,
            raw_summary_object_name=(raw_summary_object_name),
        )

    except (
        MinioBatchTransformError,
        MinioConfigurationError,
        MinioOperationError,
        MinioObjectIOError,
        S3Error,
        ValueError,
        TypeError,
    ) as error:
        print(f"Transform trực tiếp trên MinIO thất bại: {error}")

        raise SystemExit(1) from error

    print("Transform trực tiếp trên MinIO hoàn tất.")

    print(f"Status: {transform_summary['status']}")

    print(f"Batch ID: {transform_summary['batch_id']}")

    print(f"Raw status: {transform_summary['raw_status']}")

    print(f"Input objects: {transform_summary['input_objects']}")

    print(f"Successful objects: {transform_summary['successful_objects']}")

    print(f"Failed objects: {transform_summary['failed_objects']}")

    print(f"Records transformed: {transform_summary['records_transformed']}")

    print(f"Output bucket: {transform_summary['transformed_bucket']}")

    print(f"Parquet object: {transform_summary['transformed_object_name']}")

    print(f"Parquet size: {transform_summary['transformed_size_bytes']} bytes")

    print(f"Summary object: {transform_summary['summary_object_name']}")

    if transform_summary["failures"]:
        print()
        print("Các Raw object bị lỗi:")

        for failure in transform_summary["failures"]:
            print(
                "- "
                f"{failure.get('point_id', 'UNKNOWN')}: "
                f"{failure['error_type']} - "
                f"{failure['error_message']}"
            )


if __name__ == "__main__":
    main()
