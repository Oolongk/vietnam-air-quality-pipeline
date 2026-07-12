from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg

from src.load.timescaledb_loader import (
    TimescaleDBLoadError,
    load_clean_parquet_batch,
)
from src.utils.db import (
    DatabaseConfigurationError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

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

LOAD_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "load"
)


def _read_json(
    input_path: Path,
) -> dict[str, Any]:
    try:
        with input_path.open(
            mode="r",
            encoding="utf-8",
        ) as input_file:
            data = json.load(input_file)
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise FileNotFoundError(
            "Không thể đọc Data Quality summary: "
            f"{input_path}"
        ) from error

    if not isinstance(data, dict):
        raise ValueError(
            "Data Quality summary phải là "
            "JSON object."
        )

    return data


def find_latest_loadable_clean_batch(
    quality_root: Path,
    clean_root: Path,
) -> dict[str, Any]:
    if not quality_root.exists():
        raise FileNotFoundError(
            "Quality root chưa tồn tại: "
            f"{quality_root}"
        )

    summary_files = sorted(
        quality_root.rglob(
            "data_quality_summary.json"
        ),
        key=lambda path: (
            path.stat().st_mtime
        ),
        reverse=True,
    )

    if not summary_files:
        raise FileNotFoundError(
            "Không tìm thấy "
            "data_quality_summary.json."
        )

    for summary_path in summary_files:
        summary = _read_json(
            summary_path
        )

        clean_relative_path = (
            summary.get("clean_data_path")
        )

        if not isinstance(
            clean_relative_path,
            str,
        ):
            continue

        clean_relative_path = (
            clean_relative_path.strip()
        )

        if not clean_relative_path:
            continue

        clean_data_path = (
            clean_root
            / clean_relative_path
        ).resolve()

        if not clean_data_path.exists():
            continue

        batch_id = summary.get("batch_id")
        partition_date = summary.get(
            "partition_date"
        )
        partition_hour = summary.get(
            "partition_hour"
        )

        required_values = {
            "batch_id": batch_id,
            "partition_date": partition_date,
            "partition_hour": partition_hour,
        }

        invalid_fields = [
            key
            for key, value
            in required_values.items()
            if (
                not isinstance(value, str)
                or not value.strip()
            )
        ]

        if invalid_fields:
            invalid_text = ", ".join(
                invalid_fields
            )

            raise ValueError(
                "Data Quality summary thiếu: "
                f"{invalid_text}"
            )

        return {
            "quality_summary_path": (
                summary_path
            ),
            "clean_data_path": (
                clean_data_path
            ),
            "batch_id": str(batch_id),
            "partition_date": str(
                partition_date
            ),
            "partition_hour": str(
                partition_hour
            ),
        }

    raise FileNotFoundError(
        "Không tìm thấy Data Quality batch "
        "có Clean Parquet hợp lệ."
    )


def main() -> None:
    try:
        batch_metadata = (
            find_latest_loadable_clean_batch(
                quality_root=QUALITY_ROOT,
                clean_root=CLEAN_ROOT,
            )
        )

        summary = load_clean_parquet_batch(
            clean_data_path=(
                batch_metadata[
                    "clean_data_path"
                ]
            ),
            load_root=LOAD_ROOT,
            batch_id=(
                batch_metadata["batch_id"]
            ),
            partition_date=(
                batch_metadata[
                    "partition_date"
                ]
            ),
            partition_hour=(
                batch_metadata[
                    "partition_hour"
                ]
            ),
        )
    except (
        FileNotFoundError,
        ValueError,
        TimescaleDBLoadError,
        DatabaseConfigurationError,
        psycopg.Error,
    ) as error:
        print(
            "TimescaleDB load thất bại: "
            f"{error}"
        )

        raise SystemExit(1) from error

    print(
        "Load Clean Parquet vào "
        "TimescaleDB thành công."
    )
    print(
        "Batch ID: "
        f"{summary['batch_id']}"
    )
    print(
        "Database table: "
        f"{summary['database_table']}"
    )
    print(
        "Input records: "
        f"{summary['input_records']}"
    )
    print(
        "Inserted records: "
        f"{summary['inserted_records']}"
    )
    print(
        "Updated records: "
        f"{summary['updated_records']}"
    )
    print(
        "Database records before: "
        f"{summary['database_records_before']}"
    )
    print(
        "Database records after: "
        f"{summary['database_records_after']}"
    )
    print(
        "Thời gian load: "
        f"{summary['duration_seconds']:.2f} giây"
    )
    print(
        "Load summary: "
        f"{summary['load_summary_path']}"
    )


if __name__ == "__main__":
    main()