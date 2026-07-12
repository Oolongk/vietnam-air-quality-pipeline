from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg

from src.utils.db import (
    get_database_connection,
)


LOAD_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "point_id",
    "location_id",
    "forecast_time",
    "latitude",
    "longitude",
    "grid_latitude",
    "grid_longitude",
    "pm2_5",
    "pm10",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
    "us_aqi",
    "us_aqi_pm2_5",
    "us_aqi_pm10",
    "timezone",
    "utc_offset_seconds",
    "source",
    "ingested_at",
)

UNIQUE_KEY_COLUMNS: tuple[str, ...] = (
    "point_id",
    "forecast_time",
    "source",
)

DATETIME_COLUMNS: tuple[str, ...] = (
    "forecast_time",
    "ingested_at",
)

UPSERT_SQL = """
    INSERT INTO fact_air_quality_hourly (
        schema_version,
        point_id,
        location_id,
        forecast_time,
        latitude,
        longitude,
        grid_latitude,
        grid_longitude,
        pm2_5,
        pm10,
        carbon_monoxide,
        nitrogen_dioxide,
        sulphur_dioxide,
        ozone,
        us_aqi,
        us_aqi_pm2_5,
        us_aqi_pm10,
        timezone,
        utc_offset_seconds,
        source,
        ingested_at
    )
    VALUES (
        %(schema_version)s,
        %(point_id)s,
        %(location_id)s,
        %(forecast_time)s,
        %(latitude)s,
        %(longitude)s,
        %(grid_latitude)s,
        %(grid_longitude)s,
        %(pm2_5)s,
        %(pm10)s,
        %(carbon_monoxide)s,
        %(nitrogen_dioxide)s,
        %(sulphur_dioxide)s,
        %(ozone)s,
        %(us_aqi)s,
        %(us_aqi_pm2_5)s,
        %(us_aqi_pm10)s,
        %(timezone)s,
        %(utc_offset_seconds)s,
        %(source)s,
        %(ingested_at)s
    )
    ON CONFLICT (
        point_id,
        forecast_time,
        source
    )
    DO UPDATE SET
        schema_version =
            EXCLUDED.schema_version,

        location_id =
            EXCLUDED.location_id,

        latitude =
            EXCLUDED.latitude,

        longitude =
            EXCLUDED.longitude,

        grid_latitude =
            EXCLUDED.grid_latitude,

        grid_longitude =
            EXCLUDED.grid_longitude,

        pm2_5 =
            EXCLUDED.pm2_5,

        pm10 =
            EXCLUDED.pm10,

        carbon_monoxide =
            EXCLUDED.carbon_monoxide,

        nitrogen_dioxide =
            EXCLUDED.nitrogen_dioxide,

        sulphur_dioxide =
            EXCLUDED.sulphur_dioxide,

        ozone =
            EXCLUDED.ozone,

        us_aqi =
            EXCLUDED.us_aqi,

        us_aqi_pm2_5 =
            EXCLUDED.us_aqi_pm2_5,

        us_aqi_pm10 =
            EXCLUDED.us_aqi_pm10,

        timezone =
            EXCLUDED.timezone,

        utc_offset_seconds =
            EXCLUDED.utc_offset_seconds,

        ingested_at =
            EXCLUDED.ingested_at;
"""


class TimescaleDBLoadError(RuntimeError):
    """Lỗi khi load Clean data vào TimescaleDB."""


def _blank_string_mask(
    series: pd.Series,
) -> pd.Series:
    string_values = series.astype(
        "string"
    )

    return (
        string_values.isna()
        | string_values
        .str.strip()
        .eq("")
        .fillna(True)
    )


def _validate_datetime_timezone(
    dataframe: pd.DataFrame,
    column: str,
) -> None:
    for row_index, value in (
        dataframe[column].items()
    ):
        if value is None or pd.isna(value):
            raise TimescaleDBLoadError(
                f"{column} bị thiếu tại "
                f"row index {row_index}."
            )

        try:
            timestamp = pd.Timestamp(value)
        except (
            TypeError,
            ValueError,
        ) as error:
            raise TimescaleDBLoadError(
                f"{column} không hợp lệ tại "
                f"row index {row_index}."
            ) from error

        if (
            timestamp.tzinfo is None
            or timestamp.utcoffset() is None
        ):
            raise TimescaleDBLoadError(
                f"{column} phải có timezone tại "
                f"row index {row_index}."
            )


def _validate_load_dataframe(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    if not isinstance(
        dataframe,
        pd.DataFrame,
    ):
        raise TypeError(
            "dataframe phải là Pandas DataFrame."
        )

    if dataframe.empty:
        raise TimescaleDBLoadError(
            "Clean DataFrame không có record."
        )

    missing_columns = (
        set(LOAD_COLUMNS)
        - set(dataframe.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise TimescaleDBLoadError(
            "Clean DataFrame thiếu các cột: "
            f"{missing_text}"
        )

    working_dataframe = (
        dataframe
        .loc[:, list(LOAD_COLUMNS)]
        .copy()
        .reset_index(drop=True)
    )

    point_id_invalid = _blank_string_mask(
        working_dataframe["point_id"]
    )

    if point_id_invalid.any():
        raise TimescaleDBLoadError(
            "Clean DataFrame có point_id rỗng."
        )

    location_id_invalid = (
        _blank_string_mask(
            working_dataframe[
                "location_id"
            ]
        )
    )

    if location_id_invalid.any():
        raise TimescaleDBLoadError(
            "Clean DataFrame có location_id rỗng."
        )

    source_values = (
        working_dataframe["source"]
        .astype("string")
        .str.strip()
    )

    invalid_source = (
        source_values.isna()
        | source_values.ne("open_meteo")
    )

    if invalid_source.any():
        raise TimescaleDBLoadError(
            "Tất cả source phải là "
            "'open_meteo'."
        )

    duplicate_mask = (
        working_dataframe
        .duplicated(
            subset=list(
                UNIQUE_KEY_COLUMNS
            ),
            keep=False,
        )
    )

    if duplicate_mask.any():
        duplicate_count = int(
            duplicate_mask.sum()
        )

        raise TimescaleDBLoadError(
            "Clean DataFrame vẫn có "
            f"{duplicate_count} dòng thuộc "
            "nhóm duplicate."
        )

    for column in DATETIME_COLUMNS:
        _validate_datetime_timezone(
            dataframe=working_dataframe,
            column=column,
        )

    return working_dataframe


def _to_python_value(
    value: Any,
) -> Any:
    if value is None or value is pd.NA:
        return None

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()

    if isinstance(value, datetime):
        return value

    try:
        if bool(pd.isna(value)):
            return None
    except (
        TypeError,
        ValueError,
    ):
        pass

    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            pass

    return value


def prepare_air_quality_records(
    dataframe: pd.DataFrame,
) -> list[dict[str, Any]]:
    working_dataframe = (
        _validate_load_dataframe(
            dataframe
        )
    )

    records: list[dict[str, Any]] = []

    for row in working_dataframe.to_dict(
        orient="records"
    ):
        prepared_record = {
            column: _to_python_value(
                row[column]
            )
            for column in LOAD_COLUMNS
        }

        records.append(
            prepared_record
        )

    return records


def _extract_row_value(
    row: Any,
    key: str,
    position: int,
) -> Any:
    if isinstance(row, dict):
        return row[key]

    return row[position]


def _count_fact_records(
    cursor: Any,
) -> int:
    cursor.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM fact_air_quality_hourly;
        """
    )

    row = cursor.fetchone()

    if row is None:
        raise TimescaleDBLoadError(
            "Không đọc được số record "
            "trong fact_air_quality_hourly."
        )

    return int(
        _extract_row_value(
            row=row,
            key="row_count",
            position=0,
        )
    )


def _validate_dimension_references(
    cursor: Any,
    records: list[dict[str, Any]],
) -> None:
    required_pairs = {
        (
            str(record["point_id"]),
            str(record["location_id"]),
        )
        for record in records
    }

    cursor.execute(
        """
        SELECT
            point_id,
            location_id
        FROM dim_monitoring_point;
        """
    )

    database_rows = cursor.fetchall()

    database_pairs = {
        (
            str(
                _extract_row_value(
                    row=row,
                    key="point_id",
                    position=0,
                )
            ),
            str(
                _extract_row_value(
                    row=row,
                    key="location_id",
                    position=1,
                )
            ),
        )
        for row in database_rows
    }

    missing_pairs = (
        required_pairs
        - database_pairs
    )

    if missing_pairs:
        missing_text = ", ".join(
            f"{point_id}/{location_id}"
            for point_id, location_id
            in sorted(missing_pairs)
        )

        raise TimescaleDBLoadError(
            "Các cặp point_id/location_id "
            "chưa tồn tại trong "
            "dim_monitoring_point: "
            f"{missing_text}"
        )


def load_air_quality_dataframe(
    dataframe: pd.DataFrame,
    connection: Any | None = None,
) -> dict[str, int]:
    records = prepare_air_quality_records(
        dataframe
    )

    owns_connection = connection is None

    resolved_connection = (
        connection
        or get_database_connection()
    )

    try:
        with resolved_connection.transaction():
            with resolved_connection.cursor() as cursor:
                _validate_dimension_references(
                    cursor=cursor,
                    records=records,
                )

                records_before = (
                    _count_fact_records(
                        cursor
                    )
                )

                cursor.executemany(
                    UPSERT_SQL,
                    records,
                )

                records_after = (
                    _count_fact_records(
                        cursor
                    )
                )
    except psycopg.Error as error:
        raise TimescaleDBLoadError(
            "TimescaleDB từ chối batch load: "
            f"{error}"
        ) from error
    finally:
        if owns_connection:
            resolved_connection.close()

    inserted_records = (
        records_after
        - records_before
    )

    if not 0 <= inserted_records <= len(
        records
    ):
        raise TimescaleDBLoadError(
            "Không thể xác định số record "
            "insert/update hợp lệ."
        )

    updated_records = (
        len(records)
        - inserted_records
    )

    return {
        "input_records": len(records),
        "inserted_records": (
            inserted_records
        ),
        "updated_records": (
            updated_records
        ),
        "database_records_before": (
            records_before
        ),
        "database_records_after": (
            records_after
        ),
    }


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

        temporary_path.replace(
            output_path
        )
    except OSError as error:
        raise TimescaleDBLoadError(
            "Không thể ghi load summary: "
            f"{output_path}"
        ) from error


def _build_load_directory(
    load_root: Path,
    partition_date: str,
    partition_hour: str,
    batch_id: str,
) -> Path:
    return (
        load_root
        / "air_quality"
        / "hourly"
        / f"date={partition_date}"
        / f"hour={partition_hour}"
        / f"batch_id={batch_id}"
    )


def load_clean_parquet_batch(
    clean_data_path: Path,
    load_root: Path,
    batch_id: str,
    partition_date: str,
    partition_hour: str,
) -> dict[str, Any]:
    clean_data_path = (
        clean_data_path.resolve()
    )

    load_root = load_root.resolve()

    if not clean_data_path.exists():
        raise TimescaleDBLoadError(
            "Không tìm thấy Clean Parquet: "
            f"{clean_data_path}"
        )

    if not clean_data_path.is_file():
        raise TimescaleDBLoadError(
            "Clean data path không phải file: "
            f"{clean_data_path}"
        )

    try:
        clean_dataframe = pd.read_parquet(
            clean_data_path
        )
    except (
        OSError,
        ValueError,
        ImportError,
    ) as error:
        raise TimescaleDBLoadError(
            "Không thể đọc Clean Parquet."
        ) from error

    started_at = datetime.now(
        timezone.utc
    )

    load_result = load_air_quality_dataframe(
        clean_dataframe
    )

    finished_at = datetime.now(
        timezone.utc
    )

    load_directory = _build_load_directory(
        load_root=load_root,
        partition_date=partition_date,
        partition_hour=partition_hour,
        batch_id=batch_id,
    )

    summary_path = (
        load_directory
        / "load_summary.json"
    )

    summary = {
        "pipeline_name": (
            "open_meteo_air_quality_timescaledb_load"
        ),
        "source": "open_meteo",
        "status": "SUCCESS",
        "batch_id": batch_id,
        "partition_date": partition_date,
        "partition_hour": partition_hour,
        "database_table": (
            "fact_air_quality_hourly"
        ),
        "upsert_key": list(
            UNIQUE_KEY_COLUMNS
        ),
        "clean_data_path": str(
            clean_data_path
        ),
        "started_at": started_at.isoformat(),
        "finished_at": (
            finished_at.isoformat()
        ),
        "duration_seconds": (
            finished_at - started_at
        ).total_seconds(),
        **load_result,
        "load_summary_path": str(
            summary_path
        ),
    }

    _write_json_atomically(
        output_path=summary_path,
        data=summary,
    )

    return summary