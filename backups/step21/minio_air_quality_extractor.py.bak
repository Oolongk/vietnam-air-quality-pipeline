from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from minio import Minio

from src.utils.minio_client import (
    MinioSettings,
    ensure_buckets,
    get_minio_client,
)
from src.utils.minio_object_io import (
    put_json_object,
)


class MinioAirQualityExtractionError(
    RuntimeError
):
    """Lỗi khi extraction dữ liệu vào MinIO."""


@dataclass(frozen=True)
class MonitoringPoint:
    point_id: str
    location_id: str
    point_name: str
    point_type: str
    latitude: float
    longitude: float
    is_active: bool


AirQualityFetcher = Callable[
    [MonitoringPoint],
    dict[str, Any],
]


REQUIRED_POINT_COLUMNS: set[str] = {
    "point_id",
    "location_id",
    "point_name",
    "point_type",
    "latitude",
    "longitude",
    "is_active",
}


def _parse_boolean(
    value: str,
    field_name: str,
) -> bool:
    normalized_value = (
        value.strip().lower()
    )

    if normalized_value in {
        "true",
        "1",
        "yes",
        "y",
    }:
        return True

    if normalized_value in {
        "false",
        "0",
        "no",
        "n",
    }:
        return False

    raise MinioAirQualityExtractionError(
        f"{field_name} phải là true hoặc false, "
        f"nhận được: {value!r}"
    )


def _require_text(
    row: dict[str, str],
    field_name: str,
    row_number: int,
) -> str:
    value = row.get(field_name)

    if value is None:
        raise MinioAirQualityExtractionError(
            f"Thiếu cột {field_name} "
            f"tại dòng {row_number}."
        )

    cleaned_value = value.strip()

    if not cleaned_value:
        raise MinioAirQualityExtractionError(
            f"{field_name} bị rỗng "
            f"tại dòng {row_number}."
        )

    return cleaned_value


def _parse_coordinate(
    row: dict[str, str],
    field_name: str,
    row_number: int,
    minimum: float,
    maximum: float,
) -> float:
    raw_value = _require_text(
        row=row,
        field_name=field_name,
        row_number=row_number,
    )

    try:
        coordinate = float(
            raw_value
        )
    except ValueError as error:
        raise MinioAirQualityExtractionError(
            f"{field_name} phải là số "
            f"tại dòng {row_number}."
        ) from error

    if not minimum <= coordinate <= maximum:
        raise MinioAirQualityExtractionError(
            f"{field_name} tại dòng "
            f"{row_number} phải nằm trong "
            f"khoảng {minimum} đến {maximum}."
        )

    return coordinate


def load_active_monitoring_points(
    csv_path: Path,
) -> list[MonitoringPoint]:
    resolved_path = csv_path.resolve()

    if not resolved_path.exists():
        raise MinioAirQualityExtractionError(
            "Không tìm thấy monitoring points CSV: "
            f"{resolved_path}"
        )

    if not resolved_path.is_file():
        raise MinioAirQualityExtractionError(
            "Monitoring points path không phải file: "
            f"{resolved_path}"
        )

    try:
        with resolved_path.open(
            mode="r",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            reader = csv.DictReader(
                csv_file
            )

            if reader.fieldnames is None:
                raise (
                    MinioAirQualityExtractionError(
                        "Monitoring points CSV "
                        "không có header."
                    )
                )

            actual_columns = {
                column.strip()
                for column in reader.fieldnames
                if column is not None
            }

            missing_columns = (
                REQUIRED_POINT_COLUMNS
                - actual_columns
            )

            if missing_columns:
                missing_text = ", ".join(
                    sorted(missing_columns)
                )

                raise (
                    MinioAirQualityExtractionError(
                        "Monitoring points CSV "
                        "thiếu các cột: "
                        f"{missing_text}"
                    )
                )

            monitoring_points: list[
                MonitoringPoint
            ] = []

            point_ids: set[str] = set()

            for row_number, row in enumerate(
                reader,
                start=2,
            ):
                point_id = _require_text(
                    row=row,
                    field_name="point_id",
                    row_number=row_number,
                )

                if point_id in point_ids:
                    raise (
                        MinioAirQualityExtractionError(
                            "Duplicate point_id "
                            f"{point_id!r} tại dòng "
                            f"{row_number}."
                        )
                    )

                point_ids.add(
                    point_id
                )

                is_active = _parse_boolean(
                    value=_require_text(
                        row=row,
                        field_name="is_active",
                        row_number=row_number,
                    ),
                    field_name="is_active",
                )

                monitoring_point = (
                    MonitoringPoint(
                        point_id=point_id,
                        location_id=(
                            _require_text(
                                row=row,
                                field_name=(
                                    "location_id"
                                ),
                                row_number=(
                                    row_number
                                ),
                            )
                        ),
                        point_name=(
                            _require_text(
                                row=row,
                                field_name=(
                                    "point_name"
                                ),
                                row_number=(
                                    row_number
                                ),
                            )
                        ),
                        point_type=(
                            _require_text(
                                row=row,
                                field_name=(
                                    "point_type"
                                ),
                                row_number=(
                                    row_number
                                ),
                            )
                        ),
                        latitude=(
                            _parse_coordinate(
                                row=row,
                                field_name=(
                                    "latitude"
                                ),
                                row_number=(
                                    row_number
                                ),
                                minimum=-90,
                                maximum=90,
                            )
                        ),
                        longitude=(
                            _parse_coordinate(
                                row=row,
                                field_name=(
                                    "longitude"
                                ),
                                row_number=(
                                    row_number
                                ),
                                minimum=-180,
                                maximum=180,
                            )
                        ),
                        is_active=is_active,
                    )
                )

                if monitoring_point.is_active:
                    monitoring_points.append(
                        monitoring_point
                    )

    except OSError as error:
        raise MinioAirQualityExtractionError(
            "Không thể đọc monitoring points CSV: "
            f"{resolved_path}"
        ) from error

    if not monitoring_points:
        raise MinioAirQualityExtractionError(
            "Không có monitoring point active."
        )

    return monitoring_points


def build_batch_prefix(
    partition_date: str,
    partition_hour: str,
    batch_id: str,
) -> str:
    return (
        "open_meteo/"
        "air_quality/"
        f"date={partition_date}/"
        f"hour={partition_hour}/"
        f"batch_id={batch_id}"
    )


def build_point_object_name(
    batch_prefix: str,
    point_id: str,
) -> str:
    return (
        f"{batch_prefix}/"
        f"point_id={point_id}/"
        "data.json"
    )


def build_summary_object_name(
    batch_prefix: str,
) -> str:
    return (
        f"{batch_prefix}/"
        "run_summary.json"
    )


def _count_hourly_records(
    api_response: dict[str, Any],
) -> int:
    hourly = api_response.get(
        "hourly"
    )

    if not isinstance(
        hourly,
        dict,
    ):
        return 0

    hourly_times = hourly.get(
        "time"
    )

    if not isinstance(
        hourly_times,
        list,
    ):
        return 0

    return len(
        hourly_times
    )


def _build_raw_envelope(
    point: MonitoringPoint,
    api_response: dict[str, Any],
    batch_id: str,
    extracted_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "batch_id": batch_id,
        "source": "open_meteo",
        "extracted_at": (
            extracted_at.isoformat()
        ),
        "point": {
            "point_id": point.point_id,
            "location_id": (
                point.location_id
            ),
            "point_name": (
                point.point_name
            ),
            "point_type": (
                point.point_type
            ),
            "latitude": point.latitude,
            "longitude": (
                point.longitude
            ),
        },
        "api_response": api_response,
    }


def extract_monitoring_points_to_minio(
    monitoring_points: list[
        MonitoringPoint
    ],
    fetch_air_quality: AirQualityFetcher,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
    batch_id: str | None = None,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    if not monitoring_points:
        raise MinioAirQualityExtractionError(
            "Danh sách monitoring point rỗng."
        )

    if not callable(
        fetch_air_quality
    ):
        raise TypeError(
            "fetch_air_quality phải là callable."
        )

    resolved_settings = (
        settings
        or MinioSettings.from_environment()
    )

    resolved_client = (
        client
        or get_minio_client(
            resolved_settings
        )
    )

    ensure_buckets(
        settings=resolved_settings,
        client=resolved_client,
    )

    resolved_started_at = (
        started_at
        or datetime.now(
            timezone.utc
        )
    )

    if (
        resolved_started_at.tzinfo
        is None
        or resolved_started_at.utcoffset()
        is None
    ):
        raise MinioAirQualityExtractionError(
            "started_at phải có timezone."
        )

    local_started_at = (
        resolved_started_at.astimezone(
            ZoneInfo(
                "Asia/Ho_Chi_Minh"
            )
        )
    )

    resolved_batch_id = (
        batch_id
        or (
            resolved_started_at.strftime(
                "%Y%m%dT%H%M%SZ"
            )
            + "_"
            + uuid4().hex[:8]
        )
    )

    partition_date = (
        local_started_at.strftime(
            "%Y-%m-%d"
        )
    )

    partition_hour = (
        local_started_at.strftime(
            "%H"
        )
    )

    batch_prefix = build_batch_prefix(
        partition_date=partition_date,
        partition_hour=partition_hour,
        batch_id=resolved_batch_id,
    )

    successes: list[
        dict[str, Any]
    ] = []

    failures: list[
        dict[str, Any]
    ] = []

    records_extracted = 0

    for point in monitoring_points:
        point_started_at = (
            datetime.now(
                timezone.utc
            )
        )

        try:
            api_response = (
                fetch_air_quality(
                    point
                )
            )

            if not isinstance(
                api_response,
                dict,
            ):
                raise (
                    MinioAirQualityExtractionError(
                        "Open-Meteo client phải "
                        "trả về dictionary."
                    )
                )

            record_count = (
                _count_hourly_records(
                    api_response
                )
            )

            raw_envelope = (
                _build_raw_envelope(
                    point=point,
                    api_response=(
                        api_response
                    ),
                    batch_id=(
                        resolved_batch_id
                    ),
                    extracted_at=(
                        point_started_at
                    ),
                )
            )

            object_name = (
                build_point_object_name(
                    batch_prefix=(
                        batch_prefix
                    ),
                    point_id=(
                        point.point_id
                    ),
                )
            )

            upload_result = (
                put_json_object(
                    bucket_name=(
                        resolved_settings
                        .raw_bucket
                    ),
                    object_name=(
                        object_name
                    ),
                    data=raw_envelope,
                    settings=(
                        resolved_settings
                    ),
                    client=(
                        resolved_client
                    ),
                )
            )

            records_extracted += (
                record_count
            )

            successes.append(
                {
                    "point_id": (
                        point.point_id
                    ),
                    "location_id": (
                        point.location_id
                    ),
                    "record_count": (
                        record_count
                    ),
                    "bucket_name": (
                        resolved_settings
                        .raw_bucket
                    ),
                    "object_name": (
                        object_name
                    ),
                    "etag": (
                        upload_result[
                            "etag"
                        ]
                    ),
                    "size_bytes": (
                        upload_result[
                            "size_bytes"
                        ]
                    ),
                }
            )

        except Exception as error:
            failures.append(
                {
                    "point_id": (
                        point.point_id
                    ),
                    "location_id": (
                        point.location_id
                    ),
                    "error_type": (
                        type(error).__name__
                    ),
                    "error_message": (
                        str(error)
                    ),
                }
            )

    finished_at = datetime.now(
        timezone.utc
    )

    successful_points = len(
        successes
    )

    failed_points = len(
        failures
    )

    if successful_points == len(
        monitoring_points
    ):
        status = "SUCCESS"
    elif successful_points > 0:
        status = "PARTIAL_SUCCESS"
    else:
        status = "FAILED"

    summary_object_name = (
        build_summary_object_name(
            batch_prefix
        )
    )

    summary = {
        "pipeline_name": (
            "open_meteo_air_quality_extraction"
        ),
        "source": "open_meteo",
        "storage_backend": "minio",
        "status": status,
        "batch_id": (
            resolved_batch_id
        ),
        "partition_date": (
            partition_date
        ),
        "partition_hour": (
            partition_hour
        ),
        "started_at": (
            resolved_started_at
            .isoformat()
        ),
        "finished_at": (
            finished_at.isoformat()
        ),
        "duration_seconds": (
            finished_at
            - resolved_started_at
        ).total_seconds(),
        "active_points": len(
            monitoring_points
        ),
        "successful_points": (
            successful_points
        ),
        "failed_points": (
            failed_points
        ),
        "records_extracted": (
            records_extracted
        ),
        "total_records": (
            records_extracted
        ),
        "raw_bucket": (
            resolved_settings.raw_bucket
        ),
        "batch_prefix": (
            batch_prefix
        ),
        "successes": successes,
        "failures": failures,
        "summary_bucket": (
            resolved_settings.raw_bucket
        ),
        "summary_object_name": (
            summary_object_name
        ),
    }

    try:
        put_json_object(
            bucket_name=(
                resolved_settings
                .raw_bucket
            ),
            object_name=(
                summary_object_name
            ),
            data=summary,
            settings=(
                resolved_settings
            ),
            client=resolved_client,
        )
    except Exception as error:
        raise MinioAirQualityExtractionError(
            "Đã xử lý các monitoring point "
            "nhưng không thể ghi "
            "run_summary.json lên MinIO: "
            f"{error}"
        ) from error

    return summary