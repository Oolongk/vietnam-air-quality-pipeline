from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from src.ingestion.open_meteo_client import (
    OpenMeteoClient,
    OpenMeteoClientError,
)


VIETNAM_TIMEZONE = timezone(
    timedelta(hours=7),
    name="Asia/Ho_Chi_Minh",
)

REQUIRED_POINT_COLUMNS = {
    "point_id",
    "location_id",
    "latitude",
    "longitude",
    "is_active",
}

SAFE_BATCH_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]+$"
)


class AirQualityExtractionError(RuntimeError):
    """Lỗi cấu hình hoặc điều phối quá trình extraction."""


def _validate_monitoring_points(
    monitoring_points: pd.DataFrame,
) -> None:
    if not isinstance(
        monitoring_points,
        pd.DataFrame,
    ):
        raise TypeError(
            "monitoring_points phải là Pandas DataFrame."
        )

    missing_columns = (
        REQUIRED_POINT_COLUMNS
        - set(monitoring_points.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise AirQualityExtractionError(
            "Monitoring points thiếu các cột: "
            f"{missing_text}"
        )


def _create_batch_id(
    run_time: datetime,
) -> str:
    timestamp_part = run_time.strftime(
        "%Y%m%dT%H%M%S"
    )

    random_part = uuid4().hex[:8]

    return f"{timestamp_part}_{random_part}"


def _validate_batch_id(
    batch_id: str,
) -> str:
    cleaned_batch_id = batch_id.strip()

    if not cleaned_batch_id:
        raise AirQualityExtractionError(
            "batch_id không được rỗng."
        )

    if not SAFE_BATCH_ID_PATTERN.fullmatch(
        cleaned_batch_id
    ):
        raise AirQualityExtractionError(
            "batch_id chỉ được chứa chữ, số, "
            "dấu gạch ngang và dấu gạch dưới."
        )

    return cleaned_batch_id


def _build_batch_directory(
    raw_root: Path,
    run_time: datetime,
    batch_id: str,
) -> Path:
    return (
        raw_root
        / "open_meteo"
        / "air_quality"
        / f"date={run_time:%Y-%m-%d}"
        / f"hour={run_time:%H}"
        / f"batch_id={batch_id}"
    )


def _write_json(
    output_path: Path,
    data: dict[str, Any],
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = output_path.with_suffix(
        output_path.suffix + ".tmp"
    )

    with temporary_path.open(
        mode="w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            data,
            output_file,
            ensure_ascii=False,
            indent=2,
        )

    temporary_path.replace(output_path)


def extract_active_monitoring_points(
    monitoring_points: pd.DataFrame,
    client: OpenMeteoClient,
    raw_root: Path,
    forecast_hours: int = 24,
    run_time: datetime | None = None,
    batch_id: str | None = None,
) -> dict[str, Any]:
    _validate_monitoring_points(
        monitoring_points
    )

    if forecast_hours <= 0:
        raise ValueError(
            "forecast_hours phải lớn hơn 0."
        )

    resolved_run_time = (
        run_time
        or datetime.now(VIETNAM_TIMEZONE)
    )

    if (
        resolved_run_time.tzinfo is None
        or resolved_run_time.utcoffset() is None
    ):
        raise AirQualityExtractionError(
            "run_time phải có timezone."
        )

    resolved_batch_id = _validate_batch_id(
        batch_id
        or _create_batch_id(
            resolved_run_time
        )
    )

    batch_directory = _build_batch_directory(
        raw_root=raw_root,
        run_time=resolved_run_time,
        batch_id=resolved_batch_id,
    )

    active_points = monitoring_points[
        monitoring_points["is_active"]
    ].copy()

    active_points = active_points.sort_values(
        by="point_id"
    ).reset_index(drop=True)

    if active_points.empty:
        raise AirQualityExtractionError(
            "Không có monitoring point nào "
            "đang hoạt động."
        )

    started_at = datetime.now(
        timezone.utc
    )

    successes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for point in active_points.to_dict(
        orient="records"
    ):
        point_id = str(
            point["point_id"]
        ).strip()

        location_id = str(
            point["location_id"]
        ).strip()

        try:
            raw_payload = (
                client.fetch_hourly_air_quality(
                    point_id=point_id,
                    location_id=location_id,
                    latitude=float(
                        point["latitude"]
                    ),
                    longitude=float(
                        point["longitude"]
                    ),
                    forecast_hours=forecast_hours,
                )
            )

            output_path = (
                batch_directory
                / f"point_id={point_id}"
                / "data.json"
            )

            _write_json(
                output_path=output_path,
                data=raw_payload,
            )

            record_count = len(
                raw_payload["response"][
                    "hourly"
                ]["time"]
            )

            relative_path = (
                output_path
                .relative_to(raw_root)
                .as_posix()
            )

            successes.append(
                {
                    "point_id": point_id,
                    "location_id": location_id,
                    "records_extracted": (
                        record_count
                    ),
                    "raw_path": relative_path,
                }
            )
        except (
            OpenMeteoClientError,
            TypeError,
            ValueError,
            KeyError,
        ) as error:
            failures.append(
                {
                    "point_id": point_id,
                    "location_id": location_id,
                    "error_type": (
                        type(error).__name__
                    ),
                    "error_message": str(error),
                }
            )

    finished_at = datetime.now(
        timezone.utc
    )

    succeeded_points = len(successes)
    failed_points = len(failures)

    if failed_points == 0:
        status = "SUCCESS"
    elif succeeded_points == 0:
        status = "FAILED"
    else:
        status = "PARTIAL_SUCCESS"

    summary_path = (
        batch_directory
        / "run_summary.json"
    )

    summary = {
        "pipeline_name": (
            "open_meteo_air_quality_extraction"
        ),
        "source": "open_meteo",
        "status": status,
        "batch_id": resolved_batch_id,
        "partition_timezone": (
            str(resolved_run_time.tzinfo)
        ),
        "partition_date": (
            resolved_run_time.strftime(
                "%Y-%m-%d"
            )
        ),
        "partition_hour": (
            resolved_run_time.strftime("%H")
        ),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (
            finished_at - started_at
        ).total_seconds(),
        "forecast_hours": forecast_hours,
        "total_active_points": len(
            active_points
        ),
        "succeeded_points": succeeded_points,
        "failed_points": failed_points,
        "records_extracted": sum(
            item["records_extracted"]
            for item in successes
        ),
        "successes": successes,
        "failures": failures,
        "summary_path": (
            summary_path
            .relative_to(raw_root)
            .as_posix()
        ),
    }

    _write_json(
        output_path=summary_path,
        data=summary,
    )

    return summary