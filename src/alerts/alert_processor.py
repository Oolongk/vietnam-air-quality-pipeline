from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg

from src.alerts.alert_rules import (
    AQIClassificationError,
    build_alert_message,
    classify_us_aqi,
)
from src.utils.db import (
    get_database_connection,
)


REQUIRED_COLUMNS: set[str] = {
    "point_id",
    "location_id",
    "forecast_time",
    "us_aqi",
    "source",
}

UNIQUE_KEY_COLUMNS: tuple[str, ...] = (
    "point_id",
    "forecast_time",
    "source",
)


UPDATE_FACT_SQL = """
    UPDATE fact_air_quality_hourly
    SET
        aqi_level = %(aqi_level)s,
        aqi_severity = %(aqi_severity)s
    WHERE
        point_id = %(point_id)s
        AND forecast_time = %(forecast_time)s
        AND source = %(source)s
    RETURNING id;
"""


DELETE_ALL_ALERTS_FOR_KEY_SQL = """
    DELETE FROM fact_air_quality_alerts
    WHERE
        point_id = %(point_id)s
        AND alert_time = %(forecast_time)s
        AND source = %(source)s;
"""


DELETE_STALE_ALERTS_SQL = """
    DELETE FROM fact_air_quality_alerts
    WHERE
        point_id = %(point_id)s
        AND alert_time = %(forecast_time)s
        AND source = %(source)s
        AND severity <> %(alert_severity)s;
"""


UPSERT_ALERT_SQL = """
    INSERT INTO fact_air_quality_alerts (
        point_id,
        location_id,
        alert_time,
        aqi_value,
        aqi_level,
        severity,
        message,
        status,
        source
    )
    VALUES (
        %(point_id)s,
        %(location_id)s,
        %(forecast_time)s,
        %(us_aqi)s,
        %(aqi_level)s,
        %(alert_severity)s,
        %(alert_message)s,
        'OPEN',
        %(source)s
    )
    ON CONFLICT (
        point_id,
        alert_time,
        severity,
        source
    )
    DO UPDATE SET
        location_id =
            EXCLUDED.location_id,

        aqi_value =
            EXCLUDED.aqi_value,

        aqi_level =
            EXCLUDED.aqi_level,

        message =
            EXCLUDED.message;
"""


class AirQualityAlertProcessingError(
    RuntimeError
):
    """Lỗi khi phân loại AQI hoặc tạo alert."""


def _blank_string_mask(
    series: pd.Series,
) -> pd.Series:
    values = series.astype(
        "string"
    )

    return (
        values.isna()
        | values
        .str.strip()
        .eq("")
        .fillna(True)
    )


def _validate_dataframe(
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
        raise AirQualityAlertProcessingError(
            "Clean DataFrame không có record."
        )

    missing_columns = (
        REQUIRED_COLUMNS
        - set(dataframe.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise AirQualityAlertProcessingError(
            "Clean DataFrame thiếu các cột: "
            f"{missing_text}"
        )

    working_dataframe = (
        dataframe
        .copy()
        .reset_index(drop=True)
    )

    for column in (
        "point_id",
        "location_id",
        "source",
    ):
        invalid_mask = _blank_string_mask(
            working_dataframe[column]
        )

        if invalid_mask.any():
            raise AirQualityAlertProcessingError(
                f"Clean DataFrame có "
                f"{column} bị rỗng."
            )

    invalid_source = (
        working_dataframe["source"]
        .astype("string")
        .str.strip()
        .ne("open_meteo")
    )

    if invalid_source.any():
        raise AirQualityAlertProcessingError(
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
        raise AirQualityAlertProcessingError(
            "Clean DataFrame vẫn có "
            "duplicate theo khóa logic."
        )

    return working_dataframe


def _to_python_datetime(
    value: Any,
    field_name: str,
) -> datetime:
    if value is None or pd.isna(value):
        raise AirQualityAlertProcessingError(
            f"{field_name} không được rỗng."
        )

    try:
        timestamp = pd.Timestamp(value)
    except (
        TypeError,
        ValueError,
    ) as error:
        raise AirQualityAlertProcessingError(
            f"{field_name} không hợp lệ."
        ) from error

    if (
        timestamp.tzinfo is None
        or timestamp.utcoffset() is None
    ):
        raise AirQualityAlertProcessingError(
            f"{field_name} phải có timezone."
        )

    return timestamp.to_pydatetime()


def prepare_classified_records(
    dataframe: pd.DataFrame,
) -> list[dict[str, Any]]:
    working_dataframe = (
        _validate_dataframe(
            dataframe
        )
    )

    classified_records: list[
        dict[str, Any]
    ] = []

    for row_index, row in (
        working_dataframe.iterrows()
    ):
        try:
            classification = (
                classify_us_aqi(
                    row["us_aqi"]
                )
            )
        except AQIClassificationError as error:
            raise AirQualityAlertProcessingError(
                "Không thể phân loại AQI tại "
                f"row index {row_index}: {error}"
            ) from error

        point_id = str(
            row["point_id"]
        ).strip()

        location_id = str(
            row["location_id"]
        ).strip()

        source = str(
            row["source"]
        ).strip()

        forecast_time = (
            _to_python_datetime(
                row["forecast_time"],
                "forecast_time",
            )
        )

        if classification is None:
            classified_records.append(
                {
                    "point_id": point_id,
                    "location_id": location_id,
                    "forecast_time": (
                        forecast_time
                    ),
                    "source": source,
                    "us_aqi": None,
                    "aqi_level": None,
                    "aqi_severity": None,
                    "alert_severity": None,
                    "alert_message": None,
                }
            )

            continue

        alert_message = None

        if (
            classification.alert_severity
            is not None
        ):
            alert_message = (
                build_alert_message(
                    point_id=point_id,
                    location_id=location_id,
                    classification=(
                        classification
                    ),
                )
            )

        classified_records.append(
            {
                "point_id": point_id,
                "location_id": location_id,
                "forecast_time": (
                    forecast_time
                ),
                "source": source,
                "us_aqi": (
                    classification.aqi_value
                ),
                "aqi_level": (
                    classification.aqi_level
                ),
                "aqi_severity": (
                    classification.aqi_severity
                ),
                "alert_severity": (
                    classification.alert_severity
                ),
                "alert_message": (
                    alert_message
                ),
            }
        )

    return classified_records


def update_aqi_and_alerts(
    dataframe: pd.DataFrame,
    connection: Any | None = None,
) -> dict[str, Any]:
    records = prepare_classified_records(
        dataframe
    )

    owns_connection = connection is None

    resolved_connection = (
        connection
        or get_database_connection()
    )

    facts_updated = 0
    alerts_generated = 0
    null_aqi_records = 0

    alert_counts = {
        "MEDIUM": 0,
        "HIGH": 0,
        "CRITICAL": 0,
    }

    try:
        with resolved_connection.transaction():
            with resolved_connection.cursor() as cursor:
                for record in records:
                    cursor.execute(
                        UPDATE_FACT_SQL,
                        record,
                    )

                    updated_row = cursor.fetchone()

                    if updated_row is None:
                        raise (
                            AirQualityAlertProcessingError(
                                "Không tìm thấy fact record: "
                                f"{record['point_id']} | "
                                f"{record['forecast_time']} | "
                                f"{record['source']}"
                            )
                        )

                    facts_updated += 1

                    if record["us_aqi"] is None:
                        null_aqi_records += 1

                        cursor.execute(
                            DELETE_ALL_ALERTS_FOR_KEY_SQL,
                            record,
                        )

                        continue

                    if (
                        record["alert_severity"]
                        is None
                    ):
                        cursor.execute(
                            DELETE_ALL_ALERTS_FOR_KEY_SQL,
                            record,
                        )

                        continue

                    cursor.execute(
                        DELETE_STALE_ALERTS_SQL,
                        record,
                    )

                    cursor.execute(
                        UPSERT_ALERT_SQL,
                        record,
                    )

                    alerts_generated += 1

                    alert_counts[
                        record["alert_severity"]
                    ] += 1

    except psycopg.Error as error:
        raise AirQualityAlertProcessingError(
            "TimescaleDB từ chối cập nhật "
            f"AQI hoặc alert: {error}"
        ) from error
    finally:
        if owns_connection:
            resolved_connection.close()

    return {
        "input_records": len(records),
        "facts_updated": facts_updated,
        "classified_records": (
            len(records)
            - null_aqi_records
        ),
        "null_aqi_records": (
            null_aqi_records
        ),
        "alerts_generated": (
            alerts_generated
        ),
        "medium_alerts": (
            alert_counts["MEDIUM"]
        ),
        "high_alerts": (
            alert_counts["HIGH"]
        ),
        "critical_alerts": (
            alert_counts["CRITICAL"]
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
        raise AirQualityAlertProcessingError(
            "Không thể ghi alert summary: "
            f"{output_path}"
        ) from error


def process_clean_batch_alerts(
    clean_data_path: Path,
    alert_root: Path,
    batch_id: str,
    partition_date: str,
    partition_hour: str,
) -> dict[str, Any]:
    clean_data_path = (
        clean_data_path.resolve()
    )

    alert_root = alert_root.resolve()

    if not clean_data_path.exists():
        raise AirQualityAlertProcessingError(
            "Không tìm thấy Clean Parquet: "
            f"{clean_data_path}"
        )

    try:
        dataframe = pd.read_parquet(
            clean_data_path
        )
    except (
        OSError,
        ValueError,
        ImportError,
    ) as error:
        raise AirQualityAlertProcessingError(
            "Không thể đọc Clean Parquet."
        ) from error

    started_at = datetime.now(
        timezone.utc
    )

    processing_result = (
        update_aqi_and_alerts(
            dataframe
        )
    )

    finished_at = datetime.now(
        timezone.utc
    )

    output_directory = (
        alert_root
        / "air_quality"
        / "hourly"
        / f"date={partition_date}"
        / f"hour={partition_hour}"
        / f"batch_id={batch_id}"
    )

    summary_path = (
        output_directory
        / "alert_summary.json"
    )

    summary = {
        "pipeline_name": (
            "open_meteo_air_quality_alert_processing"
        ),
        "source": "open_meteo",
        "status": "SUCCESS",
        "batch_id": batch_id,
        "partition_date": partition_date,
        "partition_hour": partition_hour,
        "clean_data_path": str(
            clean_data_path
        ),
        "started_at": (
            started_at.isoformat()
        ),
        "finished_at": (
            finished_at.isoformat()
        ),
        "duration_seconds": (
            finished_at - started_at
        ).total_seconds(),
        **processing_result,
        "alert_summary_path": str(
            summary_path
        ),
    }

    _write_json_atomically(
        output_path=summary_path,
        data=summary,
    )

    return summary