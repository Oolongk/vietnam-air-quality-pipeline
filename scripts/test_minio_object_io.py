from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from minio.error import S3Error

from src.utils.minio_client import (
    MinioConfigurationError,
    MinioOperationError,
    MinioSettings,
    ensure_buckets,
    get_minio_client,
)
from src.utils.minio_object_io import (
    MinioObjectIOError,
    get_json_object,
    get_parquet_object,
    list_object_names,
    object_exists,
    put_json_object,
    put_parquet_object,
)


JSON_OBJECT_NAME = (
    "_system_tests/"
    "object_io/"
    "sample.json"
)

PARQUET_OBJECT_NAME = (
    "_system_tests/"
    "object_io/"
    "sample.parquet"
)


def main() -> None:
    try:
        settings = (
            MinioSettings.from_environment()
        )

        client = get_minio_client(
            settings
        )

        ensure_buckets(
            settings=settings,
            client=client,
        )

        json_data = {
            "test_name": (
                "minio_json_round_trip"
            ),
            "location_id": "HN",
            "point_id": "HN_CENTER",
            "message": (
                "Kiểm tra dữ liệu tiếng Việt"
            ),
            "created_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }

        json_upload_result = (
            put_json_object(
                bucket_name=(
                    settings.raw_bucket
                ),
                object_name=(
                    JSON_OBJECT_NAME
                ),
                data=json_data,
                settings=settings,
                client=client,
            )
        )

        downloaded_json = (
            get_json_object(
                bucket_name=(
                    settings.raw_bucket
                ),
                object_name=(
                    JSON_OBJECT_NAME
                ),
                settings=settings,
                client=client,
            )
        )

        if downloaded_json != json_data:
            raise RuntimeError(
                "JSON tải về không giống "
                "JSON đã upload."
            )

        expected_dataframe = pd.DataFrame(
            [
                {
                    "point_id": "HN_CENTER",
                    "location_id": "HN",
                    "us_aqi": 75,
                    "pm2_5": 18.5,
                },
                {
                    "point_id": "HCM_CENTER",
                    "location_id": "HCM",
                    "us_aqi": 82,
                    "pm2_5": 20.1,
                },
            ]
        )

        parquet_upload_result = (
            put_parquet_object(
                bucket_name=(
                    settings.clean_bucket
                ),
                object_name=(
                    PARQUET_OBJECT_NAME
                ),
                dataframe=(
                    expected_dataframe
                ),
                settings=settings,
                client=client,
            )
        )

        downloaded_dataframe = (
            get_parquet_object(
                bucket_name=(
                    settings.clean_bucket
                ),
                object_name=(
                    PARQUET_OBJECT_NAME
                ),
                settings=settings,
                client=client,
            )
        )

        pd.testing.assert_frame_equal(
            downloaded_dataframe,
            expected_dataframe,
            check_dtype=True,
        )

        json_exists = object_exists(
            bucket_name=(
                settings.raw_bucket
            ),
            object_name=(
                JSON_OBJECT_NAME
            ),
            settings=settings,
            client=client,
        )

        parquet_exists = object_exists(
            bucket_name=(
                settings.clean_bucket
            ),
            object_name=(
                PARQUET_OBJECT_NAME
            ),
            settings=settings,
            client=client,
        )

        raw_test_objects = (
            list_object_names(
                bucket_name=(
                    settings.raw_bucket
                ),
                prefix=(
                    "_system_tests/object_io"
                ),
                settings=settings,
                client=client,
            )
        )

        clean_test_objects = (
            list_object_names(
                bucket_name=(
                    settings.clean_bucket
                ),
                prefix=(
                    "_system_tests/object_io"
                ),
                settings=settings,
                client=client,
            )
        )

    except (
        MinioConfigurationError,
        MinioOperationError,
        MinioObjectIOError,
        S3Error,
        RuntimeError,
        AssertionError,
    ) as error:
        print(
            "Kiểm tra MinIO Object I/O "
            f"thất bại: {error}"
        )

        raise SystemExit(1) from error

    print(
        "Kiểm tra MinIO Object I/O "
        "thành công."
    )

    print()
    print("JSON object:")

    print(
        "Bucket: "
        f"{json_upload_result['bucket_name']}"
    )

    print(
        "Object: "
        f"{json_upload_result['object_name']}"
    )

    print(
        "Size: "
        f"{json_upload_result['size_bytes']} bytes"
    )

    print(
        "Exists: "
        f"{json_exists}"
    )

    print()
    print("Parquet object:")

    print(
        "Bucket: "
        f"{parquet_upload_result['bucket_name']}"
    )

    print(
        "Object: "
        f"{parquet_upload_result['object_name']}"
    )

    print(
        "Size: "
        f"{parquet_upload_result['size_bytes']} bytes"
    )

    print(
        "Rows: "
        f"{len(downloaded_dataframe)}"
    )

    print(
        "Exists: "
        f"{parquet_exists}"
    )

    print()
    print("Raw test objects:")

    for object_name in raw_test_objects:
        print(
            f"- {object_name}"
        )

    print()
    print("Clean test objects:")

    for object_name in clean_test_objects:
        print(
            f"- {object_name}"
        )


if __name__ == "__main__":
    main()