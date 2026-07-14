from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from dotenv import load_dotenv
from minio import Minio
from psycopg import sql

from src.quality.minio_quality_processor import (
    find_latest_loadable_quality_batch,
)
from src.utils.minio_client import (
    MinioSettings,
    ensure_buckets,
    get_minio_client,
)
from src.utils.minio_object_io import (
    get_parquet_object,
    put_json_object,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(
    PROJECT_ROOT / ".env",
    override=False,
)


FACT_TABLE_NAME = (
    "fact_air_quality_hourly"
)

MANDATORY_DATAFRAME_COLUMNS: set[str] = {
    "point_id",
    "location_id",
    "forecast_time",
    "latitude",
    "longitude",
    "source",
}

LOGICAL_KEY_COLUMNS: tuple[str, ...] = (
    "point_id",
    "forecast_time",
    "source",
)


class MinioTimescaleDBLoadError(
    RuntimeError
):
    """Lỗi khi load Clean Parquet từ MinIO vào TimescaleDB."""


def _first_environment_value(
    *variable_names: str,
    default: str | None = None,
    required: bool = True,
) -> str:
    for variable_name in variable_names:
        value = os.getenv(
            variable_name
        )

        if value is not None:
            cleaned_value = value.strip()

            if cleaned_value:
                return cleaned_value

    if default is not None:
        return default

    if required:
        names_text = ", ".join(
            variable_names
        )

        raise MinioTimescaleDBLoadError(
            "Thiếu biến môi trường database. "
            f"Cần một trong các biến: {names_text}"
        )

    return ""


@dataclass(frozen=True)
class TimescaleDBSettings:
    host: str
    port: int
    database: str
    user: str
    password: str

    @classmethod
    def from_environment(
        cls,
    ) -> "TimescaleDBSettings":
        host = _first_environment_value(
            "TIMESCALEDB_HOST",
            "POSTGRES_HOST",
            "DB_HOST",
            default="localhost",
        )

        raw_port = _first_environment_value(
            "TIMESCALEDB_PORT",
            "POSTGRES_PORT",
            "DB_PORT",
            default="5432",
        )

        try:
            port = int(
                raw_port
            )
        except ValueError as error:
            raise MinioTimescaleDBLoadError(
                "Database port phải là số nguyên."
            ) from error

        database = _first_environment_value(
            "TIMESCALEDB_DATABASE",
            "TIMESCALEDB_DB",
            "POSTGRES_DB",
            "DB_NAME",
        )

        user = _first_environment_value(
            "TIMESCALEDB_USER",
            "POSTGRES_USER",
            "DB_USER",
        )

        password = _first_environment_value(
            "TIMESCALEDB_PASSWORD",
            "POSTGRES_PASSWORD",
            "DB_PASSWORD",
        )

        return cls(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
        )

    def connect(
        self,
    ) -> psycopg.Connection:
        try:
            return psycopg.connect(
                host=self.host,
                port=self.port,
                dbname=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=10,
            )
        except psycopg.Error as error:
            raise MinioTimescaleDBLoadError(
                "Không thể kết nối TimescaleDB: "
                f"{error}"
            ) from error


def prepare_fact_dataframe(
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
        raise MinioTimescaleDBLoadError(
            "Clean DataFrame không có record."
        )

    missing_columns = (
        MANDATORY_DATAFRAME_COLUMNS
        - set(dataframe.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise MinioTimescaleDBLoadError(
            "Clean DataFrame thiếu các cột: "
            f"{missing_text}"
        )

    prepared = (
        dataframe
        .copy()
        .reset_index(drop=True)
    )

    for column_name in (
        "point_id",
        "location_id",
        "source",
    ):
        prepared[column_name] = (
            prepared[column_name]
            .astype("string")
            .str.strip()
        )

        invalid_mask = (
            prepared[column_name].isna()
            | prepared[column_name].eq("")
        )

        if invalid_mask.any():
            raise MinioTimescaleDBLoadError(
                f"{column_name} có giá trị rỗng."
            )

    prepared["forecast_time"] = (
        pd.to_datetime(
            prepared["forecast_time"],
            errors="coerce",
            utc=True,
        )
    )

    if prepared[
        "forecast_time"
    ].isna().any():
        raise MinioTimescaleDBLoadError(
            "forecast_time có timestamp không hợp lệ."
        )

    if "ingested_at" in prepared.columns:
        prepared["ingested_at"] = (
            pd.to_datetime(
                prepared["ingested_at"],
                errors="coerce",
                utc=True,
            )
        )

        if prepared[
            "ingested_at"
        ].isna().any():
            raise MinioTimescaleDBLoadError(
                "ingested_at có timestamp không hợp lệ."
            )

    duplicate_mask = (
        prepared.duplicated(
            subset=list(
                LOGICAL_KEY_COLUMNS
            ),
            keep=False,
        )
    )

    if duplicate_mask.any():
        duplicate_count = int(
            duplicate_mask.sum()
        )

        raise MinioTimescaleDBLoadError(
            "Clean DataFrame có "
            f"{duplicate_count} record duplicate "
            "theo point_id + forecast_time + source."
        )

    return prepared


def _get_table_columns(
    connection: psycopg.Connection,
    table_name: str,
) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (
                table_name,
            ),
        )

        rows = cursor.fetchall()

    if not rows:
        raise MinioTimescaleDBLoadError(
            f"Không tìm thấy bảng {table_name}."
        )

    return {
        str(row[0])
        for row in rows
    }


def _validate_dimensions(
    connection: psycopg.Connection,
    dataframe: pd.DataFrame,
) -> None:
    location_ids = sorted(
        dataframe[
            "location_id"
        ].dropna().unique().tolist()
    )

    point_ids = sorted(
        dataframe[
            "point_id"
        ].dropna().unique().tolist()
    )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT location_id
            FROM dim_location
            WHERE location_id = ANY(%s)
            """,
            (
                location_ids,
            ),
        )

        existing_locations = {
            str(row[0])
            for row in cursor.fetchall()
        }

        cursor.execute(
            """
            SELECT point_id
            FROM dim_monitoring_point
            WHERE point_id = ANY(%s)
            """,
            (
                point_ids,
            ),
        )

        existing_points = {
            str(row[0])
            for row in cursor.fetchall()
        }

    missing_locations = (
        set(location_ids)
        - existing_locations
    )

    missing_points = (
        set(point_ids)
        - existing_points
    )

    if missing_locations:
        missing_text = ", ".join(
            sorted(missing_locations)
        )

        raise MinioTimescaleDBLoadError(
            "dim_location thiếu các location_id: "
            f"{missing_text}"
        )

    if missing_points:
        missing_text = ", ".join(
            sorted(missing_points)
        )

        raise MinioTimescaleDBLoadError(
            "dim_monitoring_point thiếu các point_id: "
            f"{missing_text}"
        )


def _resolve_time_column(
    table_columns: set[str],
) -> str:
    if "forecast_time" in table_columns:
        return "forecast_time"

    if "datetime" in table_columns:
        return "datetime"

    raise MinioTimescaleDBLoadError(
        "fact_air_quality_hourly thiếu "
        "forecast_time hoặc datetime."
    )


def _build_column_mapping(
    table_columns: set[str],
    dataframe_columns: set[str],
    time_column: str,
) -> list[tuple[str, str]]:
    candidates: list[
    tuple[str, str]
] = [
    (
        "point_id",
        "point_id",
    ),
    (
        "location_id",
        "location_id",
    ),
    (
        "point_name",
        "point_name",
    ),
    (
        "point_type",
        "point_type",
    ),
    (
        "latitude",
        "latitude",
    ),
    (
        "longitude",
        "longitude",
    ),
    (
        time_column,
        "forecast_time",
    ),
        (
            "pm2_5",
            "pm2_5",
        ),
        (
            "pm10",
            "pm10",
        ),
        (
            "carbon_monoxide",
            "carbon_monoxide",
        ),
        (
            "nitrogen_dioxide",
            "nitrogen_dioxide",
        ),
        (
            "sulphur_dioxide",
            "sulphur_dioxide",
        ),
        (
            "ozone",
            "ozone",
        ),
        (
            "us_aqi",
            "us_aqi",
        ),
        (
            "us_aqi_pm2_5",
            "us_aqi_pm2_5",
        ),
        (
            "us_aqi_pm10",
            "us_aqi_pm10",
        ),
        (
            "us_aqi_nitrogen_dioxide",
            "us_aqi_nitrogen_dioxide",
        ),
        (
            "us_aqi_carbon_monoxide",
            "us_aqi_carbon_monoxide",
        ),
        (
            "us_aqi_ozone",
            "us_aqi_ozone",
        ),
        (
            "us_aqi_sulphur_dioxide",
            "us_aqi_sulphur_dioxide",
        ),
        (
            "aqi_level",
            "aqi_level",
        ),
        (
            "aqi_severity",
            "aqi_severity",
        ),
        (
            "source",
            "source",
        ),
        (
            "batch_id",
            "batch_id",
        ),
        (
            "schema_version",
            "schema_version",
        ),
        (
            "ingested_at",
            "ingested_at",
        ),
    ]

    mapping = [
        (
            database_column,
            dataframe_column,
        )
        for (
            database_column,
            dataframe_column,
        ) in candidates
        if (
            database_column
            in table_columns
            and dataframe_column
            in dataframe_columns
        )
    ]

    mapped_database_columns = {
        database_column
        for database_column, _ in mapping
    }

    mandatory_database_columns = {
        "point_id",
        "location_id",
        time_column,
        "source",
    }

    missing_mandatory = (
        mandatory_database_columns
        - mapped_database_columns
    )

    if missing_mandatory:
        missing_text = ", ".join(
            sorted(missing_mandatory)
        )

        raise MinioTimescaleDBLoadError(
            "Không thể map các cột database: "
            f"{missing_text}"
        )

    return mapping


def _python_scalar(
    value: Any,
) -> Any:
    try:
        missing_value = pd.isna(
            value
        )

        if isinstance(
            missing_value,
            bool,
        ) and missing_value:
            return None
    except (
        TypeError,
        ValueError,
    ):
        pass

    if isinstance(
        value,
        pd.Timestamp,
    ):
        return value.to_pydatetime()

    item_method = getattr(
        value,
        "item",
        None,
    )

    if callable(item_method):
        try:
            return item_method()
        except (
            TypeError,
            ValueError,
        ):
            pass

    return value


def _existing_logical_keys(
    connection: psycopg.Connection,
    dataframe: pd.DataFrame,
    time_column: str,
) -> set[tuple[str, datetime, str]]:
    point_ids = (
        dataframe[
            "point_id"
        ].unique().tolist()
    )

    sources = (
        dataframe[
            "source"
        ].unique().tolist()
    )

    minimum_time = (
        dataframe[
            "forecast_time"
        ].min().to_pydatetime()
    )

    maximum_time = (
        dataframe[
            "forecast_time"
        ].max().to_pydatetime()
    )

    query = sql.SQL(
        """
        SELECT
            point_id,
            {time_column},
            source
        FROM {table_name}
        WHERE point_id = ANY(%s)
          AND {time_column} >= %s
          AND {time_column} <= %s
          AND source = ANY(%s)
        """
    ).format(
        time_column=sql.Identifier(
            time_column
        ),
        table_name=sql.Identifier(
            FACT_TABLE_NAME
        ),
    )

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                point_ids,
                minimum_time,
                maximum_time,
                sources,
            ),
        )

        rows = cursor.fetchall()

    return {
        (
            str(row[0]),
            pd.Timestamp(
                row[1]
            ).tz_convert(
                "UTC"
            ).to_pydatetime(),
            str(row[2]),
        )
        for row in rows
    }


def upsert_fact_dataframe(
    connection: psycopg.Connection,
    dataframe: pd.DataFrame,
) -> dict[str, Any]:
    prepared_dataframe = (
        prepare_fact_dataframe(
            dataframe
        )
    )

    _validate_dimensions(
        connection=connection,
        dataframe=prepared_dataframe,
    )

    table_columns = (
        _get_table_columns(
            connection=connection,
            table_name=FACT_TABLE_NAME,
        )
    )

    time_column = (
        _resolve_time_column(
            table_columns
        )
    )

    column_mapping = (
        _build_column_mapping(
            table_columns=table_columns,
            dataframe_columns=set(
                prepared_dataframe.columns
            ),
            time_column=time_column,
        )
    )

    existing_keys = (
        _existing_logical_keys(
            connection=connection,
            dataframe=prepared_dataframe,
            time_column=time_column,
        )
    )

    dataframe_keys = [
        (
            str(row.point_id),
            pd.Timestamp(
                row.forecast_time
            ).tz_convert(
                "UTC"
            ).to_pydatetime(),
            str(row.source),
        )
        for row in (
            prepared_dataframe[
                [
                    "point_id",
                    "forecast_time",
                    "source",
                ]
            ].itertuples(
                index=False
            )
        )
    ]

    updated_rows = sum(
        key in existing_keys
        for key in dataframe_keys
    )

    inserted_rows = (
        len(prepared_dataframe)
        - updated_rows
    )

    database_columns = [
        database_column
        for (
            database_column,
            _,
        ) in column_mapping
    ]

    dataframe_columns = [
        dataframe_column
        for (
            _,
            dataframe_column,
        ) in column_mapping
    ]

    conflict_columns = [
        "point_id",
        time_column,
        "source",
    ]

    update_columns = [
        column_name
        for column_name in database_columns
        if column_name
        not in conflict_columns
    ]

    insert_identifiers = sql.SQL(
        ", "
    ).join(
        sql.Identifier(
            column_name
        )
        for column_name
        in database_columns
    )

    placeholders = sql.SQL(
        ", "
    ).join(
        sql.Placeholder()
        for _ in database_columns
    )

    conflict_identifiers = sql.SQL(
        ", "
    ).join(
        sql.Identifier(
            column_name
        )
        for column_name
        in conflict_columns
    )

    if update_columns:
        update_expression = sql.SQL(
            ", "
        ).join(
            sql.SQL(
                "{column_name} = "
                "EXCLUDED.{column_name}"
            ).format(
                column_name=sql.Identifier(
                    column_name
                )
            )
            for column_name
            in update_columns
        )

        upsert_action = sql.SQL(
            "DO UPDATE SET "
        ) + update_expression
    else:
        upsert_action = sql.SQL(
            "DO NOTHING"
        )

    query = sql.SQL(
        """
        INSERT INTO {table_name}
            ({insert_columns})
        VALUES
            ({placeholders})
        ON CONFLICT
            ({conflict_columns})
        {upsert_action}
        """
    ).format(
        table_name=sql.Identifier(
            FACT_TABLE_NAME
        ),
        insert_columns=(
            insert_identifiers
        ),
        placeholders=placeholders,
        conflict_columns=(
            conflict_identifiers
        ),
        upsert_action=upsert_action,
    )

    records = (
        prepared_dataframe[
            dataframe_columns
        ].to_dict(
            orient="records"
        )
    )

    values = [
        tuple(
            _python_scalar(
                record[
                    dataframe_column
                ]
            )
            for dataframe_column
            in dataframe_columns
        )
        for record in records
    ]

    try:
        with connection.cursor() as cursor:
            cursor.executemany(
                query,
                values,
            )

    except psycopg.Error as error:
        raise MinioTimescaleDBLoadError(
            "Không thể upsert "
            "fact_air_quality_hourly: "
            f"{error}"
        ) from error

    return {
        "processed_rows": (
            len(prepared_dataframe)
        ),
        "inserted_rows": (
            inserted_rows
        ),
        "updated_rows": (
            updated_rows
        ),
        "database_columns": (
            database_columns
        ),
        "time_column": (
            time_column
        ),
    }


def load_latest_minio_clean_batch(
    minio_settings: MinioSettings | None = None,
    minio_client: Minio | None = None,
    database_settings: TimescaleDBSettings | None = None,
) -> dict[str, Any]:
    resolved_minio_settings = (
        minio_settings
        or MinioSettings.from_environment()
    )

    resolved_minio_client = (
        minio_client
        or get_minio_client(
            resolved_minio_settings
        )
    )

    resolved_database_settings = (
        database_settings
        or TimescaleDBSettings.from_environment()
    )

    ensure_buckets(
        settings=resolved_minio_settings,
        client=resolved_minio_client,
    )

    (
        quality_summary_object_name,
        quality_summary,
    ) = find_latest_loadable_quality_batch(
        settings=resolved_minio_settings,
        client=resolved_minio_client,
    )

    clean_object_name = (
        quality_summary.get(
            "clean_object_name"
        )
    )

    if (
        not isinstance(
            clean_object_name,
            str,
        )
        or not clean_object_name.strip()
    ):
        raise MinioTimescaleDBLoadError(
            "Data Quality summary thiếu "
            "clean_object_name."
        )

    batch_id = str(
        quality_summary.get(
            "batch_id",
            "",
        )
    ).strip()

    partition_date = str(
        quality_summary.get(
            "partition_date",
            "",
        )
    ).strip()

    partition_hour = str(
        quality_summary.get(
            "partition_hour",
            "",
        )
    ).strip()

    if not all(
        (
            batch_id,
            partition_date,
            partition_hour,
        )
    ):
        raise MinioTimescaleDBLoadError(
            "Data Quality summary thiếu "
            "batch_id hoặc partition."
        )

    started_at = datetime.now(
        timezone.utc
    )

    clean_dataframe = (
        get_parquet_object(
            bucket_name=(
                resolved_minio_settings
                .clean_bucket
            ),
            object_name=(
                clean_object_name
            ),
            settings=(
                resolved_minio_settings
            ),
            client=(
                resolved_minio_client
            ),
        )
    )

    connection = (
        resolved_database_settings.connect()
    )

    try:
        load_result = (
            upsert_fact_dataframe(
                connection=connection,
                dataframe=clean_dataframe,
            )
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    finished_at = datetime.now(
        timezone.utc
    )

    load_summary_object_name = (
        "pipeline/load/timescaledb/"
        f"date={partition_date}/"
        f"hour={partition_hour}/"
        f"batch_id={batch_id}/"
        "load_summary.json"
    )

    load_summary = {
        "pipeline_name": (
            "air_quality_timescaledb_load"
        ),
        "source": "open_meteo",
        "storage_backend": "minio",
        "database": "timescaledb",
        "status": "SUCCESS",
        "batch_id": batch_id,
        "partition_date": partition_date,
        "partition_hour": partition_hour,
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
        "quality_summary_bucket": (
            resolved_minio_settings
            .clean_bucket
        ),
        "quality_summary_object_name": (
            quality_summary_object_name
        ),
        "clean_bucket": (
            resolved_minio_settings
            .clean_bucket
        ),
        "clean_object_name": (
            clean_object_name
        ),
        "input_rows": (
            len(clean_dataframe)
        ),
        "processed_rows": (
            load_result[
                "processed_rows"
            ]
        ),
        "inserted_rows": (
            load_result[
                "inserted_rows"
            ]
        ),
        "updated_rows": (
            load_result[
                "updated_rows"
            ]
        ),
        "fact_table": (
            FACT_TABLE_NAME
        ),
        "database_time_column": (
            load_result[
                "time_column"
            ]
        ),
        "database_columns": (
            load_result[
                "database_columns"
            ]
        ),
        "summary_bucket": (
            resolved_minio_settings
            .mart_bucket
        ),
        "summary_object_name": (
            load_summary_object_name
        ),
    }

    put_json_object(
        bucket_name=(
            resolved_minio_settings
            .mart_bucket
        ),
        object_name=(
            load_summary_object_name
        ),
        data=load_summary,
        settings=(
            resolved_minio_settings
        ),
        client=(
            resolved_minio_client
        ),
    )

    return load_summary