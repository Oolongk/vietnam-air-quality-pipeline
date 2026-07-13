from __future__ import annotations

from pathlib import Path
from typing import Any

from minio.error import S3Error

from src.ingestion.minio_air_quality_extractor import (
    MinioAirQualityExtractionError,
    MonitoringPoint,
    extract_monitoring_points_to_minio,
    load_active_monitoring_points,
)
from src.ingestion.open_meteo_client import (
    OpenMeteoClient,
)
from src.utils.minio_client import (
    MinioConfigurationError,
    MinioOperationError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

MONITORING_POINTS_PATH = (
    PROJECT_ROOT
    / "configs"
    / "monitoring_points.csv"
)


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


def main() -> None:
    client = None

    try:
        monitoring_points = (
            load_active_monitoring_points(
                MONITORING_POINTS_PATH
            )
        )

        client = OpenMeteoClient()

        fetch_air_quality = (
            build_fetcher(
                client
            )
        )

        summary = (
            extract_monitoring_points_to_minio(
                monitoring_points=(
                    monitoring_points
                ),
                fetch_air_quality=(
                    fetch_air_quality
                ),
            )
        )

    except (
        MinioAirQualityExtractionError,
        MinioConfigurationError,
        MinioOperationError,
        S3Error,
        RuntimeError,
        ValueError,
    ) as error:
        print(
            "Extraction trực tiếp lên MinIO "
            f"thất bại: {error}"
        )

        raise SystemExit(1) from error

    finally:
        if client is not None:
            close_method = getattr(
                client,
                "close",
                None,
            )

            if callable(
                close_method
            ):
                close_method()

    print(
        "Extraction trực tiếp lên MinIO "
        "hoàn tất."
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
        "Active points: "
        f"{summary['active_points']}"
    )

    print(
        "Successful points: "
        f"{summary['successful_points']}"
    )

    print(
        "Failed points: "
        f"{summary['failed_points']}"
    )

    print(
        "Records extracted: "
        f"{summary['records_extracted']}"
    )

    print(
        "Raw bucket: "
        f"{summary['raw_bucket']}"
    )

    print(
        "Batch prefix: "
        f"{summary['batch_prefix']}"
    )

    print(
        "Summary object: "
        f"{summary['summary_object_name']}"
    )

    if summary["failures"]:
        print()
        print("Các điểm bị lỗi:")

        for failure in summary[
            "failures"
        ]:
            print(
                "- "
                f"{failure['point_id']}: "
                f"{failure['error_type']} - "
                f"{failure['error_message']}"
            )


if __name__ == "__main__":
    main()