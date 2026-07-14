from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

import pandas as pd
from minio import Minio

from src.utils.minio_client import (
    MinioSettings,
    ensure_buckets,
    get_minio_client,
)
from src.utils.minio_object_io import (
    get_json_object,
    list_object_names,
    put_json_object,
    put_parquet_object,
)


RAW_ROOT_PREFIX = (
    "open_meteo/air_quality"
)

TRANSFORMED_ROOT_PREFIX = (
    "transformed/air_quality/hourly"
)


NUMERIC_FLOAT_COLUMNS: tuple[str, ...] = (
    "pm2_5",
    "pm10",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
)

AQI_COLUMNS: tuple[str, ...] = (
    "us_aqi",
    "us_aqi_pm2_5",
    "us_aqi_pm10",
    "us_aqi_nitrogen_dioxide",
    "us_aqi_carbon_monoxide",
    "us_aqi_ozone",
    "us_aqi_sulphur_dioxide",
)

LOGICAL_KEY_COLUMNS: tuple[str, ...] = (
    "point_id",
    "forecast_time",
    "source",
)


class MinioBatchTransformError(
    RuntimeError
):
    """Lỗi khi transform Raw batch trên MinIO."""


def _require_non_empty_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise MinioBatchTransformError(
            f"{field_name} phải là chuỗi."
        )

    cleaned_value = value.strip()

    if not cleaned_value:
        raise MinioBatchTransformError(
            f"{field_name} không được rỗng."
        )

    return cleaned_value


def _parse_aware_datetime(
    value: Any,
    field_name: str,
) -> datetime:
    if not isinstance(value, str):
        raise MinioBatchTransformError(
            f"{field_name} phải là chuỗi ISO datetime."
        )

    normalized_value = (
        value.strip().replace(
            "Z",
            "+00:00",
        )
    )

    try:
        parsed_value = datetime.fromisoformat(
            normalized_value
        )
    except ValueError as error:
        raise MinioBatchTransformError(
            f"{field_name} không phải ISO datetime "
            f"hợp lệ: {value!r}"
        ) from error

    if (
        parsed_value.tzinfo is None
        or parsed_value.utcoffset() is None
    ):
        raise MinioBatchTransformError(
            f"{field_name} phải có timezone."
        )

    return parsed_value


def _find_hourly_payload(
    value: Any,
) -> dict[str, Any] | None:
    if not isinstance(
        value,
        Mapping,
    ):
        return None

    hourly = value.get(
        "hourly"
    )

    if isinstance(hourly, Mapping):
        hourly_times = hourly.get(
            "time"
        )

        if isinstance(
            hourly_times,
            list,
        ):
            return dict(value)

    for child_value in value.values():
        if not isinstance(
            child_value,
            Mapping,
        ):
            continue

        result = _find_hourly_payload(
            child_value
        )

        if result is not None:
            return result

    return None


def _find_first_value(
    value: Any,
    field_name: str,
) -> Any:
    if not isinstance(
        value,
        Mapping,
    ):
        return None

    if field_name in value:
        field_value = value.get(
            field_name
        )

        if field_value is not None:
            return field_value

    for child_value in value.values():
        if not isinstance(
            child_value,
            Mapping,
        ):
            continue

        result = _find_first_value(
            child_value,
            field_name,
        )

        if result is not None:
            return result

    return None


def _extract_point_metadata(
    raw_object: Mapping[str, Any],
) -> dict[str, Any]:
    point_object = raw_object.get(
        "point"
    )

    if not isinstance(
        point_object,
        Mapping,
    ):
        point_object = {}

    def resolve_value(
        field_name: str,
    ) -> Any:
        point_value = point_object.get(
            field_name
        )

        if point_value is not None:
            return point_value

        return _find_first_value(
            raw_object.get(
                "api_response"
            ),
            field_name,
        )

    point_id = _require_non_empty_string(
        resolve_value("point_id"),
        "point_id",
    )

    location_id = (
        _require_non_empty_string(
            resolve_value("location_id"),
            "location_id",
        )
    )

    point_name_value = resolve_value(
        "point_name"
    )

    point_type_value = resolve_value(
        "point_type"
    )

    latitude_value = resolve_value(
        "latitude"
    )

    longitude_value = resolve_value(
        "longitude"
    )

    try:
        latitude = float(
            latitude_value
        )

        longitude = float(
            longitude_value
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise MinioBatchTransformError(
            f"Tọa độ không hợp lệ cho {point_id}."
        ) from error

    if not -90 <= latitude <= 90:
        raise MinioBatchTransformError(
            f"Latitude không hợp lệ cho {point_id}."
        )

    if not -180 <= longitude <= 180:
        raise MinioBatchTransformError(
            f"Longitude không hợp lệ cho {point_id}."
        )

    point_name = (
        str(point_name_value).strip()
        if point_name_value is not None
        else point_id
    )

    point_type = (
        str(point_type_value).strip()
        if point_type_value is not None
        else "unknown"
    )

    return {
        "point_id": point_id,
        "location_id": location_id,
        "point_name": point_name,
        "point_type": point_type,
        "latitude": latitude,
        "longitude": longitude,
    }


def _build_forecast_time_series(
    hourly_times: list[Any],
) -> pd.Series:
    raw_series = pd.Series(
        hourly_times,
        dtype="string",
    )

    parsed_series = pd.to_datetime(
        raw_series,
        errors="coerce",
    )

    if parsed_series.isna().any():
        bad_values = (
            raw_series[
                parsed_series.isna()
            ]
            .head(5)
            .tolist()
        )

        raise MinioBatchTransformError(
            "hourly.time có timestamp không hợp lệ: "
            f"{bad_values}"
        )

    if parsed_series.dt.tz is None:
        try:
            parsed_series = (
                parsed_series.dt.tz_localize(
                    "Asia/Ho_Chi_Minh",
                    ambiguous="raise",
                    nonexistent="raise",
                )
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            raise MinioBatchTransformError(
                "Không thể gắn timezone "
                "Asia/Ho_Chi_Minh cho hourly.time."
            ) from error
    else:
        parsed_series = (
            parsed_series.dt.tz_convert(
                "Asia/Ho_Chi_Minh"
            )
        )

    return parsed_series


def _extract_hourly_column(
    hourly: Mapping[str, Any],
    column_name: str,
    expected_length: int,
) -> pd.Series:
    values = hourly.get(
        column_name
    )

    if values is None:
        return pd.Series(
            [pd.NA] * expected_length
        )

    if not isinstance(
        values,
        list,
    ):
        raise MinioBatchTransformError(
            f"hourly.{column_name} phải là list."
        )

    if len(values) != expected_length:
        raise MinioBatchTransformError(
            f"hourly.{column_name} có "
            f"{len(values)} phần tử, "
            f"nhưng hourly.time có "
            f"{expected_length} phần tử."
        )

    return pd.Series(
        values
    )


def transform_raw_object(
    raw_object: Mapping[str, Any],
) -> pd.DataFrame:
    if not isinstance(
        raw_object,
        Mapping,
    ):
        raise MinioBatchTransformError(
            "Raw object phải là JSON object."
        )

    batch_id = _require_non_empty_string(
        raw_object.get("batch_id"),
        "batch_id",
    )

    source = _require_non_empty_string(
        raw_object.get(
            "source",
            "open_meteo",
        ),
        "source",
    )

    if source != "open_meteo":
        raise MinioBatchTransformError(
            "Raw source phải là open_meteo."
        )

    schema_version = str(
        raw_object.get(
            "schema_version",
            "1.0",
        )
    ).strip()

    extracted_at = (
        _parse_aware_datetime(
            raw_object.get(
                "extracted_at"
            ),
            "extracted_at",
        )
    )

    point_metadata = (
        _extract_point_metadata(
            raw_object
        )
    )

    payload = _find_hourly_payload(
        raw_object.get(
            "api_response"
        )
    )

    if payload is None:
        raise MinioBatchTransformError(
            "Không tìm thấy cấu trúc "
            "hourly.time trong api_response."
        )

    hourly = payload.get(
        "hourly"
    )

    if not isinstance(
        hourly,
        Mapping,
    ):
        raise MinioBatchTransformError(
            "Không tìm thấy hourly object."
        )

    hourly_times = hourly.get(
        "time"
    )

    if not isinstance(
        hourly_times,
        list,
    ):
        raise MinioBatchTransformError(
            "hourly.time phải là list."
        )

    if not hourly_times:
        raise MinioBatchTransformError(
            "hourly.time không có dữ liệu."
        )

    record_count = len(
        hourly_times
    )

    dataframe = pd.DataFrame(
        {
            "forecast_time": (
                _build_forecast_time_series(
                    hourly_times
                )
            )
        }
    )

    for column_name in (
        *NUMERIC_FLOAT_COLUMNS,
        *AQI_COLUMNS,
    ):
        dataframe[column_name] = (
            _extract_hourly_column(
                hourly=hourly,
                column_name=column_name,
                expected_length=record_count,
            )
        )

    for column_name in (
        NUMERIC_FLOAT_COLUMNS
    ):
        dataframe[column_name] = (
            pd.to_numeric(
                dataframe[column_name],
                errors="coerce",
            ).astype("Float64")
        )

    for column_name in AQI_COLUMNS:
        numeric_values = pd.to_numeric(
            dataframe[column_name],
            errors="coerce",
        )

        non_integer_mask = (
            numeric_values.notna()
            & (
                numeric_values
                % 1
                != 0
            )
        )

        if non_integer_mask.any():
            raise MinioBatchTransformError(
                f"{column_name} chứa "
                "AQI không phải số nguyên."
            )

        dataframe[column_name] = (
            numeric_values.astype(
                "Int64"
            )
        )

    for (
        metadata_column,
        metadata_value,
    ) in point_metadata.items():
        dataframe[metadata_column] = (
            metadata_value
        )

    dataframe["source"] = source

    dataframe["batch_id"] = (
        batch_id
    )

    dataframe["schema_version"] = (
        schema_version
    )

    dataframe["ingested_at"] = (
        pd.Timestamp(
            extracted_at
        ).tz_convert("UTC")
    )

    ordered_columns = [
        "point_id",
        "location_id",
        "point_name",
        "point_type",
        "latitude",
        "longitude",
        "forecast_time",
        *NUMERIC_FLOAT_COLUMNS,
        *AQI_COLUMNS,
        "source",
        "batch_id",
        "schema_version",
        "ingested_at",
    ]

    return dataframe[
        ordered_columns
    ]


def _parse_summary_timestamp(
    summary: Mapping[str, Any],
) -> datetime:
    timestamp_value = (
        summary.get("finished_at")
        or summary.get("started_at")
    )

    return _parse_aware_datetime(
        timestamp_value,
        "summary timestamp",
    )


def find_latest_transformable_raw_batch(
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> tuple[str, dict[str, Any]]:
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
                resolved_settings.raw_bucket
            ),
            prefix=RAW_ROOT_PREFIX,
            recursive=True,
            settings=resolved_settings,
            client=resolved_client,
        )
        if object_name.endswith(
            "/run_summary.json"
        )
    ]

    if not summary_object_names:
        raise MinioBatchTransformError(
            "Không tìm thấy run_summary.json "
            "trong Raw bucket."
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
            summary = get_json_object(
                bucket_name=(
                    resolved_settings
                    .raw_bucket
                ),
                object_name=object_name,
                settings=resolved_settings,
                client=resolved_client,
            )

            if not isinstance(
                summary,
                dict,
            ):
                continue

            status = str(
                summary.get(
                    "status",
                    ""
                )
            ).strip().upper()

            if status not in {
                "SUCCESS",
                "PARTIAL_SUCCESS",
            }:
                continue

            successes = summary.get(
                "successes"
            )

            if (
                not isinstance(
                    successes,
                    list,
                )
                or not successes
            ):
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
        raise MinioBatchTransformError(
            "Không tìm thấy Raw batch "
            "SUCCESS hoặc PARTIAL_SUCCESS "
            "có object dữ liệu hợp lệ."
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


def build_transformed_prefix(
    partition_date: str,
    partition_hour: str,
    batch_id: str,
) -> str:
    return (
        f"{TRANSFORMED_ROOT_PREFIX}/"
        f"date={partition_date}/"
        f"hour={partition_hour}/"
        f"batch_id={batch_id}"
    )


def transform_raw_batch_to_minio(
    raw_summary: Mapping[str, Any],
    raw_summary_object_name: str,
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> dict[str, Any]:
    if not isinstance(
        raw_summary,
        Mapping,
    ):
        raise MinioBatchTransformError(
            "Raw summary phải là JSON object."
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
        raw_summary.get("batch_id"),
        "batch_id",
    )

    partition_date = (
        _require_non_empty_string(
            raw_summary.get(
                "partition_date"
            ),
            "partition_date",
        )
    )

    partition_hour = (
        _require_non_empty_string(
            raw_summary.get(
                "partition_hour"
            ),
            "partition_hour",
        )
    )

    raw_status = str(
        raw_summary.get(
            "status",
            ""
        )
    ).strip().upper()

    successes = raw_summary.get(
        "successes"
    )

    if not isinstance(
        successes,
        list,
    ):
        raise MinioBatchTransformError(
            "Raw summary thiếu danh sách successes."
        )

    started_at = datetime.now(
        timezone.utc
    )

    transformed_frames: list[
        pd.DataFrame
    ] = []

    transformed_objects: list[
        dict[str, Any]
    ] = []

    failures: list[
        dict[str, Any]
    ] = []

    for index, success in enumerate(
        successes
    ):
        if not isinstance(
            success,
            Mapping,
        ):
            failures.append(
                {
                    "index": index,
                    "error_type": (
                        "InvalidSuccessEntry"
                    ),
                    "error_message": (
                        "Success entry không "
                        "phải JSON object."
                    ),
                }
            )

            continue

        raw_object_name = (
            success.get("object_name")
        )

        point_id = str(
            success.get(
                "point_id",
                "UNKNOWN",
            )
        )

        if (
            not isinstance(
                raw_object_name,
                str,
            )
            or not raw_object_name.strip()
        ):
            failures.append(
                {
                    "point_id": point_id,
                    "error_type": (
                        "MissingObjectName"
                    ),
                    "error_message": (
                        "Success entry thiếu "
                        "object_name."
                    ),
                }
            )

            continue

        try:
            raw_object = get_json_object(
                bucket_name=(
                    resolved_settings
                    .raw_bucket
                ),
                object_name=(
                    raw_object_name
                ),
                settings=(
                    resolved_settings
                ),
                client=resolved_client,
            )

            transformed_frame = (
                transform_raw_object(
                    raw_object
                )
            )

            transformed_frames.append(
                transformed_frame
            )

            transformed_objects.append(
                {
                    "point_id": point_id,
                    "raw_bucket": (
                        resolved_settings
                        .raw_bucket
                    ),
                    "raw_object_name": (
                        raw_object_name
                    ),
                    "records_transformed": (
                        len(
                            transformed_frame
                        )
                    ),
                }
            )

        except Exception as error:
            failures.append(
                {
                    "point_id": point_id,
                    "raw_object_name": (
                        raw_object_name
                    ),
                    "error_type": (
                        type(error).__name__
                    ),
                    "error_message": (
                        str(error)
                    ),
                }
            )

    if transformed_frames:
        combined_dataframe = pd.concat(
            transformed_frames,
            ignore_index=True,
        )

        combined_dataframe = (
            combined_dataframe.sort_values(
                by=[
                    "forecast_time",
                    "point_id",
                ],
                kind="stable",
            ).reset_index(drop=True)
        )

        duplicate_mask = (
            combined_dataframe.duplicated(
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

            raise MinioBatchTransformError(
                "Dữ liệu Transform có "
                f"{duplicate_count} dòng duplicate "
                "theo point_id + forecast_time "
                "+ source."
            )

    else:
        combined_dataframe = (
            pd.DataFrame()
        )

    if combined_dataframe.empty:
        status = "FAILED"
    elif (
        failures
        or raw_status != "SUCCESS"
    ):
        status = "PARTIAL_SUCCESS"
    else:
        status = "SUCCESS"

    transformed_prefix = (
        build_transformed_prefix(
            partition_date=partition_date,
            partition_hour=partition_hour,
            batch_id=batch_id,
        )
    )

    parquet_object_name = (
        f"{transformed_prefix}/"
        "data.parquet"
    )

    summary_object_name = (
        f"{transformed_prefix}/"
        "transform_summary.json"
    )

    parquet_upload_result = None

    if not combined_dataframe.empty:
        parquet_upload_result = (
            put_parquet_object(
                bucket_name=(
                    resolved_settings
                    .clean_bucket
                ),
                object_name=(
                    parquet_object_name
                ),
                dataframe=(
                    combined_dataframe
                ),
                settings=(
                    resolved_settings
                ),
                client=resolved_client,
            )
        )

    finished_at = datetime.now(
        timezone.utc
    )

    summary = {
        "pipeline_name": (
            "open_meteo_air_quality_transform"
        ),
        "source": "open_meteo",
        "storage_backend": "minio",
        "status": status,
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
            finished_at - started_at
        ).total_seconds(),
        "raw_status": raw_status,
        "raw_bucket": (
            resolved_settings.raw_bucket
        ),
        "raw_summary_object_name": (
            raw_summary_object_name
        ),
        "input_objects": len(
            successes
        ),
        "successful_objects": len(
            transformed_objects
        ),
        "failed_objects": len(
            failures
        ),
        "records_transformed": len(
            combined_dataframe
        ),
        "transformed_bucket": (
            resolved_settings.clean_bucket
        ),
        "transformed_object_name": (
            parquet_object_name
            if parquet_upload_result
            is not None
            else None
        ),
        "transformed_size_bytes": (
            parquet_upload_result[
                "size_bytes"
            ]
            if parquet_upload_result
            is not None
            else 0
        ),
        "transformed_objects": (
            transformed_objects
        ),
        "failures": failures,
        "summary_bucket": (
            resolved_settings.clean_bucket
        ),
        "summary_object_name": (
            summary_object_name
        ),
    }

    put_json_object(
        bucket_name=(
            resolved_settings.clean_bucket
        ),
        object_name=(
            summary_object_name
        ),
        data=summary,
        settings=resolved_settings,
        client=resolved_client,
    )

    return summary