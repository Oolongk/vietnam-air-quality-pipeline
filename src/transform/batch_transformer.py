from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.transform.air_quality_transform import (
    AirQualityTransformError,
    transform_open_meteo_payload,
)


RAW_SUMMARY_FILENAME = "run_summary.json"
RAW_DATA_FILENAME = "data.json"

TRANSFORMED_DATA_FILENAME = "data.parquet"
TRANSFORM_SUMMARY_FILENAME = "transform_summary.json"

DUPLICATE_KEY_COLUMNS: tuple[str, ...] = (
    "point_id",
    "forecast_time",
    "source",
)


class BatchTransformError(RuntimeError):
    """Lỗi xảy ra khi transform toàn bộ một Raw batch."""


def _read_json(
    input_path: Path,
) -> dict[str, Any]:
    if not input_path.exists():
        raise BatchTransformError(
            f"Không tìm thấy file JSON: {input_path}"
        )

    if not input_path.is_file():
        raise BatchTransformError(
            f"Đường dẫn không phải file: {input_path}"
        )

    try:
        with input_path.open(
            mode="r",
            encoding="utf-8",
        ) as input_file:
            data = json.load(input_file)
    except json.JSONDecodeError as error:
        raise BatchTransformError(
            f"File JSON không hợp lệ: {input_path}"
        ) from error
    except OSError as error:
        raise BatchTransformError(
            f"Không thể đọc file: {input_path}"
        ) from error

    if not isinstance(data, dict):
        raise BatchTransformError(
            f"Nội dung JSON phải là object: {input_path}"
        )

    return data


def _write_json_atomically(
    output_path: Path,
    data: dict[str, Any],
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = output_path.with_name(
        output_path.name + ".tmp"
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
            )

        temporary_path.replace(output_path)
    except OSError as error:
        raise BatchTransformError(
            f"Không thể ghi file JSON: {output_path}"
        ) from error


def _write_parquet_atomically(
    dataframe: pd.DataFrame,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = output_path.with_name(
        output_path.name + ".tmp"
    )

    try:
        dataframe.to_parquet(
            temporary_path,
            engine="pyarrow",
            index=False,
            compression="snappy",
        )

        temporary_path.replace(output_path)
    except (
        OSError,
        ValueError,
        ImportError,
    ) as error:
        raise BatchTransformError(
            f"Không thể ghi file Parquet: {output_path}"
        ) from error


def _require_summary_string(
    summary: dict[str, Any],
    key: str,
) -> str:
    value = summary.get(key)

    if not isinstance(value, str):
        raise BatchTransformError(
            f"run_summary.json thiếu chuỗi '{key}'."
        )

    cleaned_value = value.strip()

    if not cleaned_value:
        raise BatchTransformError(
            f"run_summary.json có '{key}' bị rỗng."
        )

    return cleaned_value


def _build_transformed_directory(
    transformed_root: Path,
    partition_date: str,
    partition_hour: str,
    batch_id: str,
) -> Path:
    return (
        transformed_root
        / "air_quality"
        / "hourly"
        / f"date={partition_date}"
        / f"hour={partition_hour}"
        / f"batch_id={batch_id}"
    )


def transform_raw_batch(
    raw_batch_directory: Path,
    transformed_root: Path,
) -> dict[str, Any]:
    raw_batch_directory = (
        raw_batch_directory.resolve()
    )

    transformed_root = transformed_root.resolve()

    if not raw_batch_directory.exists():
        raise BatchTransformError(
            "Không tìm thấy Raw batch directory: "
            f"{raw_batch_directory}"
        )

    if not raw_batch_directory.is_dir():
        raise BatchTransformError(
            "Raw batch path không phải thư mục: "
            f"{raw_batch_directory}"
        )

    raw_summary_path = (
        raw_batch_directory
        / RAW_SUMMARY_FILENAME
    )

    raw_summary = _read_json(
        raw_summary_path
    )

    partition_date = _require_summary_string(
        raw_summary,
        "partition_date",
    )

    partition_hour = _require_summary_string(
        raw_summary,
        "partition_hour",
    )

    batch_id = _require_summary_string(
        raw_summary,
        "batch_id",
    )

    transformed_directory = (
        _build_transformed_directory(
            transformed_root=transformed_root,
            partition_date=partition_date,
            partition_hour=partition_hour,
            batch_id=batch_id,
        )
    )

    transformed_data_path = (
        transformed_directory
        / TRANSFORMED_DATA_FILENAME
    )

    transform_summary_path = (
        transformed_directory
        / TRANSFORM_SUMMARY_FILENAME
    )

    raw_files = sorted(
        raw_batch_directory.glob(
            f"point_id=*/{RAW_DATA_FILENAME}"
        )
    )

    if not raw_files:
        raise BatchTransformError(
            "Raw batch không có file "
            "'point_id=*/data.json'."
        )

    started_at = datetime.now(
        timezone.utc
    )

    transformed_frames: list[pd.DataFrame] = []
    successes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for raw_file in raw_files:
        try:
            raw_payload = _read_json(
                raw_file
            )

            point_dataframe = (
                transform_open_meteo_payload(
                    raw_payload
                )
            )

            point_id = str(
                point_dataframe[
                    "point_id"
                ].iloc[0]
            )

            location_id = str(
                point_dataframe[
                    "location_id"
                ].iloc[0]
            )

            transformed_frames.append(
                point_dataframe
            )

            successes.append(
                {
                    "point_id": point_id,
                    "location_id": location_id,
                    "records_transformed": len(
                        point_dataframe
                    ),
                    "raw_path": (
                        raw_file
                        .relative_to(
                            raw_batch_directory
                        )
                        .as_posix()
                    ),
                }
            )
        except (
            BatchTransformError,
            AirQualityTransformError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as error:
            failures.append(
                {
                    "raw_path": (
                        raw_file
                        .relative_to(
                            raw_batch_directory
                        )
                        .as_posix()
                    ),
                    "error_type": (
                        type(error).__name__
                    ),
                    "error_message": str(error),
                }
            )

    combined_dataframe: (
        pd.DataFrame | None
    ) = None

    duplicate_key_rows = 0

    if transformed_frames:
        combined_dataframe = pd.concat(
            transformed_frames,
            ignore_index=True,
        )

        combined_dataframe = (
            combined_dataframe
            .sort_values(
                by=[
                    "point_id",
                    "forecast_time",
                ],
                ascending=True,
            )
            .reset_index(drop=True)
        )

        duplicate_mask = (
            combined_dataframe
            .duplicated(
                subset=list(
                    DUPLICATE_KEY_COLUMNS
                ),
                keep=False,
            )
        )

        duplicate_key_rows = int(
            duplicate_mask.sum()
        )

        _write_parquet_atomically(
            dataframe=combined_dataframe,
            output_path=transformed_data_path,
        )

    finished_at = datetime.now(
        timezone.utc
    )

    succeeded_files = len(successes)
    failed_files = len(failures)

    if failed_files == 0:
        status = "SUCCESS"
    elif succeeded_files == 0:
        status = "FAILED"
    else:
        status = "PARTIAL_SUCCESS"

    expected_raw_files = raw_summary.get(
        "succeeded_points"
    )

    records_transformed = (
        len(combined_dataframe)
        if combined_dataframe is not None
        else 0
    )

    transformed_relative_path = None

    if combined_dataframe is not None:
        transformed_relative_path = (
            transformed_data_path
            .relative_to(transformed_root)
            .as_posix()
        )

    summary = {
        "pipeline_name": (
            "open_meteo_air_quality_transform"
        ),
        "source": "open_meteo",
        "status": status,
        "batch_id": batch_id,
        "partition_date": partition_date,
        "partition_hour": partition_hour,
        "raw_batch_status": raw_summary.get(
            "status"
        ),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (
            finished_at - started_at
        ).total_seconds(),
        "expected_raw_files": expected_raw_files,
        "discovered_raw_files": len(
            raw_files
        ),
        "succeeded_files": succeeded_files,
        "failed_files": failed_files,
        "records_transformed": (
            records_transformed
        ),
        "duplicate_key_rows": (
            duplicate_key_rows
        ),
        "duplicate_key_columns": list(
            DUPLICATE_KEY_COLUMNS
        ),
        "transformed_data_path": (
            transformed_relative_path
        ),
        "successes": successes,
        "failures": failures,
    }

    _write_json_atomically(
        output_path=transform_summary_path,
        data=summary,
    )

    return summary