from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.transform.air_quality_transform import (
    AirQualityTransformError,
    transform_open_meteo_payload,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "local_test"
    / "open_meteo_HN_CENTER_sample.json"
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "local_test"
    / "clean"
)

OUTPUT_PATH = (
    OUTPUT_DIRECTORY
    / "open_meteo_HN_CENTER_hourly.parquet"
)


def load_raw_payload(
    input_path: Path,
) -> dict:
    if not input_path.exists():
        raise FileNotFoundError(
            "Không tìm thấy Raw JSON tại: "
            f"{input_path}"
        )

    with input_path.open(
        mode="r",
        encoding="utf-8",
    ) as input_file:
        return json.load(input_file)


def main() -> None:
    try:
        raw_payload = load_raw_payload(
            INPUT_PATH
        )

        clean_dataframe = (
            transform_open_meteo_payload(
                raw_payload
            )
        )
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        AirQualityTransformError,
    ) as error:
        print(
            "Transform thất bại: "
            f"{error}"
        )

        raise SystemExit(1) from error

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    clean_dataframe.to_parquet(
        OUTPUT_PATH,
        engine="pyarrow",
        index=False,
        compression="snappy",
    )

    print("Transform thành công.")
    print(
        "Số record Clean: "
        f"{len(clean_dataframe)}"
    )
    print(
        "Số cột Clean: "
        f"{len(clean_dataframe.columns)}"
    )
    print(
        "File Parquet: "
        f"{OUTPUT_PATH}"
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
        clean_dataframe[
            preview_columns
        ]
        .head(5)
        .to_string(index=False)
    )

    print()
    print("Kiểu dữ liệu:")

    print(
        clean_dataframe.dtypes.to_string()
    )

    print()
    print("Thống kê giá trị thiếu:")

    missing_counts = (
        clean_dataframe
        .isna()
        .sum()
    )

    missing_counts = missing_counts[
        missing_counts > 0
    ]

    if missing_counts.empty:
        print(
            "Không có giá trị thiếu "
            "trong dữ liệu mẫu."
        )
    else:
        print(
            missing_counts.to_string()
        )


if __name__ == "__main__":
    main()