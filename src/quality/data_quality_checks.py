from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd


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

DUPLICATE_KEY_COLUMNS: tuple[str, ...] = (
    "point_id",
    "forecast_time",
    "source",
)

RULE_MESSAGES: dict[str, str] = {
    "POINT_ID_REQUIRED": (
        "point_id không được rỗng."
    ),
    "LOCATION_ID_REQUIRED": (
        "location_id không được rỗng."
    ),
    "FORECAST_TIME_REQUIRED": (
        "forecast_time phải là datetime hợp lệ."
    ),
    "PM2_5_NON_NEGATIVE": (
        "pm2_5 không được âm."
    ),
    "PM10_NON_NEGATIVE": (
        "pm10 không được âm."
    ),
    "US_AQI_NON_NEGATIVE": (
        "us_aqi không được âm."
    ),
    "LATITUDE_VALID": (
        "latitude phải là số trong khoảng "
        "-90 đến 90."
    ),
    "LONGITUDE_VALID": (
        "longitude phải là số trong khoảng "
        "-180 đến 180."
    ),
    "SOURCE_OPEN_METEO": (
        "source phải là 'open_meteo'."
    ),
    "UNIQUE_POINT_TIME_SOURCE": (
        "Không được duplicate theo "
        "point_id + forecast_time + source."
    ),
}


class DataQualitySchemaError(ValueError):
    """DataFrame thiếu cột bắt buộc để chạy Data Quality."""


@dataclass
class DataQualityResult:
    valid_records: pd.DataFrame
    bad_records: pd.DataFrame
    check_results: list[dict[str, Any]]
    checked_at: str

    @property
    def total_records(self) -> int:
        return (
            len(self.valid_records)
            + len(self.bad_records)
        )

    @property
    def valid_count(self) -> int:
        return len(self.valid_records)

    @property
    def bad_count(self) -> int:
        return len(self.bad_records)


def _validate_required_columns(
    dataframe: pd.DataFrame,
) -> None:
    missing_columns = (
        REQUIRED_COLUMNS
        - set(dataframe.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise DataQualitySchemaError(
            "DataFrame thiếu các cột bắt buộc: "
            f"{missing_text}"
        )


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


def _append_rule_errors(
    error_codes: list[list[str]],
    error_messages: list[list[str]],
    invalid_mask: pd.Series,
    rule_code: str,
) -> None:
    normalized_mask = (
        invalid_mask
        .fillna(False)
        .astype(bool)
        .reset_index(drop=True)
    )

    rule_message = RULE_MESSAGES[
        rule_code
    ]

    invalid_positions = normalized_mask[
        normalized_mask
    ].index

    for position in invalid_positions:
        error_codes[position].append(
            rule_code
        )

        error_messages[position].append(
            rule_message
        )


def _build_check_results(
    error_codes: list[list[str]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for rule_code, message in (
        RULE_MESSAGES.items()
    ):
        bad_records_count = sum(
            rule_code in row_codes
            for row_codes in error_codes
        )

        status = (
            "PASSED"
            if bad_records_count == 0
            else "FAILED"
        )

        results.append(
            {
                "check_name": rule_code,
                "status": status,
                "bad_records_count": (
                    bad_records_count
                ),
                "message": message,
            }
        )

    return results


def run_air_quality_data_quality(
    dataframe: pd.DataFrame,
) -> DataQualityResult:
    if not isinstance(
        dataframe,
        pd.DataFrame,
    ):
        raise TypeError(
            "dataframe phải là Pandas DataFrame."
        )

    _validate_required_columns(
        dataframe
    )

    working_dataframe = (
        dataframe
        .copy()
        .reset_index(drop=True)
    )

    record_count = len(
        working_dataframe
    )

    error_codes: list[list[str]] = [
        []
        for _ in range(record_count)
    ]

    error_messages: list[list[str]] = [
        []
        for _ in range(record_count)
    ]

    point_id_invalid = _blank_string_mask(
        working_dataframe["point_id"]
    )

    _append_rule_errors(
        error_codes=error_codes,
        error_messages=error_messages,
        invalid_mask=point_id_invalid,
        rule_code="POINT_ID_REQUIRED",
    )

    location_id_invalid = (
        _blank_string_mask(
            working_dataframe["location_id"]
        )
    )

    _append_rule_errors(
        error_codes=error_codes,
        error_messages=error_messages,
        invalid_mask=location_id_invalid,
        rule_code="LOCATION_ID_REQUIRED",
    )

    parsed_forecast_time = pd.to_datetime(
        working_dataframe[
            "forecast_time"
        ],
        errors="coerce",
        utc=True,
    )

    forecast_time_invalid = (
        parsed_forecast_time.isna()
    )

    _append_rule_errors(
        error_codes=error_codes,
        error_messages=error_messages,
        invalid_mask=(
            forecast_time_invalid
        ),
        rule_code=(
            "FORECAST_TIME_REQUIRED"
        ),
    )

    pm2_5_values = pd.to_numeric(
        working_dataframe["pm2_5"],
        errors="coerce",
    )

    pm2_5_negative = (
        pm2_5_values.lt(0)
        .fillna(False)
    )

    _append_rule_errors(
        error_codes=error_codes,
        error_messages=error_messages,
        invalid_mask=pm2_5_negative,
        rule_code="PM2_5_NON_NEGATIVE",
    )

    pm10_values = pd.to_numeric(
        working_dataframe["pm10"],
        errors="coerce",
    )

    pm10_negative = (
        pm10_values.lt(0)
        .fillna(False)
    )

    _append_rule_errors(
        error_codes=error_codes,
        error_messages=error_messages,
        invalid_mask=pm10_negative,
        rule_code="PM10_NON_NEGATIVE",
    )

    us_aqi_values = pd.to_numeric(
        working_dataframe["us_aqi"],
        errors="coerce",
    )

    us_aqi_negative = (
        us_aqi_values.lt(0)
        .fillna(False)
    )

    _append_rule_errors(
        error_codes=error_codes,
        error_messages=error_messages,
        invalid_mask=us_aqi_negative,
        rule_code="US_AQI_NON_NEGATIVE",
    )

    latitude_values = pd.to_numeric(
        working_dataframe["latitude"],
        errors="coerce",
    )

    latitude_invalid = (
        latitude_values.isna()
        | ~latitude_values.between(
            -90,
            90,
        )
    )

    _append_rule_errors(
        error_codes=error_codes,
        error_messages=error_messages,
        invalid_mask=latitude_invalid,
        rule_code="LATITUDE_VALID",
    )

    longitude_values = pd.to_numeric(
        working_dataframe["longitude"],
        errors="coerce",
    )

    longitude_invalid = (
        longitude_values.isna()
        | ~longitude_values.between(
            -180,
            180,
        )
    )

    _append_rule_errors(
        error_codes=error_codes,
        error_messages=error_messages,
        invalid_mask=longitude_invalid,
        rule_code="LONGITUDE_VALID",
    )

    normalized_source = (
        working_dataframe["source"]
        .astype("string")
        .str.strip()
    )

    source_invalid = (
        normalized_source.isna()
        | normalized_source.ne(
            "open_meteo"
        )
    )

    _append_rule_errors(
        error_codes=error_codes,
        error_messages=error_messages,
        invalid_mask=source_invalid,
        rule_code="SOURCE_OPEN_METEO",
    )

    duplicate_mask = (
        working_dataframe
        .duplicated(
            subset=list(
                DUPLICATE_KEY_COLUMNS
            ),
            keep=False,
        )
    )

    _append_rule_errors(
        error_codes=error_codes,
        error_messages=error_messages,
        invalid_mask=duplicate_mask,
        rule_code=(
            "UNIQUE_POINT_TIME_SOURCE"
        ),
    )

    valid_mask = pd.Series(
        [
            len(row_errors) == 0
            for row_errors in error_codes
        ]
    )

    valid_records = (
        working_dataframe[
            valid_mask
        ]
        .copy()
        .reset_index(drop=True)
    )

    bad_records = (
        working_dataframe[
            ~valid_mask
        ]
        .copy()
        .reset_index(drop=True)
    )

    bad_error_codes = [
        error_codes[index]
        for index in valid_mask[
            ~valid_mask
        ].index
    ]

    bad_error_messages = [
        error_messages[index]
        for index in valid_mask[
            ~valid_mask
        ].index
    ]

    checked_at = datetime.now(
        timezone.utc
    ).isoformat()

    if not bad_records.empty:
        bad_records["dq_status"] = (
            "FAILED"
        )

        bad_records["dq_checked_at"] = (
            checked_at
        )

        bad_records["dq_error_codes"] = [
            json.dumps(
                codes,
                ensure_ascii=False,
            )
            for codes in bad_error_codes
        ]

        bad_records[
            "dq_error_messages"
        ] = [
            json.dumps(
                messages,
                ensure_ascii=False,
            )
            for messages in (
                bad_error_messages
            )
        ]

    check_results = _build_check_results(
        error_codes
    )

    return DataQualityResult(
        valid_records=valid_records,
        bad_records=bad_records,
        check_results=check_results,
        checked_at=checked_at,
    )