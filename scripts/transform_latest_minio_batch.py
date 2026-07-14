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
        ) = (
            find_latest_transformable_raw_batch()
        )

        transform_summary = (
            transform_raw_batch_to_minio(
                raw_summary=raw_summary,
                raw_summary_object_name=(
                    raw_summary_object_name
                ),
            )
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
        print(
            "Transform trực tiếp trên MinIO "
            f"thất bại: {error}"
        )

        raise SystemExit(1) from error

    print(
        "Transform trực tiếp trên MinIO "
        "hoàn tất."
    )

    print(
        "Status: "
        f"{transform_summary['status']}"
    )

    print(
        "Batch ID: "
        f"{transform_summary['batch_id']}"
    )

    print(
        "Raw status: "
        f"{transform_summary['raw_status']}"
    )

    print(
        "Input objects: "
        f"{transform_summary['input_objects']}"
    )

    print(
        "Successful objects: "
        f"{transform_summary['successful_objects']}"
    )

    print(
        "Failed objects: "
        f"{transform_summary['failed_objects']}"
    )

    print(
        "Records transformed: "
        f"{transform_summary['records_transformed']}"
    )

    print(
        "Output bucket: "
        f"{transform_summary['transformed_bucket']}"
    )

    print(
        "Parquet object: "
        f"{transform_summary['transformed_object_name']}"
    )

    print(
        "Parquet size: "
        f"{transform_summary['transformed_size_bytes']} bytes"
    )

    print(
        "Summary object: "
        f"{transform_summary['summary_object_name']}"
    )

    if transform_summary["failures"]:
        print()
        print("Các Raw object bị lỗi:")

        for failure in (
            transform_summary["failures"]
        ):
            print(
                "- "
                f"{failure.get('point_id', 'UNKNOWN')}: "
                f"{failure['error_type']} - "
                f"{failure['error_message']}"
            )


if __name__ == "__main__":
    main()