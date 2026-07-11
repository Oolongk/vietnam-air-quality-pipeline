from __future__ import annotations

from pathlib import Path

from src.ingestion.air_quality_extractor import (
    AirQualityExtractionError,
    extract_active_monitoring_points,
)
from src.ingestion.open_meteo_client import (
    OpenMeteoClient,
)
from src.utils.config_loader import (
    load_project_config,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "raw"
)


def main() -> None:
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
        print(
            "Không thể bắt đầu extraction: "
            f"{error}"
        )

        raise SystemExit(1) from error
    finally:
        client.close()

    print("Hoàn tất extraction 10 điểm.")
    print(
        "Trạng thái: "
        f"{summary['status']}"
    )
    print(
        "Batch ID: "
        f"{summary['batch_id']}"
    )
    print(
        "Tổng điểm active: "
        f"{summary['total_active_points']}"
    )
    print(
        "Điểm thành công: "
        f"{summary['succeeded_points']}"
    )
    print(
        "Điểm thất bại: "
        f"{summary['failed_points']}"
    )
    print(
        "Tổng record lấy được: "
        f"{summary['records_extracted']}"
    )
    print(
        "Thời gian chạy: "
        f"{summary['duration_seconds']:.2f} giây"
    )
    print(
        "File summary: "
        f"{RAW_ROOT / summary['summary_path']}"
    )

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