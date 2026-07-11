from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.quality.quality_processor import (
    DataQualityProcessingError,
    process_transformed_batch_quality,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

TRANSFORMED_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "transformed"
)

CLEAN_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "clean"
)

QUALITY_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "quality"
)


def find_latest_transformed_batch(
    transformed_root: Path,
) -> Path:
    if not transformed_root.exists():
        raise FileNotFoundError(
            "Transformed root chưa tồn tại: "
            f"{transformed_root}"
        )

    summary_files = list(
        transformed_root.rglob(
            "transform_summary.json"
        )
    )

    if not summary_files:
        raise FileNotFoundError(
            "Không tìm thấy "
            "transform_summary.json."
        )

    latest_summary = max(
        summary_files,
        key=lambda path: (
            path.stat().st_mtime
        ),
    )

    return latest_summary.parent


def main() -> None:
    try:
        transformed_batch_directory = (
            find_latest_transformed_batch(
                TRANSFORMED_ROOT
            )
        )

        summary = (
            process_transformed_batch_quality(
                transformed_batch_directory=(
                    transformed_batch_directory
                ),
                clean_root=CLEAN_ROOT,
                quality_root=QUALITY_ROOT,
            )
        )
    except (
        FileNotFoundError,
        DataQualityProcessingError,
        OSError,
    ) as error:
        print(
            "Data Quality thất bại: "
            f"{error}"
        )

        raise SystemExit(1) from error

    print("Hoàn tất Data Quality Check.")
    print(
        "Trạng thái: "
        f"{summary['status']}"
    )
    print(
        "Batch ID: "
        f"{summary['batch_id']}"
    )
    print(
        "Input records: "
        f"{summary['input_records']}"
    )
    print(
        "Valid records: "
        f"{summary['valid_records']}"
    )
    print(
        "Bad records: "
        f"{summary['bad_records']}"
    )
    print(
        "Valid percentage: "
        f"{summary['valid_percentage']}%"
    )
    print(
        "Thời gian chạy: "
        f"{summary['duration_seconds']:.2f} giây"
    )

    print()
    print("Kết quả từng rule:")

    for check in summary["checks"]:
        print(
            f"- {check['status']} | "
            f"{check['check_name']} | "
            f"Bad records: "
            f"{check['bad_records_count']}"
        )

    clean_relative_path = (
        summary["clean_data_path"]
    )

    if clean_relative_path:
        clean_path = (
            CLEAN_ROOT
            / clean_relative_path
        )

        clean_dataframe = pd.read_parquet(
            clean_path
        )

        print()
        print(
            "Clean Parquet: "
            f"{clean_path}"
        )

        print("Năm Clean record đầu tiên:")

        preview_columns = [
            "point_id",
            "location_id",
            "forecast_time",
            "pm2_5",
            "pm10",
            "us_aqi",
            "source",
        ]

        print(
            clean_dataframe[
                preview_columns
            ]
            .head(5)
            .to_string(index=False)
        )

    bad_relative_path = (
        summary["bad_records_path"]
    )

    if bad_relative_path:
        bad_path = (
            QUALITY_ROOT
            / bad_relative_path
        )

        print()
        print(
            "Bad Records Parquet: "
            f"{bad_path}"
        )

    if summary["status"] != "SUCCESS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()