from __future__ import annotations

import psycopg
from minio.error import S3Error

from src.load.minio_timescaledb_loader import (
    MinioTimescaleDBLoadError,
    load_latest_minio_clean_batch,
)
from src.quality.minio_quality_processor import (
    MinioDataQualityError,
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
        summary = (
            load_latest_minio_clean_batch()
        )

    except (
        MinioTimescaleDBLoadError,
        MinioDataQualityError,
        MinioConfigurationError,
        MinioOperationError,
        MinioObjectIOError,
        S3Error,
        psycopg.Error,
        ValueError,
        TypeError,
    ) as error:
        print(
            "Load Clean Parquet từ MinIO "
            f"vào TimescaleDB thất bại: {error}"
        )

        raise SystemExit(1) from error

    print(
        "Load Clean Parquet từ MinIO "
        "vào TimescaleDB hoàn tất."
    )

    print(
        "Status: "
        f"{summary['status']}"
    )

    print(
        "Batch ID: "
        f"{summary['batch_id']}"
    )

    print(
        "Input rows: "
        f"{summary['input_rows']}"
    )

    print(
        "Processed rows: "
        f"{summary['processed_rows']}"
    )

    print(
        "Inserted rows: "
        f"{summary['inserted_rows']}"
    )

    print(
        "Updated rows: "
        f"{summary['updated_rows']}"
    )

    print(
        "Fact table: "
        f"{summary['fact_table']}"
    )

    print(
        "Database time column: "
        f"{summary['database_time_column']}"
    )

    print(
        "Clean object: "
        f"{summary['clean_object_name']}"
    )

    print(
        "Load summary: "
        f"{summary['summary_bucket']}/"
        f"{summary['summary_object_name']}"
    )


if __name__ == "__main__":
    main()