from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.transform.batch_transformer import (
    BatchTransformError,
    transform_raw_batch,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "raw"
)

TRANSFORMED_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "transformed"
)


def find_latest_raw_batch(
    raw_root: Path,
) -> Path:
    if not raw_root.exists():
        raise FileNotFoundError(
            f"Raw root chưa tồn tại: {raw_root}"
        )

    summary_files = list(
        raw_root.rglob(
            "run_summary.json"
        )
    )

    if not summary_files:
        raise FileNotFoundError(
            "Không tìm thấy run_summary.json "
            f"bên trong {raw_root}"
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
        raw_batch_directory = (
            find_latest_raw_batch(
                RAW_ROOT
            )
        )

        summary = transform_raw_batch(
            raw_batch_directory=(
                raw_batch_directory
            ),
            transformed_root=(
                TRANSFORMED_ROOT
            ),
        )
    except (
        FileNotFoundError,
        BatchTransformError,
        OSError,
    ) as error:
        print(
            "Batch transform thất bại: "
            f"{error}"
        )

        raise SystemExit(1) from error

    print("Hoàn tất batch transform.")
    print(
        "Trạng thái: "
        f"{summary['status']}"
    )
    print(
        "Batch ID: "
        f"{summary['batch_id']}"
    )
    print(
        "Raw batch: "
        f"{raw_batch_directory}"
    )
    print(
        "Số Raw file tìm thấy: "
        f"{summary['discovered_raw_files']}"
    )
    print(
        "File thành công: "
        f"{summary['succeeded_files']}"
    )
    print(
        "File thất bại: "
        f"{summary['failed_files']}"
    )
    print(
        "Tổng record sau transform: "
        f"{summary['records_transformed']}"
    )
    print(
        "Số dòng thuộc nhóm duplicate: "
        f"{summary['duplicate_key_rows']}"
    )
    print(
        "Thời gian chạy: "
        f"{summary['duration_seconds']:.2f} giây"
    )

    transformed_relative_path = (
        summary["transformed_data_path"]
    )

    if transformed_relative_path:
        transformed_path = (
            TRANSFORMED_ROOT
            / transformed_relative_path
        )

        print(
            "File Parquet: "
            f"{transformed_path}"
        )

        dataframe = pd.read_parquet(
            transformed_path
        )

        print()
        print("Năm record đầu tiên:")

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
            dataframe[
                preview_columns
            ]
            .head(5)
            .to_string(index=False)
        )

        print()
        print("Số record theo point_id:")

        print(
            dataframe
            .groupby("point_id")
            .size()
            .sort_index()
            .to_string()
        )

    if summary["status"] != "SUCCESS":
        print()
        print("Các file transform thất bại:")

        for failure in summary["failures"]:
            print(
                f"- {failure['raw_path']} | "
                f"{failure['error_type']} | "
                f"{failure['error_message']}"
            )

        raise SystemExit(1)


if __name__ == "__main__":
    main()  