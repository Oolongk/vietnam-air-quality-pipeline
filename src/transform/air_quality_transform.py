from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


POLLUTANT_COLUMNS: tuple[str, ...] = (
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
)

HOURLY_COLUMNS: tuple[str, ...] = (
    *POLLUTANT_COLUMNS,
    *AQI_COLUMNS,
)

OUTPUT_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "source",
    "point_id",
    "location_id",
    "latitude",
    "longitude",
    "grid_latitude",
    "grid_longitude",
    "forecast_time",
    *POLLUTANT_COLUMNS,
    *AQI_COLUMNS,
    "timezone",
    "utc_offset_seconds",
    "ingested_at",
)


class AirQualityTransformError(ValueError):
    """Lỗi xảy ra khi chuyển Raw payload thành dữ liệu Clean."""


def _require_mapping(
    container: Mapping[str, Any],
    key: str,
    context: str,
) -> Mapping[str, Any]:
    value = container.get(key)

    if not isinstance(value, Mapping):
        raise AirQualityTransformError(
            f"{context} thiếu object '{key}' "
            "hoặc giá trị không phải JSON object."
        )

    return value


def _require_non_empty_string(
    container: Mapping[str, Any],
    key: str,
    context: str,
) -> str:
    value = container.get(key)

    if not isinstance(value, str):
        raise AirQualityTransformError(
            f"{context}.{key} phải là chuỗi."
        )

    cleaned_value = value.strip()

    if not cleaned_value:
        raise AirQualityTransformError(
            f"{context}.{key} không được rỗng."
        )

    return cleaned_value


def _require_number(
    container: Mapping[str, Any],
    key: str,
    context: str,
) -> float:
    value = container.get(key)

    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise AirQualityTransformError(
            f"{context}.{key} phải là số."
        ) from error


def _validate_hourly_arrays(
    hourly_data: Mapping[str, Any],
) -> int:
    time_values = hourly_data.get("time")

    if not isinstance(time_values, list):
        raise AirQualityTransformError(
            "response.hourly.time phải là một array."
        )

    if not time_values:
        raise AirQualityTransformError(
            "response.hourly.time không có dữ liệu."
        )

    expected_length = len(time_values)

    for column in HOURLY_COLUMNS:
        values = hourly_data.get(column)

        if not isinstance(values, list):
            raise AirQualityTransformError(
                f"response.hourly.{column} "
                "phải là một array."
            )

        if len(values) != expected_length:
            raise AirQualityTransformError(
                f"response.hourly.{column} có "
                f"{len(values)} phần tử nhưng "
                f"response.hourly.time có "
                f"{expected_length} phần tử."
            )

    return expected_length


def _parse_forecast_times(
    time_values: list[Any],
    timezone_name: str,
) -> pd.DatetimeIndex:
    try:
        parsed_times = pd.to_datetime(
            time_values,
            errors="raise",
        )
    except (TypeError, ValueError) as error:
        raise AirQualityTransformError(
            "Không thể chuyển hourly.time "
            "thành datetime."
        ) from error

    datetime_index = pd.DatetimeIndex(
        parsed_times
    )

    try:
        if datetime_index.tz is None:
            datetime_index = (
                datetime_index.tz_localize(
                    timezone_name,
                    ambiguous="raise",
                    nonexistent="raise",
                )
            )
        else:
            datetime_index = (
                datetime_index.tz_convert(
                    timezone_name
                )
            )
    except (TypeError, ValueError) as error:
        raise AirQualityTransformError(
            "Không thể áp dụng timezone "
            f"'{timezone_name}' cho forecast_time."
        ) from error

    return datetime_index


def _convert_pollutant_columns(
    dataframe: pd.DataFrame,
    hourly_data: Mapping[str, Any],
) -> None:
    for column in POLLUTANT_COLUMNS:
        numeric_values = pd.to_numeric(
            pd.Series(hourly_data[column]),
            errors="coerce",
        )

        dataframe[column] = (
            numeric_values.astype("Float64")
        )


def _convert_aqi_columns(
    dataframe: pd.DataFrame,
    hourly_data: Mapping[str, Any],
) -> None:
    for column in AQI_COLUMNS:
        numeric_values = pd.to_numeric(
            pd.Series(hourly_data[column]),
            errors="coerce",
        )

        try:
            dataframe[column] = (
                numeric_values.astype("Int64")
            )
        except (TypeError, ValueError) as error:
            raise AirQualityTransformError(
                f"Không thể chuyển '{column}' "
                "thành số nguyên."
            ) from error


def transform_open_meteo_payload(
    raw_payload: Mapping[str, Any],
) -> pd.DataFrame:
    if not isinstance(raw_payload, Mapping):
        raise AirQualityTransformError(
            "Raw payload phải là một JSON object."
        )

    schema_version = (
        _require_non_empty_string(
            raw_payload,
            "schema_version",
            "payload",
        )
    )

    source = _require_non_empty_string(
        raw_payload,
        "source",
        "payload",
    )

    if source != "open_meteo":
        raise AirQualityTransformError(
            "payload.source phải là "
            "'open_meteo'."
        )

    ingested_at_value = (
        _require_non_empty_string(
            raw_payload,
            "ingested_at",
            "payload",
        )
    )

    request_data = _require_mapping(
        raw_payload,
        "request",
        "payload",
    )

    response_data = _require_mapping(
        raw_payload,
        "response",
        "payload",
    )

    hourly_data = _require_mapping(
        response_data,
        "hourly",
        "response",
    )

    point_id = _require_non_empty_string(
        request_data,
        "point_id",
        "request",
    )

    location_id = _require_non_empty_string(
        request_data,
        "location_id",
        "request",
    )

    latitude = _require_number(
        request_data,
        "latitude",
        "request",
    )

    longitude = _require_number(
        request_data,
        "longitude",
        "request",
    )

    timezone_name = (
        _require_non_empty_string(
            request_data,
            "timezone",
            "request",
        )
    )

    grid_latitude = _require_number(
        response_data,
        "latitude",
        "response",
    )

    grid_longitude = _require_number(
        response_data,
        "longitude",
        "response",
    )

    record_count = _validate_hourly_arrays(
        hourly_data
    )

    forecast_times = _parse_forecast_times(
        time_values=hourly_data["time"],
        timezone_name=timezone_name,
    )

    try:
        ingested_at = pd.to_datetime(
            ingested_at_value,
            utc=True,
            errors="raise",
        )
    except (TypeError, ValueError) as error:
        raise AirQualityTransformError(
            "payload.ingested_at không phải "
            "datetime hợp lệ."
        ) from error

    dataframe = pd.DataFrame(
        {
            "forecast_time": forecast_times,
        }
    )

    _convert_pollutant_columns(
        dataframe=dataframe,
        hourly_data=hourly_data,
    )

    _convert_aqi_columns(
        dataframe=dataframe,
        hourly_data=hourly_data,
    )

    dataframe["schema_version"] = (
        schema_version
    )
    dataframe["source"] = source
    dataframe["point_id"] = point_id
    dataframe["location_id"] = location_id
    dataframe["latitude"] = latitude
    dataframe["longitude"] = longitude
    dataframe["grid_latitude"] = (
        grid_latitude
    )
    dataframe["grid_longitude"] = (
        grid_longitude
    )
    dataframe["timezone"] = timezone_name
    dataframe["utc_offset_seconds"] = int(
        response_data.get(
            "utc_offset_seconds",
            0,
        )
    )
    dataframe["ingested_at"] = ingested_at

    dataframe = dataframe.loc[
        :,
        list(OUTPUT_COLUMNS),
    ]

    dataframe = dataframe.sort_values(
        by=["point_id", "forecast_time"],
        ascending=True,
    ).reset_index(drop=True)

    if len(dataframe) != record_count:
        raise AirQualityTransformError(
            "Số record sau transform không bằng "
            "số timestamp trong Raw payload."
        )

    return dataframe