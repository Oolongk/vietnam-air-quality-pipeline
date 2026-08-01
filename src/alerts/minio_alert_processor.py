from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from minio import Minio

from src.alerts.alert_processor import process_clean_batch_alerts
from src.utils.minio_client import MinioSettings, get_minio_client
from src.utils.minio_object_io import get_parquet_object, put_bytes_object


class MinioAlertProcessingError(RuntimeError):
    """Không thể xử lý alert cho một Clean batch trên MinIO."""


def detect_content_type(file_path: Path) -> str:
    content_types = {
        ".json": "application/json; charset=utf-8",
        ".parquet": "application/vnd.apache.parquet",
        ".csv": "text/csv; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
    }
    return content_types.get(file_path.suffix.lower(), "application/octet-stream")


def upload_alert_directory_to_minio(
    alert_directory: Path,
    bucket_name: str,
    object_prefix: str,
    settings: MinioSettings,
    client: Minio,
) -> list[dict[str, Any]]:
    if not alert_directory.is_dir():
        raise MinioAlertProcessingError(
            f"Không tìm thấy thư mục alert output: {alert_directory}"
        )

    files = sorted(
        file_path for file_path in alert_directory.rglob("*") if file_path.is_file()
    )
    if not files:
        raise MinioAlertProcessingError("Alert processor không tạo ra file output nào.")

    uploaded_objects: list[dict[str, Any]] = []

    for file_path in files:
        relative_path = file_path.relative_to(alert_directory).as_posix()
        object_name = f"{object_prefix.rstrip('/')}/{relative_path}"

        try:
            payload = file_path.read_bytes()
        except OSError as error:
            raise MinioAlertProcessingError(
                f"Không thể đọc file alert tạm: {file_path}"
            ) from error

        if not payload:
            raise MinioAlertProcessingError(
                f"Không upload file alert rỗng: {file_path}"
            )

        upload_result = put_bytes_object(
            bucket_name=bucket_name,
            object_name=object_name,
            payload=payload,
            content_type=detect_content_type(file_path),
            settings=settings,
            client=client,
        )

        uploaded_objects.append(
            {
                "local_name": relative_path,
                "bucket_name": bucket_name,
                "object_name": object_name,
                "size_bytes": upload_result["size_bytes"],
                "etag": upload_result["etag"],
            }
        )

    return uploaded_objects


def process_minio_quality_batch_alerts(
    quality_summary: Mapping[str, Any],
    quality_summary_object_name: str,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> dict[str, Any]:
    if not isinstance(quality_summary, Mapping):
        raise MinioAlertProcessingError("Data Quality summary phải là JSON object.")

    resolved_settings = settings or MinioSettings.from_environment()
    resolved_client = client or get_minio_client(resolved_settings)

    batch_id = str(quality_summary.get("batch_id", "")).strip()
    partition_date = str(quality_summary.get("partition_date", "")).strip()
    partition_hour = str(quality_summary.get("partition_hour", "")).strip()
    clean_object_name = str(quality_summary.get("clean_object_name", "")).strip()
    normalized_quality_summary_object_name = str(quality_summary_object_name).strip()

    if not all(
        (
            batch_id,
            partition_date,
            partition_hour,
            clean_object_name,
            normalized_quality_summary_object_name,
        )
    ):
        raise MinioAlertProcessingError(
            "Data Quality summary thiếu batch hoặc object metadata."
        )

    status = str(quality_summary.get("status", "")).strip().upper()
    if status not in {"SUCCESS", "PARTIAL_SUCCESS"}:
        raise MinioAlertProcessingError(
            f"Data Quality summary không thể tạo alert. Status={status or 'EMPTY'}."
        )

    try:
        valid_records = int(quality_summary.get("valid_records", 0))
    except (TypeError, ValueError) as error:
        raise MinioAlertProcessingError(
            "Data Quality summary có valid_records không hợp lệ."
        ) from error

    if valid_records <= 0:
        raise MinioAlertProcessingError(
            "Data Quality summary không có valid_records để tạo alert."
        )

    clean_dataframe = get_parquet_object(
        bucket_name=resolved_settings.clean_bucket,
        object_name=clean_object_name,
        settings=resolved_settings,
        client=resolved_client,
    )

    if clean_dataframe.empty:
        raise MinioAlertProcessingError("Clean Parquet không có dữ liệu.")

    with TemporaryDirectory(prefix="air_quality_alerts_") as temporary_directory:
        temporary_root = Path(temporary_directory)
        temporary_clean_path = temporary_root / "input" / "data.parquet"
        temporary_clean_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_alert_root = temporary_root / "alerts"

        clean_dataframe.to_parquet(
            temporary_clean_path,
            engine="pyarrow",
            compression="snappy",
            index=False,
        )

        alert_summary = process_clean_batch_alerts(
            clean_data_path=temporary_clean_path,
            alert_root=temporary_alert_root,
            batch_id=batch_id,
            partition_date=partition_date,
            partition_hour=partition_hour,
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
            "alerts/air_quality/hourly/"
            f"date={partition_date}/"
            f"hour={partition_hour}/"
            f"batch_id={batch_id}"
        )

        uploaded_objects = upload_alert_directory_to_minio(
            alert_directory=generated_alert_directory,
            bucket_name=resolved_settings.mart_bucket,
            object_prefix=minio_alert_prefix,
            settings=resolved_settings,
            client=resolved_client,
        )

    alert_summary_object_name = f"{minio_alert_prefix}/alert_summary.json"

    return {
        **alert_summary,
        "storage_backend": "minio",
        "quality_summary_bucket": resolved_settings.clean_bucket,
        "quality_summary_object_name": normalized_quality_summary_object_name,
        "clean_bucket": resolved_settings.clean_bucket,
        "clean_object_name": clean_object_name,
        "summary_bucket": resolved_settings.mart_bucket,
        "summary_object_name": alert_summary_object_name,
        "uploaded_object_count": len(uploaded_objects),
        "uploaded_objects": uploaded_objects,
    }
