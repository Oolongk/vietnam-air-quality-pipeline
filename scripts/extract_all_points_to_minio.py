from __future__ import annotations

from pathlib import Path
from typing import Any

from minio.error import S3Error

from src.ingestion.minio_air_quality_extractor import (
    MinioAirQualityExtractionError,
    MonitoringPoint,
    chunk_monitoring_points,
    extract_monitoring_points_to_minio,
    get_open_meteo_batch_size,
    load_active_monitoring_points,
)
from src.ingestion.open_meteo_client import (
    OpenMeteoClient,
)
from src.operations.batch_context import (
    PipelineBatchContext,
    PipelineBatchContextError,
)
from src.utils.minio_client import (
    MinioConfigurationError,
    MinioOperationError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MONITORING_POINTS_PATH = PROJECT_ROOT / "configs" / "monitoring_points.csv"


def build_fetcher(
    client: OpenMeteoClient,
):
    def fetch_air_quality(
        point: MonitoringPoint,
    ) -> dict[str, Any]:
        return client.fetch_hourly_air_quality(
            latitude=point.latitude,
            longitude=point.longitude,
            point_id=point.point_id,
            location_id=point.location_id,
        )

    return fetch_air_quality


def prefetch_air_quality_batches(
    client: OpenMeteoClient,
    monitoring_points: list[MonitoringPoint],
    batch_size: int,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, str],
]:
    """
    Gọi Open-Meteo theo từng batch và lưu response
    theo point_id.

    Batch lỗi không làm dừng toàn bộ extraction.
    Các point thuộc batch lỗi sẽ được đánh dấu để
    extractor ghi nhận vào failures.
    """

    request_points: list[dict[str, Any]] = [
        {
            "point_id": point.point_id,
            "location_id": (point.location_id),
            "latitude": point.latitude,
            "longitude": point.longitude,
        }
        for point in monitoring_points
    ]

    responses_by_point_id: dict[
        str,
        dict[str, Any],
    ] = {}

    failures_by_point_id: dict[
        str,
        str,
    ] = {}

    for request_batch in chunk_monitoring_points(
        monitoring_points=(request_points),
        batch_size=batch_size,
    ):
        try:
            batch_results = client.fetch_hourly_air_quality_batch(
                monitoring_points=(request_batch)
            )

            if not isinstance(
                batch_results,
                list,
            ):
                raise RuntimeError("Open-Meteo batch phải trả về list.")

            if len(batch_results) != len(request_batch):
                raise RuntimeError(
                    "Số batch response không "
                    "khớp số monitoring point. "
                    f"Expected={len(request_batch)}, "
                    f"actual={len(batch_results)}."
                )

            if not all(
                isinstance(
                    result,
                    dict,
                )
                for result in batch_results
            ):
                raise RuntimeError("Một batch response không phải dictionary.")

            for request_point, result in zip(
                request_batch,
                batch_results,
                strict=True,
            ):
                point_id = str(request_point["point_id"])

                responses_by_point_id[point_id] = result

        except Exception as error:
            error_message = f"{type(error).__name__}: {error}"

            for request_point in request_batch:
                point_id = str(request_point["point_id"])

                failures_by_point_id[point_id] = error_message

    return (
        responses_by_point_id,
        failures_by_point_id,
    )


def build_prefetched_fetcher(
    responses_by_point_id: dict[
        str,
        dict[str, Any],
    ],
    failures_by_point_id: dict[
        str,
        str,
    ],
):
    """
    Tạo callback tương thích với extractor cũ.

    Callback này không gọi HTTP nữa. Nó chỉ lấy
    response đã được tải theo batch ở bước trước.
    """

    def fetch_air_quality(
        point: MonitoringPoint,
    ) -> dict[str, Any]:
        failure_message = failures_by_point_id.get(point.point_id)

        if failure_message is not None:
            raise RuntimeError(
                f"Open-Meteo batch thất bại cho {point.point_id}: {failure_message}"
            )

        api_response = responses_by_point_id.get(point.point_id)

        if api_response is None:
            raise RuntimeError(
                f"Không tìm thấy response đã tải cho monitoring point {point.point_id}."
            )

        return api_response

    return fetch_air_quality


def main() -> None:
    client = None
    batch_context = None

    try:
        batch_context = PipelineBatchContext.from_environment()
        monitoring_points = load_active_monitoring_points(MONITORING_POINTS_PATH)

        client = OpenMeteoClient()

        batch_size = get_open_meteo_batch_size()

        (
            responses_by_point_id,
            failures_by_point_id,
        ) = prefetch_air_quality_batches(
            client=client,
            monitoring_points=(monitoring_points),
            batch_size=batch_size,
        )

        fetch_air_quality = build_prefetched_fetcher(
            responses_by_point_id=(responses_by_point_id),
            failures_by_point_id=(failures_by_point_id),
        )

        summary = extract_monitoring_points_to_minio(
            monitoring_points=monitoring_points,
            fetch_air_quality=fetch_air_quality,
            batch_id=(batch_context.batch_id if batch_context is not None else None),
            started_at=(
                batch_context.started_at if batch_context is not None else None
            ),
        )

        if batch_context is not None:
            batch_context.validate_summary(summary, "Extraction summary")

    except (
        MinioAirQualityExtractionError,
        PipelineBatchContextError,
        MinioConfigurationError,
        MinioOperationError,
        S3Error,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"Extraction trực tiếp lên MinIO thất bại: {error}")

        raise SystemExit(1) from error

    finally:
        if client is not None:
            close_method = getattr(
                client,
                "close",
                None,
            )

            if callable(close_method):
                close_method()

    print("Extraction trực tiếp lên MinIO hoàn tất.")

    execution_mode = "AIRFLOW_BATCH" if batch_context is not None else "LATEST_MANUAL"
    print(f"Execution mode: {execution_mode}")
    print(f"Status: {summary['status']}")

    print(f"Batch ID: {summary['batch_id']}")

    print(f"Active points: {summary['active_points']}")

    print(f"Successful points: {summary['successful_points']}")

    print(f"Failed points: {summary['failed_points']}")

    print(f"Open-Meteo batch size: {batch_size}")

    print(f"Prefetched points: {len(responses_by_point_id)}")

    print(f"Prefetch failed points: {len(failures_by_point_id)}")

    request_metrics = client.get_request_metrics()

    print(f"Total HTTP attempts: {request_metrics['total_http_attempts']}")

    print(f"Records extracted: {summary['records_extracted']}")

    print(f"Raw bucket: {summary['raw_bucket']}")

    print(f"Batch prefix: {summary['batch_prefix']}")

    print(f"Summary object: {summary['summary_object_name']}")

    if summary["failures"]:
        print()
        print("Các điểm bị lỗi:")

        for failure in summary["failures"]:
            print(
                "- "
                f"{failure['point_id']}: "
                f"{failure['error_type']} - "
                f"{failure['error_message']}"
            )


if __name__ == "__main__":
    main()
