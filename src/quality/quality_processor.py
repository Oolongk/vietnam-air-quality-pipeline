from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.quality.data_quality_checks import (
    DataQualityConfigurationError,
    DataQualitySchemaError,
    run_air_quality_data_quality,
)


TRANSFORMED_DATA_FILENAME = (
    "data.parquet"
)

TRANSFORM_SUMMARY_FILENAME = (
    "transform_summary.json"
)

CLEAN_DATA_FILENAME = (
    "data.parquet"
)

BAD_RECORDS_FILENAME = (
    "bad_records.parquet"
)

QUALITY_SUMMARY_FILENAME = (
    "data_quality_summary.json"
)

QUALITY_SNAPSHOT_FILENAME = (
    "quality_snapshot.json"
)

DEFAULT_MONITORING_POINTS_PATH = (
    "configs/monitoring_points.csv"
)

DEFAULT_LOCATIONS_PATH = (
    "configs/locations.csv"
)


class DataQualityProcessingError(
    RuntimeError
):
    """Lỗi khi xử lý Data Quality cho một batch local."""


def _read_json(
    input_path: Path,
) -> dict[str, Any]:
    if not input_path.exists():
        raise DataQualityProcessingError(
            f"Không tìm thấy file: {input_path}"
        )

    try:
        with input_path.open(
            mode="r",
            encoding="utf-8",
        ) as input_file:
            data = json.load(
                input_file
            )
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise DataQualityProcessingError(
            f"Không thể đọc JSON: {input_path}"
        ) from error

    if not isinstance(
        data,
        dict,
    ):
        raise DataQualityProcessingError(
            "Nội dung summary phải là "
            "JSON object."
        )

    return data


def _read_csv(
    input_path: Path,
    config_name: str,
) -> pd.DataFrame:
    if not input_path.exists():
        raise DataQualityProcessingError(
            f"Không tìm thấy {config_name}: "
            f"{input_path}"
        )

    try:
        return pd.read_csv(
            input_path,
            encoding="utf-8-sig",
        )
    except Exception as error:
        raise DataQualityProcessingError(
            f"Không thể đọc {config_name}: "
            f"{input_path}"
        ) from error


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

    return path.resolve()


def _require_summary_string(
    summary: dict[str, Any],
    key: str,
) -> str:
    value = summary.get(
        key
    )

    if not isinstance(
        value,
        str,
    ):
        raise DataQualityProcessingError(
            f"Transform summary thiếu '{key}'."
        )

    cleaned_value = (
        value.strip()
    )

    if not cleaned_value:
        raise DataQualityProcessingError(
            f"Transform summary có '{key}' rỗng."
        )

    return cleaned_value


def _write_json_atomically(
    output_path: Path,
    data: dict[str, Any],
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = (
        output_path.with_name(
            output_path.name
            + ".tmp"
        )
    )

    try:
        with temporary_path.open(
            mode="w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                data,
                output_file,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        temporary_path.replace(
            output_path
        )

    except OSError as error:
        raise DataQualityProcessingError(
            f"Không thể ghi JSON: "
            f"{output_path}"
        ) from error


def _write_parquet_atomically(
    dataframe: pd.DataFrame,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = (
        output_path.with_name(
            output_path.name
            + ".tmp"
        )
    )

    try:
        dataframe.to_parquet(
            temporary_path,
            engine="pyarrow",
            index=False,
            compression="snappy",
        )

        temporary_path.replace(
            output_path
        )

    except (
        OSError,
        ValueError,
        ImportError,
    ) as error:
        raise DataQualityProcessingError(
            f"Không thể ghi Parquet: "
            f"{output_path}"
        ) from error


def _build_partition_directory(
    root: Path,
    partition_date: str,
    partition_hour: str,
    batch_id: str,
) -> Path:
    return (
        root
        / "air_quality"
        / "hourly"
        / f"date={partition_date}"
        / f"hour={partition_hour}"
        / f"batch_id={batch_id}"
    )


def process_transformed_batch_quality(
    transformed_batch_directory: Path,
    clean_root: Path,
    quality_root: Path,
) -> dict[str, Any]:
    transformed_batch_directory = (
        transformed_batch_directory
        .resolve()
    )

    clean_root = (
        clean_root.resolve()
    )

    quality_root = (
        quality_root.resolve()
    )

    transform_summary_path = (
        transformed_batch_directory
        / TRANSFORM_SUMMARY_FILENAME
    )

    transformed_data_path = (
        transformed_batch_directory
        / TRANSFORMED_DATA_FILENAME
    )

    transform_summary = (
        _read_json(
            transform_summary_path
        )
    )

    partition_date = (
        _require_summary_string(
            transform_summary,
            "partition_date",
        )
    )

    partition_hour = (
        _require_summary_string(
            transform_summary,
            "partition_hour",
        )
    )

    batch_id = (
        _require_summary_string(
            transform_summary,
            "batch_id",
        )
    )

    if not transformed_data_path.exists():
        raise DataQualityProcessingError(
            "Không tìm thấy Transformed Parquet: "
            f"{transformed_data_path}"
        )

    try:
        transformed_dataframe = (
            pd.read_parquet(
                transformed_data_path
            )
        )
    except (
        OSError,
        ValueError,
        ImportError,
    ) as error:
        raise DataQualityProcessingError(
            "Không thể đọc Transformed Parquet."
        ) from error

    if transformed_dataframe.empty:
        raise DataQualityProcessingError(
            "Transformed Parquet không có record."
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

    monitoring_points = (
        _read_csv(
            monitoring_points_path,
            "monitoring_points.csv",
        )
    )

    locations = _read_csv(
        locations_path,
        "locations.csv",
    )

    started_at = datetime.now(
        timezone.utc
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
                expected_forecast_hours=int(
                    os.getenv(
                        "DQ_EXPECTED_FORECAST_HOURS",
                        "24",
                    )
                ),
                freshness_minutes=int(
                    os.getenv(
                        "DQ_FRESHNESS_MINUTES",
                        "90",
                    )
                ),
                coordinate_tolerance=float(
                    os.getenv(
                        "DQ_COORDINATE_TOLERANCE",
                        "0.001",
                    )
                ),
                expected_batch_id=(
                    batch_id
                ),
            )
        )

    except (
        DataQualitySchemaError,
        DataQualityConfigurationError,
        ValueError,
    ) as error:
        raise DataQualityProcessingError(
            f"Data Quality lỗi: {error}"
        ) from error

    clean_directory = (
        _build_partition_directory(
            root=clean_root,
            partition_date=(
                partition_date
            ),
            partition_hour=(
                partition_hour
            ),
            batch_id=batch_id,
        )
    )

    quality_directory = (
        _build_partition_directory(
            root=quality_root,
            partition_date=(
                partition_date
            ),
            partition_hour=(
                partition_hour
            ),
            batch_id=batch_id,
        )
    )

    clean_data_path = (
        clean_directory
        / CLEAN_DATA_FILENAME
    )

    bad_records_path = (
        quality_directory
        / BAD_RECORDS_FILENAME
    )

    quality_summary_path = (
        quality_directory
        / QUALITY_SUMMARY_FILENAME
    )

    quality_snapshot_path = (
        quality_directory
        / QUALITY_SNAPSHOT_FILENAME
    )

    clean_relative_path = None
    bad_records_relative_path = None

    if not result.valid_records.empty:
        _write_parquet_atomically(
            dataframe=(
                result.valid_records
            ),
            output_path=(
                clean_data_path
            ),
        )

        clean_relative_path = (
            clean_data_path
            .relative_to(
                clean_root
            )
            .as_posix()
        )

    if not result.bad_records.empty:
        _write_parquet_atomically(
            dataframe=(
                result.bad_records
            ),
            output_path=(
                bad_records_path
            ),
        )

        bad_records_relative_path = (
            bad_records_path
            .relative_to(
                quality_root
            )
            .as_posix()
        )

    finished_at = datetime.now(
        timezone.utc
    )

    valid_percentage = round(
        (
            result.valid_count
            / result.total_records
            * 100
        ),
        2,
    )

    summary = {
        "pipeline_name": (
            "open_meteo_air_quality_data_quality"
        ),
        "stage_name": (
            "data_quality"
        ),
        "source": "open_meteo",
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
        "transform_status": (
            transform_summary.get(
                "status"
            )
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
        "input_records": (
            result.total_records
        ),
        "expected_records": (
            result.expected_records
        ),
        "valid_records": (
            result.valid_count
        ),
        "bad_records": (
            result.bad_count
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
        "clean_data_path": (
            clean_relative_path
        ),
        "bad_records_path": (
            bad_records_relative_path
        ),
        "checks": result.checks,
        "row_checks": (
            result.row_checks
        ),
        "batch_checks": (
            result.batch_checks
        ),
    }

    _write_json_atomically(
        output_path=(
            quality_summary_path
        ),
        data=summary,
    )

    _write_json_atomically(
        output_path=(
            quality_snapshot_path
        ),
        data=summary,
    )

    return summary
