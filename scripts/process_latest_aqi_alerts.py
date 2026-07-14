from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from minio import Minio
from minio.error import S3Error

from src.alerts.alert_processor import (
    process_clean_batch_alerts,
)
from src.quality.minio_quality_processor import (
    MinioDataQualityError,
    find_latest_loadable_quality_batch,
)
from src.utils.minio_client import (
    MinioConfigurationError,
    MinioOperationError,
    MinioSettings,
    get_minio_client,
)
from src.utils.minio_object_io import (
    MinioObjectIOError,
    get_parquet_object,
    put_bytes_object,
)


def detect_content_type(
    file_path: Path,
) -> str:
    suffix = file_path.suffix.lower()

    content_types = {
        ".json": (
            "application/json; charset=utf-8"
        ),
        ".parquet": (
            "application/vnd.apache.parquet"
        ),
        ".csv": (
            "text/csv; charset=utf-8"
        ),
        ".txt": (
            "text/plain; charset=utf-8"
        ),
    }

    return content_types.get(
        suffix,
        "application/octet-stream",
    )


def upload_alert_directory_to_minio(
    alert_directory: Path,
    bucket_name: str,
    object_prefix: str,
    settings: MinioSettings,
    client: Minio,
) -> list[dict[str, Any]]:
    if not alert_directory.exists():
        raise RuntimeError(
            "Không tìm thấy thư mục alert "
            f"được tạo: {alert_directory}"
        )

    uploaded_objects: list[
        dict[str, Any]
    ] = []

    files = sorted(
        file_path
        for file_path in (
            alert_directory.rglob("*")
        )
        if file_path.is_file()
    )

    if not files:
        raise RuntimeError(
            "Alert processor không tạo "
            "ra file output nào."
        )

    for file_path in files:
        relative_path = (
            file_path
            .relative_to(
                alert_directory
            )
            .as_posix()
        )

        object_name = (
            f"{object_prefix}/"
            f"{relative_path}"
        )

        try:
            payload = file_path.read_bytes()
        except OSError as error:
            raise RuntimeError(
                "Không thể đọc file alert tạm: "
                f"{file_path}"
            ) from error

        if not payload:
            raise RuntimeError(
                "Không upload file alert rỗng: "
                f"{file_path}"
            )

        upload_result = put_bytes_object(
            bucket_name=bucket_name,
            object_name=object_name,
            payload=payload,
            content_type=(
                detect_content_type(
                    file_path
                )
            ),
            settings=settings,
            client=client,
        )

        uploaded_objects.append(
            {
                "local_name": (
                    relative_path
                ),
                "bucket_name": (
                    bucket_name
                ),
                "object_name": (
                    object_name
                ),
                "size_bytes": (
                    upload_result[
                        "size_bytes"
                    ]
                ),
                "etag": (
                    upload_result[
                        "etag"
                    ]
                ),
            }
        )

    return uploaded_objects


def main() -> None:
    try:
        minio_settings = (
            MinioSettings.from_environment()
        )

        minio_client = get_minio_client(
            minio_settings
        )

        (
            quality_summary_object_name,
            quality_summary,
        ) = (
            find_latest_loadable_quality_batch(
                settings=minio_settings,
                client=minio_client,
            )
        )

        batch_id = str(
            quality_summary[
                "batch_id"
            ]
        ).strip()

        partition_date = str(
            quality_summary[
                "partition_date"
            ]
        ).strip()

        partition_hour = str(
            quality_summary[
                "partition_hour"
            ]
        ).strip()

        clean_object_name = str(
            quality_summary[
                "clean_object_name"
            ]
        ).strip()

        if not all(
            (
                batch_id,
                partition_date,
                partition_hour,
                clean_object_name,
            )
        ):
            raise RuntimeError(
                "Quality summary thiếu "
                "batch hoặc object metadata."
            )

        clean_dataframe = (
            get_parquet_object(
                bucket_name=(
                    minio_settings
                    .clean_bucket
                ),
                object_name=(
                    clean_object_name
                ),
                settings=minio_settings,
                client=minio_client,
            )
        )

        if clean_dataframe.empty:
            raise RuntimeError(
                "Clean Parquet mới nhất "
                "không có dữ liệu."
            )

        print(
            "Đã chọn batch mới nhất "
            "từ MinIO:"
        )

        print(
            f"Batch ID: {batch_id}"
        )

        print(
            "Quality summary: "
            f"{quality_summary_object_name}"
        )

        print(
            "Clean object: "
            f"{clean_object_name}"
        )

        print(
            "Clean rows: "
            f"{len(clean_dataframe)}"
        )

        with TemporaryDirectory(
            prefix="air_quality_alerts_"
        ) as temporary_directory:
            temporary_root = Path(
                temporary_directory
            )

            temporary_clean_path = (
                temporary_root
                / "input"
                / "data.parquet"
            )

            temporary_clean_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temporary_alert_root = (
                temporary_root
                / "alerts"
            )

            clean_dataframe.to_parquet(
                temporary_clean_path,
                engine="pyarrow",
                compression="snappy",
                index=False,
            )

            alert_summary = (
                process_clean_batch_alerts(
                    clean_data_path=(
                        temporary_clean_path
                    ),
                    alert_root=(
                        temporary_alert_root
                    ),
                    batch_id=batch_id,
                    partition_date=(
                        partition_date
                    ),
                    partition_hour=(
                        partition_hour
                    ),
                )
            )

            generated_alert_directory = (
                temporary_alert_root
                / "air_quality"
                / "hourly"
                / f"date={partition_date}"
                / f"hour={partition_hour}"
                / f"batch_id={batch_id}"
            )

            minio_alert_prefix = (
                "alerts/"
                "air_quality/"
                "hourly/"
                f"date={partition_date}/"
                f"hour={partition_hour}/"
                f"batch_id={batch_id}"
            )

            uploaded_objects = (
                upload_alert_directory_to_minio(
                    alert_directory=(
                        generated_alert_directory
                    ),
                    bucket_name=(
                        minio_settings
                        .mart_bucket
                    ),
                    object_prefix=(
                        minio_alert_prefix
                    ),
                    settings=minio_settings,
                    client=minio_client,
                )
            )

        print()
        print(
            "Xử lý AQI và alert hoàn tất."
        )

        print(
            "Batch ID đã xử lý: "
            f"{batch_id}"
        )

        print(
            "Status: "
            f"{alert_summary.get(
                'status',
                'UNKNOWN',
            )}"
        )

        print(
            "Input records: "
            f"{alert_summary.get(
                'input_records',
                alert_summary.get(
                    'processed_records',
                    len(clean_dataframe),
                ),
            )}"
        )

        print(
            "Số file đã upload lên MinIO: "
            f"{len(uploaded_objects)}"
        )

        print(
            "MinIO bucket: "
            f"{minio_settings.mart_bucket}"
        )

        print(
            "MinIO prefix: "
            f"{minio_alert_prefix}"
        )

        print()
        print("Các object đã upload:")

        for uploaded_object in (
            uploaded_objects
        ):
            print(
                "- "
                f"{uploaded_object[
                    'object_name'
                ]} "
                f"({uploaded_object[
                    'size_bytes'
                ]} bytes)"
            )

    except (
        MinioDataQualityError,
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
        print(
            "Xử lý AQI và alert "
            f"thất bại: {error}"
        )

        raise SystemExit(1) from error


if __name__ == "__main__":
    main()