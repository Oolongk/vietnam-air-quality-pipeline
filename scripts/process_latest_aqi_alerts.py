from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg

from src.alerts.alert_processor import (
    AirQualityAlertProcessingError,
    process_clean_batch_alerts,
)
from src.utils.db import (
    DatabaseConfigurationError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

LOAD_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "load"
)

ALERT_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "alerts"
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
            f"Không thể đọc load summary: "
            f"{input_path}"
        ) from error

    if not isinstance(data, dict):
        raise ValueError(
            "Load summary phải là JSON object."
        )

    return data


def find_latest_successful_load(
    load_root: Path,
) -> dict[str, Any]:
    if not load_root.exists():
        raise FileNotFoundError(
            f"Load root chưa tồn tại: "
            f"{load_root}"
        )

    summary_files = sorted(
        load_root.rglob(
            "load_summary.json"
        ),
        key=lambda path: (
            path.stat().st_mtime
        ),
        reverse=True,
    )

    if not summary_files:
        raise FileNotFoundError(
            "Không tìm thấy load_summary.json."
        )

    for summary_path in summary_files:
        summary = _read_json(
            summary_path
        )

        if summary.get("status") != "SUCCESS":
            continue

        required_fields = (
            "batch_id",
            "partition_date",
            "partition_hour",
            "clean_data_path",
        )

        missing_fields = [
            field
            for field in required_fields
            if (
                not isinstance(
                    summary.get(field),
                    str,
                )
                or not summary[
                    field
                ].strip()
            )
        ]

        if missing_fields:
            continue

        clean_data_path = Path(
            summary["clean_data_path"]
        )

        if not clean_data_path.exists():
            continue

        return {
            "batch_id": summary["batch_id"],
            "partition_date": (
                summary["partition_date"]
            ),
            "partition_hour": (
                summary["partition_hour"]
            ),
            "clean_data_path": (
                clean_data_path
            ),
            "load_summary_path": (
                summary_path
            ),
        }

    raise FileNotFoundError(
        "Không tìm thấy load batch thành công "
        "có Clean Parquet hợp lệ."
    )


def main() -> None:
    try:
        batch = find_latest_successful_load(
            LOAD_ROOT
        )

        summary = process_clean_batch_alerts(
            clean_data_path=(
                batch["clean_data_path"]
            ),
            alert_root=ALERT_ROOT,
            batch_id=batch["batch_id"],
            partition_date=(
                batch["partition_date"]
            ),
            partition_hour=(
                batch["partition_hour"]
            ),
        )
    except (
        FileNotFoundError,
        ValueError,
        AirQualityAlertProcessingError,
        DatabaseConfigurationError,
        psycopg.Error,
    ) as error:
        print(
            "Phân loại AQI và tạo alert "
            f"thất bại: {error}"
        )

        raise SystemExit(1) from error

    print(
        "Phân loại AQI và tạo alert "
        "thành công."
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
        "Fact records updated: "
        f"{summary['facts_updated']}"
    )
    print(
        "Classified records: "
        f"{summary['classified_records']}"
    )
    print(
        "Null AQI records: "
        f"{summary['null_aqi_records']}"
    )
    print(
        "Alerts generated: "
        f"{summary['alerts_generated']}"
    )
    print(
        "MEDIUM alerts: "
        f"{summary['medium_alerts']}"
    )
    print(
        "HIGH alerts: "
        f"{summary['high_alerts']}"
    )
    print(
        "CRITICAL alerts: "
        f"{summary['critical_alerts']}"
    )
    print(
        "Thời gian xử lý: "
        f"{summary['duration_seconds']:.2f} giây"
    )
    print(
        "Alert summary: "
        f"{summary['alert_summary_path']}"
    )


if __name__ == "__main__":
    main()