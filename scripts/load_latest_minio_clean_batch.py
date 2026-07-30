from __future__ import annotations

from minio.error import S3Error
import psycopg

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
        summary = load_latest_minio_clean_batch()

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
        print(f"Load Clean Parquet từ MinIO vào TimescaleDB thất bại: {error}")

        raise SystemExit(1) from error

    print("Load Clean Parquet từ MinIO vào TimescaleDB hoàn tất.")

    print(f"Status: {summary['status']}")

    print(f"Batch ID: {summary['batch_id']}")

    print(f"Input rows: {summary['input_rows']}")

    print(f"Processed rows: {summary['processed_rows']}")

    print(f"Inserted rows: {summary['inserted_rows']}")

    print(f"Updated rows: {summary['updated_rows']}")

    print(f"Fact table: {summary['fact_table']}")

    print(f"Database time column: {summary['database_time_column']}")

    print(f"Clean object: {summary['clean_object_name']}")

    print(f"Load summary: {summary['summary_bucket']}/{summary['summary_object_name']}")


if __name__ == "__main__":
    main()
