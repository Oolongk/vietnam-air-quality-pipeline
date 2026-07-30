from __future__ import annotations

from pathlib import Path

from src.ingestion.air_quality_extractor import (
    AirQualityExtractionError,
    extract_active_monitoring_points,
)
from src.ingestion.open_meteo_client import (
    OpenMeteoClient,
)
from src.operations.legacy_runtime import (
    require_legacy_local_pipeline_enabled,
)
from src.utils.config_loader import (
    load_project_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_ROOT = PROJECT_ROOT / "data" / "local_lake" / "raw"


def main() -> None:
    require_legacy_local_pipeline_enabled(
        "scripts.extract_all_monitoring_points",
    )

    _, monitoring_points = load_project_config()

    client = OpenMeteoClient()

    try:
        summary = extract_active_monitoring_points(
            monitoring_points=monitoring_points,
            client=client,
            raw_root=RAW_ROOT,
            forecast_hours=24,
        )
    except (
        AirQualityExtractionError,
        ValueError,
        TypeError,
    ) as error:
        print(f"Không thể bắt đầu extraction: {error}")

        raise SystemExit(1) from error
    finally:
        client.close()

    print("Hoàn tất extraction 10 điểm.")
    print(f"Trạng thái: {summary['status']}")
    print(f"Batch ID: {summary['batch_id']}")
    print(f"Tổng điểm active: {summary['total_active_points']}")
    print(f"Điểm thành công: {summary['succeeded_points']}")
    print(f"Điểm thất bại: {summary['failed_points']}")
    print(f"Tổng record lấy được: {summary['records_extracted']}")
    print(f"Thời gian chạy: {summary['duration_seconds']:.2f} giây")
    print(f"File summary: {RAW_ROOT / summary['summary_path']}")

    print()
    print("Kết quả từng điểm:")

    for item in summary["successes"]:
        print(
            f"- SUCCESS | "
            f"{item['point_id']} | "
            f"{item['records_extracted']} records | "
            f"{item['raw_path']}"
        )

    for item in summary["failures"]:
        print(
            f"- FAILED | "
            f"{item['point_id']} | "
            f"{item['error_type']} | "
            f"{item['error_message']}"
        )

    if summary["failed_points"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
