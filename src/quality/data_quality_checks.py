from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
    "us_aqi_nitrogen_dioxide",
    "us_aqi_carbon_monoxide",
    "us_aqi_ozone",
    "us_aqi_sulphur_dioxide",
)

REQUIRED_COLUMNS: set[str] = {
    "point_id",
    "location_id",
    "point_name",
    "point_type",
    "latitude",
    "longitude",
    "forecast_time",
    *POLLUTANT_COLUMNS,
    *AQI_COLUMNS,
    "source",
    "batch_id",
    "schema_version",
    "ingested_at",
}

DUPLICATE_KEY_COLUMNS: tuple[str, ...] = (
    "point_id",
    "forecast_time",
    "source",
)

TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "y",
}

CONFIG_POINT_COLUMNS: set[str] = {
    "point_id",
    "location_id",
    "point_name",
    "point_type",
    "latitude",
    "longitude",
    "is_active",
}

CONFIG_LOCATION_COLUMNS: set[str] = {
    "location_id",
    "location_name",
    "region",
    "admin_type",
    "is_active",
}


class DataQualitySchemaError(ValueError):
    """DataFrame dữ liệu thiếu schema bắt buộc."""


class DataQualityConfigurationError(ValueError):
    """File cấu hình Data Quality không hợp lệ."""


@dataclass
class DataQualityResult:
    valid_records: pd.DataFrame
    bad_records: pd.DataFrame
    row_checks: list[dict[str, Any]]
    batch_checks: list[dict[str, Any]]
    checked_at: str
    quality_status: str
    pipeline_status: str
    quality_score: float
    expected_records: int
    expected_active_points: int
    actual_active_points: int
    expected_forecast_hours: int

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

    @property
    def checks(self) -> list[dict[str, Any]]:
        return [
            *self.row_checks,
            *self.batch_checks,
        ]

    @property
    def passed_check_count(self) -> int:
        return sum(
            check.get("status") == "PASSED"
            for check in self.checks
        )

    @property
    def warning_check_count(self) -> int:
        return sum(
            check.get("status") == "WARNED"
            for check in self.checks
        )

    @property
    def failed_check_count(self) -> int:
        return sum(
            check.get("status") == "FAILED"
            for check in self.checks
        )


def _validate_required_columns(
    dataframe: pd.DataFrame,
) -> None:
    missing_columns = (
        REQUIRED_COLUMNS
        - set(dataframe.columns)
    )

    if missing_columns:
        raise DataQualitySchemaError(
            "DataFrame thiếu các cột bắt buộc: "
            + ", ".join(
                sorted(missing_columns)
            )
        )


def _validate_config_columns(
    dataframe: pd.DataFrame,
    required_columns: set[str],
    config_name: str,
) -> None:
    if not isinstance(
        dataframe,
        pd.DataFrame,
    ):
        raise DataQualityConfigurationError(
            f"{config_name} phải là Pandas DataFrame."
        )

    if dataframe.empty:
        raise DataQualityConfigurationError(
            f"{config_name} không có dòng dữ liệu."
        )

    missing_columns = (
        required_columns
        - set(dataframe.columns)
    )

    if missing_columns:
        raise DataQualityConfigurationError(
            f"{config_name} thiếu cột: "
            + ", ".join(
                sorted(missing_columns)
            )
        )


def _active_mask(
    series: pd.Series,
) -> pd.Series:
    if pd.api.types.is_bool_dtype(
        series.dtype
    ):
        return (
            series.fillna(False)
            .astype(bool)
        )

    return (
        series.astype("string")
        .str.strip()
        .str.lower()
        .isin(TRUE_VALUES)
        .fillna(False)
    )


def _blank_string_mask(
    series: pd.Series,
) -> pd.Series:
    values = series.astype("string")

    return (
        values.isna()
        | values.str.strip().eq("")
        .fillna(True)
    )


def _aware_datetime_mask(
    series: pd.Series,
) -> pd.Series:
    def is_aware(value: Any) -> bool:
        if value is None:
            return False

        try:
            if bool(pd.isna(value)):
                return False
        except (
            TypeError,
            ValueError,
        ):
            pass

        try:
            timestamp = pd.Timestamp(value)
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

    return series.map(is_aware)


def _required_numeric_invalid_mask(
    series: pd.Series,
) -> pd.Series:
    numeric_values = pd.to_numeric(
        series,
        errors="coerce",
    )

    return (
        series.isna()
        | numeric_values.isna()
    )


def _non_negative_invalid_mask(
    series: pd.Series,
) -> pd.Series:
    numeric_values = pd.to_numeric(
        series,
        errors="coerce",
    )

    return (
        series.isna()
        | numeric_values.isna()
        | numeric_values.lt(0)
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
        series.isna()
        | numeric_values.isna()
        | numeric_values.lt(minimum)
        | numeric_values.gt(maximum)
    )


def _prepare_active_configs(
    monitoring_points: pd.DataFrame,
    locations: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    _validate_config_columns(
        monitoring_points,
        CONFIG_POINT_COLUMNS,
        "monitoring_points.csv",
    )

    _validate_config_columns(
        locations,
        CONFIG_LOCATION_COLUMNS,
        "locations.csv",
    )

    active_points = (
        monitoring_points.loc[
            _active_mask(
                monitoring_points[
                    "is_active"
                ]
            )
        ]
        .copy()
        .reset_index(drop=True)
    )

    active_locations = (
        locations.loc[
            _active_mask(
                locations[
                    "is_active"
                ]
            )
        ]
        .copy()
        .reset_index(drop=True)
    )

    duplicate_point_count = int(
        active_points.duplicated(
            "point_id",
            keep=False,
        ).sum()
    )

    if duplicate_point_count:
        raise DataQualityConfigurationError(
            "monitoring_points.csv có point_id "
            "active bị trùng."
        )

    duplicate_location_count = int(
        active_locations.duplicated(
            "location_id",
            keep=False,
        ).sum()
    )

    if duplicate_location_count:
        raise DataQualityConfigurationError(
            "locations.csv có location_id "
            "active bị trùng."
        )

    active_location_ids = set(
        active_locations[
            "location_id"
        ]
        .astype("string")
        .str.strip()
        .dropna()
        .tolist()
    )

    orphan_points = (
        active_points.loc[
            ~active_points[
                "location_id"
            ]
            .astype("string")
            .str.strip()
            .isin(active_location_ids)
        ]
    )

    if not orphan_points.empty:
        orphan_ids = ", ".join(
            orphan_points[
                "point_id"
            ]
            .astype(str)
            .tolist()
        )

        raise DataQualityConfigurationError(
            "Monitoring point active tham chiếu "
            "location không active hoặc không tồn tại: "
            f"{orphan_ids}"
        )

    return (
        active_points,
        active_locations,
    )


def _calculate_quality_score(
    valid_percentage: float,
    batch_checks: list[dict[str, Any]],
) -> float:
    row_component = (
        max(
            0.0,
            min(
                100.0,
                valid_percentage,
            ),
        )
        * 0.70
    )

    weighted_total = 0.0
    weighted_earned = 0.0

    for check in batch_checks:
        severity = str(
            check.get(
                "severity",
                "ERROR",
            )
        ).upper()

        weight = (
            2.0
            if severity == "ERROR"
            else 1.0
        )

        status = str(
            check.get(
                "status",
                "FAILED",
            )
        ).upper()

        if status == "PASSED":
            earned = weight
        elif status == "WARNED":
            earned = weight * 0.5
        else:
            earned = 0.0

        weighted_total += weight
        weighted_earned += earned

    batch_percentage = (
        (
            weighted_earned
            / weighted_total
            * 100
        )
        if weighted_total
        else 100.0
    )

    return round(
        row_component
        + batch_percentage * 0.30,
        2,
    )


def run_air_quality_data_quality(
    dataframe: pd.DataFrame,
    monitoring_points: pd.DataFrame,
    locations: pd.DataFrame,
    expected_forecast_hours: int = 24,
    freshness_minutes: int = 90,
    coordinate_tolerance: float = 0.001,
    expected_batch_id: str | None = None,
) -> DataQualityResult:
    if not isinstance(
        dataframe,
        pd.DataFrame,
    ):
        raise TypeError(
            "dataframe phải là Pandas DataFrame."
        )

    if dataframe.empty:
        raise DataQualitySchemaError(
            "DataFrame không có record."
        )

    if (
        not isinstance(
            expected_forecast_hours,
            int,
        )
        or expected_forecast_hours <= 0
    ):
        raise ValueError(
            "expected_forecast_hours phải "
            "là số nguyên lớn hơn 0."
        )

    if (
        not isinstance(
            freshness_minutes,
            int,
        )
        or freshness_minutes <= 0
    ):
        raise ValueError(
            "freshness_minutes phải "
            "là số nguyên lớn hơn 0."
        )

    if coordinate_tolerance < 0:
        raise ValueError(
            "coordinate_tolerance không được âm."
        )

    _validate_required_columns(
        dataframe
    )

    (
        active_points,
        active_locations,
    ) = _prepare_active_configs(
        monitoring_points,
        locations,
    )

    working = (
        dataframe
        .copy()
        .reset_index(drop=True)
    )

    record_count = len(working)

    invalid_record_mask = pd.Series(
        False,
        index=working.index,
        dtype=bool,
    )

    row_error_codes: list[list[str]] = [
        []
        for _ in range(record_count)
    ]

    row_error_messages: list[list[str]] = [
        []
        for _ in range(record_count)
    ]

    row_checks: list[
        dict[str, Any]
    ] = []

    def apply_row_rule(
        check_name: str,
        message: str,
        invalid_mask: pd.Series,
        severity: str = "ERROR",
    ) -> None:
        nonlocal invalid_record_mask

        normalized_mask = (
            invalid_mask
            .reindex(
                working.index
            )
            .fillna(True)
            .astype(bool)
        )

        bad_count = int(
            normalized_mask.sum()
        )

        row_checks.append(
            {
                "check_name": check_name,
                "check_scope": "ROW",
                "severity": severity,
                "status": (
                    "PASSED"
                    if bad_count == 0
                    else "FAILED"
                ),
                "bad_records_count": bad_count,
                "message": message,
                "actual_value": bad_count,
                "expected_value": 0,
            }
        )

        invalid_record_mask = (
            invalid_record_mask
            | normalized_mask
        )

        for row_index in working.index[
            normalized_mask
        ]:
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

    for column_name in (
        "point_id",
        "location_id",
        "point_name",
        "point_type",
        "source",
        "batch_id",
        "schema_version",
    ):
        apply_row_rule(
            check_name=(
                f"{column_name.upper()}_REQUIRED"
            ),
            message=(
                f"{column_name} không được rỗng."
            ),
            invalid_mask=_blank_string_mask(
                working[column_name]
            ),
        )

    forecast_aware = (
        _aware_datetime_mask(
            working[
                "forecast_time"
            ]
        )
    )

    apply_row_rule(
        check_name="FORECAST_TIME_AWARE",
        message=(
            "forecast_time phải là datetime "
            "hợp lệ và có timezone."
        ),
        invalid_mask=~forecast_aware,
    )

    ingested_aware = (
        _aware_datetime_mask(
            working[
                "ingested_at"
            ]
        )
    )

    apply_row_rule(
        check_name="INGESTED_AT_AWARE",
        message=(
            "ingested_at phải là datetime "
            "hợp lệ và có timezone."
        ),
        invalid_mask=~ingested_aware,
    )

    for column_name in (
        *POLLUTANT_COLUMNS,
        *AQI_COLUMNS,
    ):
        apply_row_rule(
            check_name=(
                f"{column_name.upper()}_REQUIRED_NUMERIC"
            ),
            message=(
                f"{column_name} phải có giá trị số."
            ),
            invalid_mask=(
                _required_numeric_invalid_mask(
                    working[
                        column_name
                    ]
                )
            ),
        )

        apply_row_rule(
            check_name=(
                f"{column_name.upper()}_NON_NEGATIVE"
            ),
            message=(
                f"{column_name} phải lớn hơn "
                "hoặc bằng 0."
            ),
            invalid_mask=(
                _non_negative_invalid_mask(
                    working[
                        column_name
                    ]
                )
            ),
        )

    apply_row_rule(
        check_name="LATITUDE_RANGE",
        message=(
            "latitude phải là số trong "
            "khoảng -90 đến 90."
        ),
        invalid_mask=_range_invalid_mask(
            working["latitude"],
            -90,
            90,
        ),
    )

    apply_row_rule(
        check_name="LONGITUDE_RANGE",
        message=(
            "longitude phải là số trong "
            "khoảng -180 đến 180."
        ),
        invalid_mask=_range_invalid_mask(
            working["longitude"],
            -180,
            180,
        ),
    )

    normalized_source = (
        working["source"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    apply_row_rule(
        check_name="SOURCE_OPEN_METEO",
        message=(
            "source phải là open_meteo."
        ),
        invalid_mask=(
            normalized_source.isna()
            | normalized_source.ne(
                "open_meteo"
            )
            .fillna(True)
        ),
    )

    duplicate_mask = (
        working.duplicated(
            list(
                DUPLICATE_KEY_COLUMNS
            ),
            keep=False,
        )
    )

    apply_row_rule(
        check_name="UNIQUE_LOGICAL_KEY",
        message=(
            "Không được duplicate theo "
            "point_id + forecast_time + source."
        ),
        invalid_mask=duplicate_mask,
    )

    expected_point_ids = set(
        active_points[
            "point_id"
        ]
        .astype("string")
        .str.strip()
        .dropna()
        .tolist()
    )

    expected_location_ids = set(
        active_locations[
            "location_id"
        ]
        .astype("string")
        .str.strip()
        .dropna()
        .tolist()
    )

    normalized_point_id = (
        working["point_id"]
        .astype("string")
        .str.strip()
    )

    normalized_location_id = (
        working["location_id"]
        .astype("string")
        .str.strip()
    )

    apply_row_rule(
        check_name="KNOWN_ACTIVE_POINT_ID",
        message=(
            "point_id phải tồn tại và active "
            "trong monitoring_points.csv."
        ),
        invalid_mask=(
            normalized_point_id.isna()
            | ~normalized_point_id.isin(
                expected_point_ids
            )
        ),
    )

    apply_row_rule(
        check_name="KNOWN_ACTIVE_LOCATION_ID",
        message=(
            "location_id phải tồn tại và active "
            "trong locations.csv."
        ),
        invalid_mask=(
            normalized_location_id.isna()
            | ~normalized_location_id.isin(
                expected_location_ids
            )
        ),
    )

    point_location_map = (
        active_points
        .set_index("point_id")[
            "location_id"
        ]
        .astype("string")
        .str.strip()
        .to_dict()
    )

    expected_location_for_point = (
        normalized_point_id.map(
            point_location_map
        )
    )

    point_location_invalid = (
        expected_location_for_point.notna()
        & normalized_location_id.ne(
            expected_location_for_point
        )
    )

    apply_row_rule(
        check_name="POINT_LOCATION_MATCH",
        message=(
            "point_id phải thuộc đúng location_id "
            "trong monitoring_points.csv."
        ),
        invalid_mask=point_location_invalid,
    )

    expected_latitude_map = (
        active_points
        .set_index("point_id")[
            "latitude"
        ]
        .to_dict()
    )

    expected_longitude_map = (
        active_points
        .set_index("point_id")[
            "longitude"
        ]
        .to_dict()
    )

    latitude_numeric = pd.to_numeric(
        working["latitude"],
        errors="coerce",
    )

    longitude_numeric = pd.to_numeric(
        working["longitude"],
        errors="coerce",
    )

    expected_latitude = (
        normalized_point_id.map(
            expected_latitude_map
        )
    )

    expected_longitude = (
        normalized_point_id.map(
            expected_longitude_map
        )
    )

    coordinate_mismatch = (
        expected_latitude.notna()
        & expected_longitude.notna()
        & (
            (
                latitude_numeric
                - expected_latitude
            ).abs().gt(
                coordinate_tolerance
            )
            | (
                longitude_numeric
                - expected_longitude
            ).abs().gt(
                coordinate_tolerance
            )
        )
    )

    apply_row_rule(
        check_name="POINT_COORDINATE_MATCH",
        message=(
            "Tọa độ của point_id phải khớp "
            "monitoring_points.csv trong sai số "
            f"{coordinate_tolerance} độ."
        ),
        invalid_mask=coordinate_mismatch,
    )

    if expected_batch_id:
        normalized_expected_batch_id = (
            str(
                expected_batch_id
            ).strip()
        )

        apply_row_rule(
            check_name="BATCH_ID_MATCH",
            message=(
                "batch_id trong dữ liệu phải khớp "
                "Transform summary."
            ),
            invalid_mask=(
                working["batch_id"]
                .astype("string")
                .str.strip()
                .ne(
                    normalized_expected_batch_id
                )
                .fillna(True)
            ),
        )

    valid_records = (
        working.loc[
            ~invalid_record_mask
        ]
        .copy()
        .reset_index(drop=True)
    )

    bad_records = (
        working.loc[
            invalid_record_mask
        ]
        .copy()
    )

    if not bad_records.empty:
        bad_indices = (
            bad_records.index
            .tolist()
        )

        checked_at = datetime.now(
            timezone.utc
        ).isoformat()

        bad_records[
            "dq_status"
        ] = "FAILED"

        bad_records[
            "dq_checked_at"
        ] = checked_at

        bad_records[
            "dq_error_codes"
        ] = [
            "|".join(
                row_error_codes[
                    int(row_index)
                ]
            )
            for row_index in bad_indices
        ]

        bad_records[
            "dq_error_messages"
        ] = [
            " | ".join(
                row_error_messages[
                    int(row_index)
                ]
            )
            for row_index in bad_indices
        ]

        bad_records = (
            bad_records
            .reset_index(drop=True)
        )
    else:
        checked_at = datetime.now(
            timezone.utc
        ).isoformat()

    batch_checks: list[
        dict[str, Any]
    ] = []

    def add_batch_check(
        check_name: str,
        passed: bool,
        message: str,
        actual_value: Any,
        expected_value: Any,
        severity: str = "ERROR",
        bad_records_count: int = 0,
    ) -> None:
        normalized_severity = (
            severity.strip().upper()
        )

        if passed:
            status = "PASSED"
        elif (
            normalized_severity
            == "WARNING"
        ):
            status = "WARNED"
        else:
            status = "FAILED"

        batch_checks.append(
            {
                "check_name": check_name,
                "check_scope": "BATCH",
                "severity": (
                    normalized_severity
                ),
                "status": status,
                "bad_records_count": int(
                    bad_records_count
                ),
                "message": message,
                "actual_value": actual_value,
                "expected_value": expected_value,
            }
        )

    actual_point_ids = set(
        normalized_point_id
        .dropna()
        .loc[
            lambda values: (
                values.ne("")
            )
        ]
        .tolist()
    )

    missing_point_ids = sorted(
        expected_point_ids
        - actual_point_ids
    )

    unexpected_point_ids = sorted(
        actual_point_ids
        - expected_point_ids
    )

    add_batch_check(
        check_name="EXPECTED_ACTIVE_POINTS",
        passed=(
            not missing_point_ids
            and not unexpected_point_ids
        ),
        message=(
            "Batch phải chứa đúng toàn bộ "
            "monitoring point đang active."
        ),
        actual_value={
            "count": len(
                actual_point_ids
            ),
            "missing": (
                missing_point_ids
            ),
            "unexpected": (
                unexpected_point_ids
            ),
        },
        expected_value={
            "count": len(
                expected_point_ids
            ),
            "point_ids": sorted(
                expected_point_ids
            ),
        },
        bad_records_count=(
            len(missing_point_ids)
            + len(
                unexpected_point_ids
            )
        ),
    )

    expected_records = (
        len(expected_point_ids)
        * expected_forecast_hours
    )

    add_batch_check(
        check_name="EXPECTED_RECORD_COUNT",
        passed=(
            record_count
            == expected_records
        ),
        message=(
            "Số record phải bằng số point active "
            "nhân số giờ forecast."
        ),
        actual_value=record_count,
        expected_value=expected_records,
        bad_records_count=abs(
            record_count
            - expected_records
        ),
    )

    parsed_forecast_time = pd.to_datetime(
        working[
            "forecast_time"
        ],
        errors="coerce",
        utc=True,
    )

    forecast_count_frame = pd.DataFrame(
        {
            "point_id": (
                normalized_point_id
            ),
            "forecast_time": (
                parsed_forecast_time
            ),
        }
    ).dropna()

    hours_by_point = (
        forecast_count_frame
        .groupby(
            "point_id"
        )[
            "forecast_time"
        ]
        .nunique()
        .to_dict()
    )

    incomplete_points = {
        point_id: int(
            hours_by_point.get(
                point_id,
                0,
            )
        )
        for point_id in sorted(
            expected_point_ids
        )
        if int(
            hours_by_point.get(
                point_id,
                0,
            )
        )
        != expected_forecast_hours
    }

    add_batch_check(
        check_name="EXPECTED_FORECAST_HOURS_PER_POINT",
        passed=(
            not incomplete_points
        ),
        message=(
            "Mỗi monitoring point phải có đủ "
            f"{expected_forecast_hours} forecast hour."
        ),
        actual_value=(
            incomplete_points
            if incomplete_points
            else {
                "all_points": (
                    expected_forecast_hours
                )
            }
        ),
        expected_value=(
            expected_forecast_hours
        ),
        bad_records_count=(
            len(incomplete_points)
        ),
    )

    cadence_issues: dict[
        str,
        list[float]
    ] = {}

    for point_id, group in (
        forecast_count_frame
        .drop_duplicates(
            [
                "point_id",
                "forecast_time",
            ]
        )
        .sort_values(
            [
                "point_id",
                "forecast_time",
            ]
        )
        .groupby(
            "point_id"
        )
    ):
        differences = (
            group[
                "forecast_time"
            ]
            .diff()
            .dropna()
            .dt.total_seconds()
            .div(3600)
        )

        invalid_differences = (
            differences.loc[
                ~differences.eq(1.0)
            ]
            .round(3)
            .tolist()
        )

        if invalid_differences:
            cadence_issues[
                str(point_id)
            ] = invalid_differences

    add_batch_check(
        check_name="HOURLY_FORECAST_CADENCE",
        passed=(
            not cadence_issues
        ),
        message=(
            "forecast_time của từng point "
            "phải cách nhau đúng 1 giờ."
        ),
        actual_value=(
            cadence_issues
            if cadence_issues
            else "1 hour"
        ),
        expected_value="1 hour",
        bad_records_count=(
            len(cadence_issues)
        ),
    )

    distinct_batch_ids = sorted(
        working[
            "batch_id"
        ]
        .astype("string")
        .str.strip()
        .dropna()
        .loc[
            lambda values: (
                values.ne("")
            )
        ]
        .unique()
        .tolist()
    )

    add_batch_check(
        check_name="SINGLE_BATCH_ID",
        passed=(
            len(
                distinct_batch_ids
            )
            == 1
        ),
        message=(
            "Một transformed batch chỉ được "
            "chứa một batch_id."
        ),
        actual_value=distinct_batch_ids,
        expected_value=1,
        bad_records_count=max(
            0,
            len(
                distinct_batch_ids
            )
            - 1,
        ),
    )

    distinct_sources = sorted(
        normalized_source
        .dropna()
        .loc[
            lambda values: (
                values.ne("")
            )
        ]
        .unique()
        .tolist()
    )

    add_batch_check(
        check_name="SINGLE_SOURCE",
        passed=(
            distinct_sources
            == [
                "open_meteo"
            ]
        ),
        message=(
            "Batch chỉ được chứa source "
            "open_meteo."
        ),
        actual_value=distinct_sources,
        expected_value=[
            "open_meteo"
        ],
        bad_records_count=max(
            0,
            len(
                distinct_sources
            )
            - 1,
        ),
    )

    parsed_ingested_at = pd.to_datetime(
        working[
            "ingested_at"
        ],
        errors="coerce",
        utc=True,
    )

    valid_forecast_times = (
        parsed_forecast_time.dropna()
    )

    valid_ingested_times = (
        parsed_ingested_at.dropna()
    )

    if (
        valid_forecast_times.empty
        or valid_ingested_times.empty
    ):
        freshness_passed = False
        freshness_delay_minutes = None
    else:
        forecast_start = (
            valid_forecast_times.min()
        )

        ingestion_hour = (
            valid_ingested_times.max()
            .floor("h")
        )

        freshness_delay_minutes = round(
            abs(
                (
                    forecast_start
                    - ingestion_hour
                ).total_seconds()
            )
            / 60,
            2,
        )

        freshness_passed = (
            freshness_delay_minutes
            <= freshness_minutes
        )

    add_batch_check(
        check_name="DATA_FRESHNESS",
        passed=freshness_passed,
        message=(
            "Giờ bắt đầu forecast nên gần "
            "giờ ingestion của batch."
        ),
        actual_value=(
            freshness_delay_minutes
        ),
        expected_value=(
            f"<= {freshness_minutes} minutes"
        ),
        severity="WARNING",
        bad_records_count=(
            0
            if freshness_passed
            else 1
        ),
    )

    valid_percentage = round(
        (
            len(valid_records)
            / record_count
            * 100
        ),
        2,
    )

    quality_score = (
        _calculate_quality_score(
            valid_percentage,
            batch_checks,
        )
    )

    critical_batch_failed = any(
        (
            check.get(
                "severity"
            )
            == "ERROR"
            and check.get(
                "status"
            )
            == "FAILED"
        )
        for check in batch_checks
    )

    warning_present = any(
        check.get(
            "status"
        )
        == "WARNED"
        for check in batch_checks
    )

    if (
        critical_batch_failed
        or len(valid_records) == 0
    ):
        quality_status = "FAIL"
        pipeline_status = "FAILED"
    elif (
        len(bad_records) > 0
        or warning_present
    ):
        quality_status = "WARN"
        pipeline_status = (
            "PARTIAL_SUCCESS"
        )
    else:
        quality_status = "PASS"
        pipeline_status = "SUCCESS"

    if quality_status == "FAIL":
        quality_score = min(
            quality_score,
            69.99,
        )

    return DataQualityResult(
        valid_records=valid_records,
        bad_records=bad_records,
        row_checks=row_checks,
        batch_checks=batch_checks,
        checked_at=checked_at,
        quality_status=(
            quality_status
        ),
        pipeline_status=(
            pipeline_status
        ),
        quality_score=quality_score,
        expected_records=expected_records,
        expected_active_points=(
            len(expected_point_ids)
        ),
        actual_active_points=(
            len(
                actual_point_ids
                & expected_point_ids
            )
        ),
        expected_forecast_hours=(
            expected_forecast_hours
        ),
    )
