from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from minio import Minio

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


REQUIRED_COLUMNS: set[str] = {
    "point_id",
    "location_id",
    "forecast_time",
    "pm2_5",
    "pm10",
    "us_aqi",
    "latitude",
    "longitude",
    "source",
}


LOGICAL_KEY_COLUMNS: tuple[str, ...] = (
    "point_id",
    "forecast_time",
    "source",
)


class MinioDataQualityError(RuntimeError):
    """Lỗi khi chạy Data Quality trực tiếp trên MinIO."""


def _require_non_empty_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise MinioDataQualityError(
            f"{field_name} phải là chuỗi."
        )

    cleaned_value = value.strip()

    if not cleaned_value:
        raise MinioDataQualityError(
            f"{field_name} không được rỗng."
        )

    return cleaned_value


def _parse_aware_datetime(
    value: Any,
    field_name: str,
) -> datetime:
    if not isinstance(value, str):
        raise MinioDataQualityError(
            f"{field_name} phải là ISO datetime."
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
        raise MinioDataQualityError(
            f"{field_name} không hợp lệ: "
            f"{value!r}"
        ) from error

    if (
        parsed_value.tzinfo is None
        or parsed_value.utcoffset() is None
    ):
        raise MinioDataQualityError(
            f"{field_name} phải có timezone."
        )

    return parsed_value


def _missing_or_blank(
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


def _non_negative_invalid_mask(
    series: pd.Series,
) -> pd.Series:
    numeric_values = pd.to_numeric(
        series,
        errors="coerce",
    )

    value_present = (
        series.notna()
    )

    return (
        value_present
        & (
            numeric_values.isna()
            | numeric_values.lt(0)
        )
    )


def _range_invalid_mask(
    series: pd.Series,
    minimum: float,
    maximum: float,
) -> pd.Series:
    numeric_values = pd.to_numeric(
        series,
        errors="coerce",
    )

    return (
        numeric_values.isna()
        | numeric_values.lt(minimum)
        | numeric_values.gt(maximum)
    )


def _is_aware_datetime(
    value: Any,
) -> bool:
    if value is None:
        return False

    try:
        missing_value = pd.isna(
            value
        )

        if isinstance(
            missing_value,
            bool,
        ) and missing_value:
            return False
    except (
        TypeError,
        ValueError,
    ):
        pass

    try:
        timestamp = pd.Timestamp(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return False

    return (
        timestamp.tzinfo is not None
        and timestamp.utcoffset()
        is not None
    )


def _validate_dataframe_schema(
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
        raise MinioDataQualityError(
            "Transformed DataFrame không có record."
        )

    missing_columns = (
        REQUIRED_COLUMNS
        - set(dataframe.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise MinioDataQualityError(
            "Transformed DataFrame thiếu các cột: "
            f"{missing_text}"
        )

    return (
        dataframe
        .copy()
        .reset_index(drop=True)
    )


def evaluate_data_quality(
    dataframe: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    list[dict[str, Any]],
]:
    working_dataframe = (
        _validate_dataframe_schema(
            dataframe
        )
    )

    record_count = len(
        working_dataframe
    )

    invalid_record_mask = pd.Series(
        False,
        index=working_dataframe.index,
        dtype=bool,
    )

    row_error_codes: list[
        list[str]
    ] = [
        []
        for _ in range(record_count)
    ]

    row_error_messages: list[
        list[str]
    ] = [
        []
        for _ in range(record_count)
    ]

    check_results: list[
        dict[str, Any]
    ] = []

    def apply_rule(
        check_name: str,
        message: str,
        invalid_mask: pd.Series,
    ) -> None:
        nonlocal invalid_record_mask

        normalized_mask = (
            invalid_mask
            .reindex(
                working_dataframe.index
            )
            .fillna(True)
            .astype(bool)
        )

        bad_records_count = int(
            normalized_mask.sum()
        )

        check_results.append(
            {
                "check_name": check_name,
                "status": (
                    "PASSED"
                    if bad_records_count == 0
                    else "FAILED"
                ),
                "bad_records_count": (
                    bad_records_count
                ),
                "message": message,
            }
        )

        invalid_record_mask = (
            invalid_record_mask
            | normalized_mask
        )

        invalid_indices = (
            working_dataframe.index[
                normalized_mask
            ]
        )

        for row_index in invalid_indices:
            row_error_codes[
                int(row_index)
            ].append(
                check_name
            )

            row_error_messages[
                int(row_index)
            ].append(
                message
            )

    apply_rule(
        check_name="POINT_ID_REQUIRED",
        message=(
            "point_id không được rỗng."
        ),
        invalid_mask=_missing_or_blank(
            working_dataframe[
                "point_id"
            ]
        ),
    )

    apply_rule(
        check_name=(
            "LOCATION_ID_REQUIRED"
        ),
        message=(
            "location_id không được rỗng."
        ),
        invalid_mask=_missing_or_blank(
            working_dataframe[
                "location_id"
            ]
        ),
    )

    forecast_time_invalid = (
        ~working_dataframe[
            "forecast_time"
        ].map(
            _is_aware_datetime
        )
    )

    apply_rule(
        check_name=(
            "FORECAST_TIME_REQUIRED"
        ),
        message=(
            "forecast_time phải hợp lệ "
            "và có timezone."
        ),
        invalid_mask=(
            forecast_time_invalid
        ),
    )

    apply_rule(
        check_name=(
            "PM2_5_NON_NEGATIVE"
        ),
        message=(
            "pm2_5 phải là số không âm "
            "nếu có giá trị."
        ),
        invalid_mask=(
            _non_negative_invalid_mask(
                working_dataframe[
                    "pm2_5"
                ]
            )
        ),
    )

    apply_rule(
        check_name=(
            "PM10_NON_NEGATIVE"
        ),
        message=(
            "pm10 phải là số không âm "
            "nếu có giá trị."
        ),
        invalid_mask=(
            _non_negative_invalid_mask(
                working_dataframe[
                    "pm10"
                ]
            )
        ),
    )

    apply_rule(
        check_name=(
            "US_AQI_NON_NEGATIVE"
        ),
        message=(
            "us_aqi phải là số không âm "
            "nếu có giá trị."
        ),
        invalid_mask=(
            _non_negative_invalid_mask(
                working_dataframe[
                    "us_aqi"
                ]
            )
        ),
    )

    apply_rule(
        check_name="LATITUDE_RANGE",
        message=(
            "latitude phải nằm trong "
            "khoảng -90 đến 90."
        ),
        invalid_mask=(
            _range_invalid_mask(
                working_dataframe[
                    "latitude"
                ],
                minimum=-90,
                maximum=90,
            )
        ),
    )

    apply_rule(
        check_name="LONGITUDE_RANGE",
        message=(
            "longitude phải nằm trong "
            "khoảng -180 đến 180."
        ),
        invalid_mask=(
            _range_invalid_mask(
                working_dataframe[
                    "longitude"
                ],
                minimum=-180,
                maximum=180,
            )
        ),
    )

    source_values = (
        working_dataframe[
            "source"
        ]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    source_invalid = (
        source_values.isna()
        | source_values.ne(
            "open_meteo"
        )
        .fillna(True)
    )

    apply_rule(
        check_name=(
            "SOURCE_OPEN_METEO"
        ),
        message=(
            "source phải là open_meteo."
        ),
        invalid_mask=(
            source_invalid
        ),
    )

    duplicate_mask = (
        working_dataframe
        .duplicated(
            subset=list(
                LOGICAL_KEY_COLUMNS
            ),
            keep=False,
        )
    )

    apply_rule(
        check_name=(
            "UNIQUE_LOGICAL_KEY"
        ),
        message=(
            "Không được duplicate theo "
            "point_id + forecast_time + source."
        ),
        invalid_mask=(
            duplicate_mask
        ),
    )

    clean_dataframe = (
        working_dataframe.loc[
            ~invalid_record_mask
        ]
        .copy()
        .reset_index(drop=True)
    )

    bad_records_dataframe = (
        working_dataframe.loc[
            invalid_record_mask
        ]
        .copy()
    )

    if not bad_records_dataframe.empty:
        bad_indices = (
            bad_records_dataframe.index
            .tolist()
        )

        bad_records_dataframe[
            "dq_error_codes"
        ] = [
            "|".join(
                row_error_codes[
                    int(row_index)
                ]
            )
            for row_index in bad_indices
        ]

        bad_records_dataframe[
            "dq_error_messages"
        ] = [
            " | ".join(
                row_error_messages[
                    int(row_index)
                ]
            )
            for row_index in bad_indices
        ]

        bad_records_dataframe = (
            bad_records_dataframe
            .reset_index(drop=True)
        )

    return (
        clean_dataframe,
        bad_records_dataframe,
        check_results,
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


def find_latest_quality_candidate(
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
                resolved_settings
                .clean_bucket
            ),
            prefix=(
                TRANSFORMED_ROOT_PREFIX
            ),
            recursive=True,
            settings=resolved_settings,
            client=resolved_client,
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
            summary = get_json_object(
                bucket_name=(
                    resolved_settings
                    .clean_bucket
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
                resolved_settings
                .clean_bucket
            ),
            prefix=QUALITY_ROOT_PREFIX,
            recursive=True,
            settings=resolved_settings,
            client=resolved_client,
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
            summary = get_json_object(
                bucket_name=(
                    resolved_settings
                    .clean_bucket
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
    transform_summary: Mapping[str, Any],
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
            settings=resolved_settings,
            client=resolved_client,
        )
    )

    (
        clean_dataframe,
        bad_records_dataframe,
        check_results,
    ) = evaluate_data_quality(
        transformed_dataframe
    )

    input_records = len(
        transformed_dataframe
    )

    valid_records = len(
        clean_dataframe
    )

    bad_records = len(
        bad_records_dataframe
    )

    if bad_records == 0:
        status = "SUCCESS"
    elif valid_records > 0:
        status = "PARTIAL_SUCCESS"
    else:
        status = "FAILED"

    clean_prefix = build_clean_prefix(
        partition_date=partition_date,
        partition_hour=partition_hour,
        batch_id=batch_id,
    )

    quality_prefix = (
        build_quality_prefix(
            partition_date=partition_date,
            partition_hour=partition_hour,
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
                    clean_dataframe
                ),
                settings=resolved_settings,
                client=resolved_client,
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
        settings=resolved_settings,
        client=resolved_client,
    ):
        delete_object(
            bucket_name=(
                resolved_settings
                .clean_bucket
            ),
            object_name=(
                clean_object_name
            ),
            settings=resolved_settings,
            client=resolved_client,
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
                    bad_records_dataframe
                ),
                settings=resolved_settings,
                client=resolved_client,
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
        settings=resolved_settings,
        client=resolved_client,
    ):
        delete_object(
            bucket_name=(
                resolved_settings
                .clean_bucket
            ),
            object_name=(
                bad_records_object_name
            ),
            settings=resolved_settings,
            client=resolved_client,
        )

    finished_at = datetime.now(
        timezone.utc
    )

    valid_percentage = (
        round(
            (
                valid_records
                / input_records
                * 100
            ),
            2,
        )
        if input_records > 0
        else 0.0
    )

    summary = {
        "pipeline_name": (
            "open_meteo_air_quality_data_quality"
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
        "transform_bucket": (
            resolved_settings.clean_bucket
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
        "valid_records": (
            valid_records
        ),
        "bad_records": (
            bad_records
        ),
        "valid_percentage": (
            valid_percentage
        ),
        "checks": check_results,
        "clean_bucket": (
            resolved_settings.clean_bucket
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
            resolved_settings.clean_bucket
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