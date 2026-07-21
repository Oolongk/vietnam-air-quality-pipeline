from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from minio import Minio

from src.utils.minio_client import MinioSettings, get_minio_client
from src.utils.minio_object_io import list_object_names


CLEAN_PREFIX = "clean/air_quality/hourly"
MART_PREFIX = "air_quality"
LOCAL_TIMEZONE = "Asia/Ho_Chi_Minh"
LOCATION_CONFIG = Path("configs/locations.csv")

POLLUTANTS = [
    "pm2_5",
    "pm10",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
]

REQUIRED_COLUMNS = [
    "point_id",
    "location_id",
    "point_name",
    "point_type",
    "latitude",
    "longitude",
    "forecast_time",
    "us_aqi",
    "source",
    "batch_id",
    "schema_version",
    "ingested_at",
    *POLLUTANTS,
]

PARTITION_PATTERN = re.compile(
    r"date=(?P<date>\d{4}-\d{2}-\d{2})/"
    r"hour=(?P<hour>\d{2})/"
    r"batch_id=(?P<batch_id>[^/]+)/data\.parquet$"
)

AQI_LABELS = [
    "Good",
    "Moderate",
    "Unhealthy for Sensitive Groups",
    "Unhealthy",
    "Very Unhealthy",
    "Hazardous",
]


class MinioMartBuildError(RuntimeError):
    """Lỗi khi xây dựng MinIO Air Quality Mart."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_parquet(
    client: Minio,
    bucket_name: str,
    object_name: str,
) -> pd.DataFrame:
    response: Any = None

    try:
        response = client.get_object(
            bucket_name,
            object_name,
        )
        payload = response.read()

        if not payload:
            raise MinioMartBuildError(
                f"Parquet rỗng: {bucket_name}/{object_name}"
            )

        return pd.read_parquet(BytesIO(payload))

    except Exception as error:
        if isinstance(error, MinioMartBuildError):
            raise

        raise MinioMartBuildError(
            f"Không đọc được {bucket_name}/{object_name}: {error}"
        ) from error

    finally:
        if response is not None:
            response.close()
            response.release_conn()


def _put_parquet(
    client: Minio,
    bucket_name: str,
    object_name: str,
    dataframe: pd.DataFrame,
) -> None:
    buffer = BytesIO()

    dataframe.to_parquet(
        buffer,
        index=False,
        engine="pyarrow",
        compression="snappy",
    )

    payload = buffer.getvalue()

    client.put_object(
        bucket_name,
        object_name,
        BytesIO(payload),
        len(payload),
        content_type="application/octet-stream",
    )


def _put_json(
    client: Minio,
    bucket_name: str,
    object_name: str,
    value: dict[str, Any],
) -> None:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        default=str,
    ).encode("utf-8")

    client.put_object(
        bucket_name,
        object_name,
        BytesIO(payload),
        len(payload),
        content_type="application/json",
    )


def _partition_parts(
    object_name: str,
) -> tuple[str, str, str]:
    match = PARTITION_PATTERN.search(object_name)

    if match is None:
        raise MinioMartBuildError(
            f"Object không đúng partition Clean: {object_name}"
        )

    return (
        match.group("date"),
        match.group("hour"),
        match.group("batch_id"),
    )


def _find_clean_objects(
    settings: MinioSettings,
    client: Minio,
) -> list[str]:
    object_names = [
        object_name
        for object_name in list_object_names(
            bucket_name=settings.clean_bucket,
            prefix=CLEAN_PREFIX,
            recursive=True,
            settings=settings,
            client=client,
        )
        if PARTITION_PATTERN.search(object_name)
    ]

    if not object_names:
        raise MinioMartBuildError(
            f"Không tìm thấy data.parquet dưới '{CLEAN_PREFIX}'."
        )

    return sorted(
        object_names,
        key=_partition_parts,
    )


def _normalize_clean(
    dataframe: pd.DataFrame,
    object_name: str,
) -> pd.DataFrame:
    missing_columns = [
        column_name
        for column_name in REQUIRED_COLUMNS
        if column_name not in dataframe.columns
    ]

    if missing_columns:
        raise MinioMartBuildError(
            f"'{object_name}' thiếu cột: "
            f"{', '.join(missing_columns)}"
        )

    if dataframe.empty:
        raise MinioMartBuildError(
            f"'{object_name}' không có dữ liệu."
        )

    result = dataframe.copy()

    result["forecast_time"] = pd.to_datetime(
        result["forecast_time"],
        errors="coerce",
        utc=True,
    ).dt.tz_convert(LOCAL_TIMEZONE)

    result["ingested_at"] = pd.to_datetime(
        result["ingested_at"],
        errors="coerce",
        utc=True,
    )

    invalid_times = (
        result["forecast_time"].isna()
        | result["ingested_at"].isna()
    )

    if invalid_times.any():
        raise MinioMartBuildError(
            f"'{object_name}' có "
            f"{int(invalid_times.sum())} dòng thời gian không hợp lệ."
        )

    duplicate_count = int(
        result.duplicated(
            [
                "point_id",
                "forecast_time",
                "batch_id",
            ]
        ).sum()
    )

    if duplicate_count:
        raise MinioMartBuildError(
            f"'{object_name}' có "
            f"{duplicate_count} logical duplicate."
        )

    return result


def _load_location_dimension() -> pd.DataFrame:
    columns = [
        "location_id",
        "location_name",
        "region",
    ]

    if not LOCATION_CONFIG.exists():
        return pd.DataFrame(columns=columns)

    dataframe = pd.read_csv(
        LOCATION_CONFIG,
        encoding="utf-8-sig",
    )

    if "location_id" not in dataframe.columns:
        return pd.DataFrame(columns=columns)

    for column_name in [
        "location_name",
        "region",
    ]:
        if column_name not in dataframe.columns:
            dataframe[column_name] = pd.NA

    return dataframe[columns].drop_duplicates(
        "location_id",
        keep="last",
    )


def _enrich_locations(
    dataframe: pd.DataFrame,
    location_dimension: pd.DataFrame,
) -> pd.DataFrame:
    result = dataframe.drop(
        columns=[
            "location_name",
            "region",
        ],
        errors="ignore",
    ).copy()

    if location_dimension.empty:
        result["location_name"] = pd.NA
        result["region"] = pd.NA
        return result

    return result.merge(
        location_dimension,
        on="location_id",
        how="left",
        validate="m:1",
    )


def _add_aqi_classification(
    dataframe: pd.DataFrame,
    source_column: str,
) -> pd.DataFrame:
    result = dataframe.copy()

    numeric_aqi = pd.to_numeric(
        result[source_column],
        errors="coerce",
    )

    bins = [
        float("-inf"),
        50,
        100,
        150,
        200,
        300,
        float("inf"),
    ]

    result["aqi_level"] = pd.cut(
        numeric_aqi,
        bins=bins,
        labels=AQI_LABELS,
    ).astype("string")

    result["aqi_severity"] = pd.cut(
        numeric_aqi,
        bins=bins,
        labels=[1, 2, 3, 4, 5, 6],
    ).astype("Int64")

    return result


def build_current_aqi(
    latest_clean: pd.DataFrame,
    mart_created_at: datetime,
) -> pd.DataFrame:
    snapshot_hour = (
        latest_clean["ingested_at"]
        .max()
        .tz_convert(LOCAL_TIMEZONE)
        .floor("h")
    )

    result = latest_clean.copy()

    result["_distance"] = (
        result["forecast_time"] - snapshot_hour
    ).abs().dt.total_seconds()

    result["_past"] = (
        result["forecast_time"] < snapshot_hour
    )

    result = (
        result.sort_values(
            [
                "point_id",
                "_distance",
                "_past",
                "forecast_time",
            ]
        )
        .drop_duplicates(
            "point_id",
            keep="first",
        )
        .drop(
            columns=[
                "_distance",
                "_past",
            ]
        )
    )

    result = _add_aqi_classification(
        result,
        "us_aqi",
    )

    result = result.rename(
        columns={
            "batch_id": "source_batch_id",
            "ingested_at": "source_ingested_at",
        }
    )

    result["mart_created_at"] = pd.Timestamp(
        mart_created_at
    )

    columns = [
        "point_id",
        "location_id",
        "location_name",
        "region",
        "point_name",
        "point_type",
        "latitude",
        "longitude",
        "forecast_time",
        "us_aqi",
        "aqi_level",
        "aqi_severity",
        *POLLUTANTS,
        "source",
        "source_batch_id",
        "schema_version",
        "source_ingested_at",
        "mart_created_at",
    ]

    return (
        result[columns]
        .sort_values(
            [
                "aqi_severity",
                "us_aqi",
                "location_id",
                "point_id",
            ],
            ascending=[
                False,
                False,
                True,
                True,
            ],
        )
        .reset_index(drop=True)
    )


def build_location_summary(
    current_aqi: pd.DataFrame,
    mart_created_at: datetime,
) -> pd.DataFrame:
    keys = [
        "location_id",
        "location_name",
        "region",
    ]

    summary = current_aqi.groupby(
        keys,
        dropna=False,
        as_index=False,
    ).agg(
        monitoring_point_count=("point_id", "nunique"),
        forecast_time=("forecast_time", "max"),
        average_us_aqi=("us_aqi", "mean"),
        minimum_us_aqi=("us_aqi", "min"),
        maximum_us_aqi=("us_aqi", "max"),
        average_pm2_5=("pm2_5", "mean"),
        maximum_pm2_5=("pm2_5", "max"),
        average_pm10=("pm10", "mean"),
        maximum_pm10=("pm10", "max"),
        average_ozone=("ozone", "mean"),
        maximum_ozone=("ozone", "max"),
        latitude=("latitude", "mean"),
        longitude=("longitude", "mean"),
        source_batch_count=("source_batch_id", "nunique"),
    )

    worst = (
        current_aqi.sort_values(
            [
                *keys,
                "us_aqi",
                "point_id",
            ],
            ascending=[
                True,
                True,
                True,
                False,
                True,
            ],
            na_position="last",
        )
        .drop_duplicates(
            keys,
            keep="first",
        )[
            [
                *keys,
                "point_id",
                "point_name",
                "us_aqi",
            ]
        ]
        .rename(
            columns={
                "point_id": "worst_point_id",
                "point_name": "worst_point_name",
                "us_aqi": "worst_point_us_aqi",
            }
        )
    )

    summary = summary.merge(
        worst,
        on=keys,
        how="left",
        validate="1:1",
    )

    summary = _add_aqi_classification(
        summary,
        "maximum_us_aqi",
    )

    float_columns = [
        "average_us_aqi",
        "average_pm2_5",
        "maximum_pm2_5",
        "average_pm10",
        "maximum_pm10",
        "average_ozone",
        "maximum_ozone",
        "latitude",
        "longitude",
    ]

    summary[float_columns] = (
        summary[float_columns]
        .astype("Float64")
        .round(2)
    )

    for column_name in [
        "minimum_us_aqi",
        "maximum_us_aqi",
        "worst_point_us_aqi",
    ]:
        summary[column_name] = (
            summary[column_name]
            .round()
            .astype("Int64")
        )

    summary["mart_created_at"] = pd.Timestamp(
        mart_created_at
    )

    return (
        summary.sort_values(
            [
                "aqi_severity",
                "maximum_us_aqi",
                "location_id",
            ],
            ascending=[
                False,
                False,
                True,
            ],
        )
        .reset_index(drop=True)
    )


def build_daily_summary(
    clean_history: pd.DataFrame,
    mart_created_at: datetime,
) -> pd.DataFrame:
    history = (
        clean_history.sort_values(
            [
                "point_id",
                "forecast_time",
                "ingested_at",
                "batch_id",
            ]
        )
        .drop_duplicates(
            [
                "point_id",
                "forecast_time",
            ],
            keep="last",
        )
        .copy()
    )

    history = _add_aqi_classification(
        history,
        "us_aqi",
    )

    history["forecast_date"] = (
        history["forecast_time"]
        .dt.strftime("%Y-%m-%d")
    )

    keys = [
        "forecast_date",
        "point_id",
        "location_id",
        "location_name",
        "region",
        "point_name",
        "point_type",
        "latitude",
        "longitude",
    ]

    summary = history.groupby(
        keys,
        dropna=False,
        as_index=False,
    ).agg(
        first_forecast_time=("forecast_time", "min"),
        last_forecast_time=("forecast_time", "max"),
        available_hours=("forecast_time", "nunique"),
        average_us_aqi=("us_aqi", "mean"),
        minimum_us_aqi=("us_aqi", "min"),
        maximum_us_aqi=("us_aqi", "max"),
        average_pm2_5=("pm2_5", "mean"),
        maximum_pm2_5=("pm2_5", "max"),
        average_pm10=("pm10", "mean"),
        maximum_pm10=("pm10", "max"),
        average_ozone=("ozone", "mean"),
        maximum_ozone=("ozone", "max"),
        good_hours=(
            "aqi_level",
            lambda values: int(
                (values == "Good").sum()
            ),
        ),
        moderate_hours=(
            "aqi_level",
            lambda values: int(
                (values == "Moderate").sum()
            ),
        ),
        sensitive_group_hours=(
            "aqi_level",
            lambda values: int(
                (
                    values
                    == "Unhealthy for Sensitive Groups"
                ).sum()
            ),
        ),
        unhealthy_hours=(
            "aqi_level",
            lambda values: int(
                (values == "Unhealthy").sum()
            ),
        ),
        very_unhealthy_hours=(
            "aqi_level",
            lambda values: int(
                (values == "Very Unhealthy").sum()
            ),
        ),
        hazardous_hours=(
            "aqi_level",
            lambda values: int(
                (values == "Hazardous").sum()
            ),
        ),
        source_batch_count=("batch_id", "nunique"),
        latest_source_ingested_at=("ingested_at", "max"),
    )

    worst = (
        history.sort_values(
            [
                *keys,
                "us_aqi",
                "forecast_time",
            ],
            ascending=[
                True,
                True,
                True,
                True,
                True,
                True,
                True,
                True,
                True,
                False,
                True,
            ],
            na_position="last",
        )
        .drop_duplicates(
            keys,
            keep="first",
        )[
            [
                *keys,
                "forecast_time",
                "batch_id",
            ]
        ]
        .rename(
            columns={
                "forecast_time": "worst_forecast_time",
                "batch_id": "worst_hour_source_batch_id",
            }
        )
    )

    summary = summary.merge(
        worst,
        on=keys,
        how="left",
        validate="1:1",
    )

    summary = _add_aqi_classification(
        summary,
        "maximum_us_aqi",
    )

    summary["coverage_status"] = (
        summary["available_hours"].map(
            lambda value: (
                "COMPLETE"
                if int(value) >= 24
                else "PARTIAL"
            )
        )
    )

    float_columns = [
        "average_us_aqi",
        "average_pm2_5",
        "maximum_pm2_5",
        "average_pm10",
        "maximum_pm10",
        "average_ozone",
        "maximum_ozone",
    ]

    summary[float_columns] = (
        summary[float_columns]
        .astype("Float64")
        .round(2)
    )

    for column_name in [
        "minimum_us_aqi",
        "maximum_us_aqi",
    ]:
        summary[column_name] = (
            summary[column_name]
            .round()
            .astype("Int64")
        )

    summary["mart_created_at"] = pd.Timestamp(
        mart_created_at
    )

    return (
        summary.sort_values(
            [
                "forecast_date",
                "maximum_us_aqi",
                "location_id",
                "point_id",
            ],
            ascending=[
                False,
                False,
                True,
                True,
            ],
        )
        .reset_index(drop=True)
    )


def build_latest_minio_mart(
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> dict[str, Any]:
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

    started_at = _utc_now()

    clean_objects = _find_clean_objects(
        resolved_settings,
        resolved_client,
    )

    latest_object = clean_objects[-1]

    (
        partition_date,
        partition_hour,
        batch_id,
    ) = _partition_parts(latest_object)

    latest_clean = _normalize_clean(
        _read_parquet(
            resolved_client,
            resolved_settings.clean_bucket,
            latest_object,
        ),
        latest_object,
    )

    valid_history: list[pd.DataFrame] = []
    skipped_objects: list[dict[str, str]] = []

    for object_name in clean_objects:
        try:
            dataframe = _read_parquet(
                resolved_client,
                resolved_settings.clean_bucket,
                object_name,
            )

            valid_history.append(
                _normalize_clean(
                    dataframe,
                    object_name,
                )
            )

        except Exception as error:
            skipped_objects.append(
                {
                    "object_name": object_name,
                    "error": str(error),
                }
            )

    if not valid_history:
        raise MinioMartBuildError(
            "Không có Clean Parquet lịch sử hợp lệ."
        )

    clean_history = pd.concat(
        valid_history,
        ignore_index=True,
    )

    location_dimension = (
        _load_location_dimension()
    )

    latest_clean = _enrich_locations(
        latest_clean,
        location_dimension,
    )

    clean_history = _enrich_locations(
        clean_history,
        location_dimension,
    )

    mart_created_at = _utc_now()

    current_aqi = build_current_aqi(
        latest_clean,
        mart_created_at,
    )

    location_summary = build_location_summary(
        current_aqi,
        mart_created_at,
    )

    daily_summary = build_daily_summary(
        clean_history,
        mart_created_at,
    )

    partition = (
        f"date={partition_date}/"
        f"hour={partition_hour}/"
        f"batch_id={batch_id}"
    )

    outputs = {
        "current_aqi": (
            f"{MART_PREFIX}/current_aqi/"
            f"{partition}/data.parquet"
        ),
        "location_summary": (
            f"{MART_PREFIX}/location_summary/"
            f"{partition}/data.parquet"
        ),
        "daily_summary": (
            f"{MART_PREFIX}/daily_summary/"
            f"{partition}/data.parquet"
        ),
        "mart_summary": (
            f"{MART_PREFIX}/build_summary/"
            f"{partition}/mart_summary.json"
        ),
    }

    _put_parquet(
        resolved_client,
        resolved_settings.mart_bucket,
        outputs["current_aqi"],
        current_aqi,
    )

    _put_parquet(
        resolved_client,
        resolved_settings.mart_bucket,
        outputs["location_summary"],
        location_summary,
    )

    _put_parquet(
        resolved_client,
        resolved_settings.mart_bucket,
        outputs["daily_summary"],
        daily_summary,
    )

    finished_at = _utc_now()

    summary = {
        "pipeline_name": "air_quality_mart_builder",
        "stage_name": "mart",
        "status": "SUCCESS",
        "source": "minio_clean",
        "source_bucket": (
            resolved_settings.clean_bucket
        ),
        "latest_source_object": latest_object,
        "valid_source_object_count": (
            len(valid_history)
        ),
        "skipped_source_object_count": (
            len(skipped_objects)
        ),
        "skipped_source_objects": (
            skipped_objects[:20]
        ),
        "location_dimension_rows": (
            len(location_dimension)
        ),
        "batch_id": batch_id,
        "partition_date": partition_date,
        "partition_hour": partition_hour,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(
            (
                finished_at
                - started_at
            ).total_seconds(),
            3,
        ),
        "current_aqi_rows": len(current_aqi),
        "location_summary_rows": (
            len(location_summary)
        ),
        "daily_summary_rows": (
            len(daily_summary)
        ),
                "latest_clean_records": (
            len(latest_clean)
        ),
        "history_input_records": (
            len(clean_history)
        ),
        "input_records": (
            len(clean_history)
        ),
        "output_records": (
            len(current_aqi)
            + len(location_summary)
            + len(daily_summary)
        ),
        "failed_records": (
            len(skipped_objects)
        ),
        "mart_bucket": (
            resolved_settings.mart_bucket
        ),
        "outputs": outputs,
    }

    _put_json(
        resolved_client,
        resolved_settings.mart_bucket,
        outputs["mart_summary"],
        summary,
    )

    return summary
