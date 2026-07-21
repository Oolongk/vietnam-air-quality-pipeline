from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from minio import Minio

from src.quality.data_quality_checks import (
    DataQualityConfigurationError,
    DataQualitySchemaError,
    run_air_quality_data_quality,
)
from src.utils.minio_client import (
    MinioSettings,
    ensure_buckets,
    get_minio_client,
)
from src.utils.minio_object_io import (
    delete_object,
    get_json_object,
    get_parquet_object,
    list_object_names,
    object_exists,
    put_json_object,
    put_parquet_object,
)


TRANSFORMED_ROOT_PREFIX = (
    "transformed/air_quality/hourly"
)

CLEAN_ROOT_PREFIX = (
    "clean/air_quality/hourly"
)

QUALITY_ROOT_PREFIX = (
    "quality/air_quality/hourly"
)

QUALITY_SNAPSHOT_HISTORY_ROOT = (
    "data_quality/history"
)

QUALITY_SNAPSHOT_LATEST_OBJECT = (
    "data_quality/latest/"
    "quality_snapshot.json"
)

DEFAULT_MONITORING_POINTS_PATH = (
    "configs/monitoring_points.csv"
)

DEFAULT_LOCATIONS_PATH = (
    "configs/locations.csv"
)


class MinioDataQualityError(
    RuntimeError
):
    """Lỗi khi chạy Data Quality trực tiếp trên MinIO."""


def _require_non_empty_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise MinioDataQualityError(
            f"{field_name} phải là chuỗi."
        )

    cleaned_value = (
        value.strip()
    )

    if not cleaned_value:
        raise MinioDataQualityError(
            f"{field_name} không được rỗng."
        )

    return cleaned_value


def _parse_aware_datetime(
    value: Any,
    field_name: str,
) -> datetime:
    if not isinstance(
        value,
        str,
    ):
        raise MinioDataQualityError(
            f"{field_name} phải là ISO datetime."
        )

    normalized_value = (
        value.strip()
        .replace(
            "Z",
            "+00:00",
        )
    )

    try:
        parsed_value = (
            datetime.fromisoformat(
                normalized_value
            )
        )
    except ValueError as error:
        raise MinioDataQualityError(
            f"{field_name} không hợp lệ: "
            f"{value!r}"
        ) from error

    if (
        parsed_value.tzinfo is None
        or parsed_value.utcoffset()
        is None
    ):
        raise MinioDataQualityError(
            f"{field_name} phải có timezone."
        )

    return parsed_value


def _parse_positive_integer_environment(
    name: str,
    default: int,
) -> int:
    raw_value = os.getenv(
        name
    )

    if raw_value is None:
        return default

    try:
        value = int(
            raw_value.strip()
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise MinioDataQualityError(
            f"{name} phải là số nguyên."
        ) from error

    if value <= 0:
        raise MinioDataQualityError(
            f"{name} phải lớn hơn 0."
        )

    return value


def _parse_non_negative_float_environment(
    name: str,
    default: float,
) -> float:
    raw_value = os.getenv(
        name
    )

    if raw_value is None:
        return default

    try:
        value = float(
            raw_value.strip()
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise MinioDataQualityError(
            f"{name} phải là số."
        ) from error

    if value < 0:
        raise MinioDataQualityError(
            f"{name} không được âm."
        )

    return value


def _resolve_config_path(
    environment_name: str,
    default_path: str,
) -> Path:
    configured_path = os.getenv(
        environment_name,
        default_path,
    )

    path = Path(
        configured_path
    )

    if not path.is_absolute():
        path = (
            Path.cwd()
            / path
        )

    resolved_path = (
        path.resolve()
    )

    if not resolved_path.exists():
        raise MinioDataQualityError(
            f"Không tìm thấy file cấu hình: "
            f"{resolved_path}"
        )

    if not resolved_path.is_file():
        raise MinioDataQualityError(
            f"Đường dẫn cấu hình không phải file: "
            f"{resolved_path}"
        )

    return resolved_path


def _read_csv_config(
    path: Path,
    config_name: str,
) -> pd.DataFrame:
    try:
        return pd.read_csv(
            path,
            encoding="utf-8-sig",
        )
    except Exception as error:
        raise MinioDataQualityError(
            f"Không đọc được {config_name}: "
            f"{path}. Chi tiết: {error}"
        ) from error


def _parse_summary_timestamp(
    summary: Mapping[str, Any],
) -> datetime:
    timestamp_value = (
        summary.get(
            "finished_at"
        )
        or summary.get(
            "started_at"
        )
    )

    return _parse_aware_datetime(
        timestamp_value,
        "summary timestamp",
    )


def build_clean_prefix(
    partition_date: str,
    partition_hour: str,
    batch_id: str,
) -> str:
    return (
        f"{CLEAN_ROOT_PREFIX}/"
        f"date={partition_date}/"
        f"hour={partition_hour}/"
        f"batch_id={batch_id}"
    )


def build_quality_prefix(
    partition_date: str,
    partition_hour: str,
    batch_id: str,
) -> str:
    return (
        f"{QUALITY_ROOT_PREFIX}/"
        f"date={partition_date}/"
        f"hour={partition_hour}/"
        f"batch_id={batch_id}"
    )


def build_quality_snapshot_prefix(
    partition_date: str,
    partition_hour: str,
    batch_id: str,
) -> str:
    return (
        f"{QUALITY_SNAPSHOT_HISTORY_ROOT}/"
        f"date={partition_date}/"
        f"hour={partition_hour}/"
        f"batch_id={batch_id}"
    )


def find_latest_quality_candidate(
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> tuple[
    str,
    dict[str, Any],
]:
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

    summary_object_names = [
        object_name
        for object_name in list_object_names(
            bucket_name=(
                resolved_settings
                .clean_bucket
            ),
            prefix=(
                TRANSFORMED_ROOT_PREFIX
            ),
            recursive=True,
            settings=(
                resolved_settings
            ),
            client=(
                resolved_client
            ),
        )
        if object_name.endswith(
            "/transform_summary.json"
        )
    ]

    if not summary_object_names:
        raise MinioDataQualityError(
            "Không tìm thấy "
            "transform_summary.json "
            "trong Clean bucket."
        )

    candidates: list[
        tuple[
            datetime,
            str,
            dict[str, Any],
        ]
    ] = []

    for object_name in (
        summary_object_names
    ):
        try:
            summary = (
                get_json_object(
                    bucket_name=(
                        resolved_settings
                        .clean_bucket
                    ),
                    object_name=(
                        object_name
                    ),
                    settings=(
                        resolved_settings
                    ),
                    client=(
                        resolved_client
                    ),
                )
            )

            if not isinstance(
                summary,
                dict,
            ):
                continue

            status = str(
                summary.get(
                    "status",
                    "",
                )
            ).strip().upper()

            if status not in {
                "SUCCESS",
                "PARTIAL_SUCCESS",
            }:
                continue

            transformed_object_name = (
                summary.get(
                    "transformed_object_name"
                )
            )

            if (
                not isinstance(
                    transformed_object_name,
                    str,
                )
                or not transformed_object_name
                .strip()
            ):
                continue

            try:
                records_transformed = int(
                    summary.get(
                        "records_transformed",
                        0,
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if records_transformed <= 0:
                continue

            candidates.append(
                (
                    _parse_summary_timestamp(
                        summary
                    ),
                    object_name,
                    summary,
                )
            )

        except Exception:
            continue

    if not candidates:
        raise MinioDataQualityError(
            "Không tìm thấy Transform batch "
            "SUCCESS hoặc PARTIAL_SUCCESS "
            "có Parquet hợp lệ."
        )

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    (
        _,
        latest_summary_object_name,
        latest_summary,
    ) = candidates[0]

    return (
        latest_summary_object_name,
        latest_summary,
    )


def find_latest_loadable_quality_batch(
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> tuple[
    str,
    dict[str, Any],
]:
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

    summary_object_names = [
        object_name
        for object_name in list_object_names(
            bucket_name=(
                resolved_settings
                .clean_bucket
            ),
            prefix=(
                QUALITY_ROOT_PREFIX
            ),
            recursive=True,
            settings=(
                resolved_settings
            ),
            client=(
                resolved_client
            ),
        )
        if object_name.endswith(
            "/data_quality_summary.json"
        )
    ]

    candidates: list[
        tuple[
            datetime,
            str,
            dict[str, Any],
        ]
    ] = []

    for object_name in (
        summary_object_names
    ):
        try:
            summary = (
                get_json_object(
                    bucket_name=(
                        resolved_settings
                        .clean_bucket
                    ),
                    object_name=(
                        object_name
                    ),
                    settings=(
                        resolved_settings
                    ),
                    client=(
                        resolved_client
                    ),
                )
            )

            if not isinstance(
                summary,
                dict,
            ):
                continue

            status = str(
                summary.get(
                    "status",
                    "",
                )
            ).strip().upper()

            if status not in {
                "SUCCESS",
                "PARTIAL_SUCCESS",
            }:
                continue

            clean_object_name = (
                summary.get(
                    "clean_object_name"
                )
            )

            if (
                not isinstance(
                    clean_object_name,
                    str,
                )
                or not clean_object_name
                .strip()
            ):
                continue

            if int(
                summary.get(
                    "valid_records",
                    0,
                )
            ) <= 0:
                continue

            candidates.append(
                (
                    _parse_summary_timestamp(
                        summary
                    ),
                    object_name,
                    summary,
                )
            )

        except Exception:
            continue

    if not candidates:
        raise MinioDataQualityError(
            "Không tìm thấy Data Quality batch "
            "có Clean Parquet hợp lệ."
        )

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    (
        _,
        latest_object_name,
        latest_summary,
    ) = candidates[0]

    return (
        latest_object_name,
        latest_summary,
    )


def process_transformed_batch_on_minio(
    transform_summary: Mapping[
        str,
        Any,
    ],
    transform_summary_object_name: str,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> dict[str, Any]:
    if not isinstance(
        transform_summary,
        Mapping,
    ):
        raise MinioDataQualityError(
            "Transform summary phải là "
            "JSON object."
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

    batch_id = _require_non_empty_string(
        transform_summary.get(
            "batch_id"
        ),
        "batch_id",
    )

    partition_date = (
        _require_non_empty_string(
            transform_summary.get(
                "partition_date"
            ),
            "partition_date",
        )
    )

    partition_hour = (
        _require_non_empty_string(
            transform_summary.get(
                "partition_hour"
            ),
            "partition_hour",
        )
    )

    transformed_object_name = (
        _require_non_empty_string(
            transform_summary.get(
                "transformed_object_name"
            ),
            "transformed_object_name",
        )
    )

    monitoring_points_path = (
        _resolve_config_path(
            "MONITORING_POINTS_CONFIG_PATH",
            DEFAULT_MONITORING_POINTS_PATH,
        )
    )

    locations_path = (
        _resolve_config_path(
            "LOCATIONS_CONFIG_PATH",
            DEFAULT_LOCATIONS_PATH,
        )
    )

    expected_forecast_hours = (
        _parse_positive_integer_environment(
            "DQ_EXPECTED_FORECAST_HOURS",
            24,
        )
    )

    freshness_minutes = (
        _parse_positive_integer_environment(
            "DQ_FRESHNESS_MINUTES",
            90,
        )
    )

    coordinate_tolerance = (
        _parse_non_negative_float_environment(
            "DQ_COORDINATE_TOLERANCE",
            0.001,
        )
    )

    started_at = datetime.now(
        timezone.utc
    )

    transformed_dataframe = (
        get_parquet_object(
            bucket_name=(
                resolved_settings
                .clean_bucket
            ),
            object_name=(
                transformed_object_name
            ),
            settings=(
                resolved_settings
            ),
            client=(
                resolved_client
            ),
        )
    )

    monitoring_points = (
        _read_csv_config(
            monitoring_points_path,
            "monitoring_points.csv",
        )
    )

    locations = _read_csv_config(
        locations_path,
        "locations.csv",
    )

    try:
        result = (
            run_air_quality_data_quality(
                dataframe=(
                    transformed_dataframe
                ),
                monitoring_points=(
                    monitoring_points
                ),
                locations=locations,
                expected_forecast_hours=(
                    expected_forecast_hours
                ),
                freshness_minutes=(
                    freshness_minutes
                ),
                coordinate_tolerance=(
                    coordinate_tolerance
                ),
                expected_batch_id=(
                    batch_id
                ),
            )
        )
    except (
        DataQualitySchemaError,
        DataQualityConfigurationError,
    ) as error:
        raise MinioDataQualityError(
            f"Data Quality không thể chạy: "
            f"{error}"
        ) from error

    input_records = (
        result.total_records
    )

    valid_records = (
        result.valid_count
    )

    bad_records = (
        result.bad_count
    )

    valid_percentage = round(
        (
            valid_records
            / input_records
            * 100
        ),
        2,
    )

    clean_prefix = (
        build_clean_prefix(
            partition_date=(
                partition_date
            ),
            partition_hour=(
                partition_hour
            ),
            batch_id=batch_id,
        )
    )

    quality_prefix = (
        build_quality_prefix(
            partition_date=(
                partition_date
            ),
            partition_hour=(
                partition_hour
            ),
            batch_id=batch_id,
        )
    )

    snapshot_prefix = (
        build_quality_snapshot_prefix(
            partition_date=(
                partition_date
            ),
            partition_hour=(
                partition_hour
            ),
            batch_id=batch_id,
        )
    )

    clean_object_name = (
        f"{clean_prefix}/"
        "data.parquet"
    )

    bad_records_object_name = (
        f"{quality_prefix}/"
        "bad_records.parquet"
    )

    summary_object_name = (
        f"{quality_prefix}/"
        "data_quality_summary.json"
    )

    snapshot_history_object_name = (
        f"{snapshot_prefix}/"
        "quality_snapshot.json"
    )

    clean_upload_result = None
    bad_upload_result = None

    if valid_records > 0:
        clean_upload_result = (
            put_parquet_object(
                bucket_name=(
                    resolved_settings
                    .clean_bucket
                ),
                object_name=(
                    clean_object_name
                ),
                dataframe=(
                    result.valid_records
                ),
                settings=(
                    resolved_settings
                ),
                client=(
                    resolved_client
                ),
            )
        )

    elif object_exists(
        bucket_name=(
            resolved_settings
            .clean_bucket
        ),
        object_name=(
            clean_object_name
        ),
        settings=(
            resolved_settings
        ),
        client=(
            resolved_client
        ),
    ):
        delete_object(
            bucket_name=(
                resolved_settings
                .clean_bucket
            ),
            object_name=(
                clean_object_name
            ),
            settings=(
                resolved_settings
            ),
            client=(
                resolved_client
            ),
        )

    if bad_records > 0:
        bad_upload_result = (
            put_parquet_object(
                bucket_name=(
                    resolved_settings
                    .clean_bucket
                ),
                object_name=(
                    bad_records_object_name
                ),
                dataframe=(
                    result.bad_records
                ),
                settings=(
                    resolved_settings
                ),
                client=(
                    resolved_client
                ),
            )
        )

    elif object_exists(
        bucket_name=(
            resolved_settings
            .clean_bucket
        ),
        object_name=(
            bad_records_object_name
        ),
        settings=(
            resolved_settings
        ),
        client=(
            resolved_client
        ),
    ):
        delete_object(
            bucket_name=(
                resolved_settings
                .clean_bucket
            ),
            object_name=(
                bad_records_object_name
            ),
            settings=(
                resolved_settings
            ),
            client=(
                resolved_client
            ),
        )

    finished_at = datetime.now(
        timezone.utc
    )

    snapshot = {
        "snapshot_schema_version": "1.0",
        "pipeline_name": (
            "open_meteo_air_quality_data_quality"
        ),
        "stage_name": "data_quality",
        "source": "open_meteo",
        "storage_backend": "minio",
        "status": (
            result.pipeline_status
        ),
        "quality_status": (
            result.quality_status
        ),
        "quality_score": (
            result.quality_score
        ),
        "batch_id": batch_id,
        "partition_date": (
            partition_date
        ),
        "partition_hour": (
            partition_hour
        ),
        "generated_at": (
            finished_at.isoformat()
        ),
        "checked_at": (
            result.checked_at
        ),
        "input_records": (
            input_records
        ),
        "expected_records": (
            result.expected_records
        ),
        "valid_records": (
            valid_records
        ),
        "bad_records": (
            bad_records
        ),
        "valid_percentage": (
            valid_percentage
        ),
        "expected_active_points": (
            result.expected_active_points
        ),
        "actual_active_points": (
            result.actual_active_points
        ),
        "expected_forecast_hours": (
            result.expected_forecast_hours
        ),
        "passed_checks": (
            result.passed_check_count
        ),
        "warning_checks": (
            result.warning_check_count
        ),
        "failed_checks": (
            result.failed_check_count
        ),
        "total_checks": len(
            result.checks
        ),
        "row_checks": (
            result.row_checks
        ),
        "batch_checks": (
            result.batch_checks
        ),
        "summary_bucket": (
            resolved_settings
            .clean_bucket
        ),
        "summary_object_name": (
            summary_object_name
        ),
        "clean_bucket": (
            resolved_settings
            .clean_bucket
        ),
        "clean_object_name": (
            clean_object_name
            if clean_upload_result
            is not None
            else None
        ),
        "bad_records_object_name": (
            bad_records_object_name
            if bad_upload_result
            is not None
            else None
        ),
        "history_snapshot_bucket": (
            resolved_settings
            .mart_bucket
        ),
        "history_snapshot_object_name": (
            snapshot_history_object_name
        ),
        "latest_snapshot_bucket": (
            resolved_settings
            .mart_bucket
        ),
        "latest_snapshot_object_name": (
            QUALITY_SNAPSHOT_LATEST_OBJECT
        ),
    }

    put_json_object(
        bucket_name=(
            resolved_settings
            .mart_bucket
        ),
        object_name=(
            snapshot_history_object_name
        ),
        data=snapshot,
        settings=(
            resolved_settings
        ),
        client=(
            resolved_client
        ),
    )

    put_json_object(
        bucket_name=(
            resolved_settings
            .mart_bucket
        ),
        object_name=(
            QUALITY_SNAPSHOT_LATEST_OBJECT
        ),
        data=snapshot,
        settings=(
            resolved_settings
        ),
        client=(
            resolved_client
        ),
    )

    summary = {
        "pipeline_name": (
            "open_meteo_air_quality_data_quality"
        ),
        "stage_name": "data_quality",
        "source": "open_meteo",
        "storage_backend": "minio",
        "status": (
            result.pipeline_status
        ),
        "quality_status": (
            result.quality_status
        ),
        "quality_score": (
            result.quality_score
        ),
        "batch_id": batch_id,
        "partition_date": (
            partition_date
        ),
        "partition_hour": (
            partition_hour
        ),
        "started_at": (
            started_at.isoformat()
        ),
        "finished_at": (
            finished_at.isoformat()
        ),
        "duration_seconds": (
            finished_at
            - started_at
        ).total_seconds(),
        "checked_at": (
            result.checked_at
        ),
        "transform_bucket": (
            resolved_settings
            .clean_bucket
        ),
        "transform_summary_object_name": (
            transform_summary_object_name
        ),
        "transformed_object_name": (
            transformed_object_name
        ),
        "input_records": (
            input_records
        ),
        "expected_records": (
            result.expected_records
        ),
        "valid_records": (
            valid_records
        ),
        "bad_records": (
            bad_records
        ),
        "valid_percentage": (
            valid_percentage
        ),
        "expected_active_points": (
            result.expected_active_points
        ),
        "actual_active_points": (
            result.actual_active_points
        ),
        "expected_forecast_hours": (
            result.expected_forecast_hours
        ),
        "passed_checks": (
            result.passed_check_count
        ),
        "warning_checks": (
            result.warning_check_count
        ),
        "failed_checks": (
            result.failed_check_count
        ),
        "checks": result.checks,
        "row_checks": (
            result.row_checks
        ),
        "batch_checks": (
            result.batch_checks
        ),
        "clean_bucket": (
            resolved_settings
            .clean_bucket
        ),
        "clean_object_name": (
            clean_object_name
            if clean_upload_result
            is not None
            else None
        ),
        "clean_size_bytes": (
            clean_upload_result[
                "size_bytes"
            ]
            if clean_upload_result
            is not None
            else 0
        ),
        "bad_records_bucket": (
            resolved_settings
            .clean_bucket
        ),
        "bad_records_object_name": (
            bad_records_object_name
            if bad_upload_result
            is not None
            else None
        ),
        "bad_records_size_bytes": (
            bad_upload_result[
                "size_bytes"
            ]
            if bad_upload_result
            is not None
            else 0
        ),
        "summary_bucket": (
            resolved_settings
            .clean_bucket
        ),
        "summary_object_name": (
            summary_object_name
        ),
        "quality_snapshot_bucket": (
            resolved_settings
            .mart_bucket
        ),
        "quality_snapshot_object_name": (
            snapshot_history_object_name
        ),
        "latest_quality_snapshot_object_name": (
            QUALITY_SNAPSHOT_LATEST_OBJECT
        ),
        "monitoring_points_config_path": (
            str(
                monitoring_points_path
            )
        ),
        "locations_config_path": (
            str(
                locations_path
            )
        ),
    }

    put_json_object(
        bucket_name=(
            resolved_settings
            .clean_bucket
        ),
        object_name=(
            summary_object_name
        ),
        data=summary,
        settings=(
            resolved_settings
        ),
        client=(
            resolved_client
        ),
    )

    return summary
