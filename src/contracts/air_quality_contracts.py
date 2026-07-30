from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal, Mapping

import pandas as pd

ContractType = Literal[
    "string",
    "number",
    "integer",
    "datetime",
    "date",
    "boolean",
]


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

CLEAN_HOURLY_COLUMNS: tuple[str, ...] = (
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
)

MART_SOURCE_REQUIRED_COLUMNS: tuple[str, ...] = (
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
    *POLLUTANT_COLUMNS,
)

MART_CURRENT_AQI_COLUMNS: tuple[str, ...] = (
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
    *POLLUTANT_COLUMNS,
    "source",
    "source_batch_id",
    "schema_version",
    "source_ingested_at",
    "mart_created_at",
)

MART_LOCATION_SUMMARY_COLUMNS: tuple[str, ...] = (
    "location_id",
    "location_name",
    "region",
    "monitoring_point_count",
    "forecast_time",
    "average_us_aqi",
    "minimum_us_aqi",
    "maximum_us_aqi",
    "average_pm2_5",
    "maximum_pm2_5",
    "average_pm10",
    "maximum_pm10",
    "average_ozone",
    "maximum_ozone",
    "latitude",
    "longitude",
    "source_batch_count",
    "worst_point_id",
    "worst_point_name",
    "worst_point_us_aqi",
    "aqi_level",
    "aqi_severity",
    "mart_created_at",
)

MART_DAILY_SUMMARY_COLUMNS: tuple[str, ...] = (
    "forecast_date",
    "point_id",
    "location_id",
    "location_name",
    "region",
    "point_name",
    "point_type",
    "latitude",
    "longitude",
    "first_forecast_time",
    "last_forecast_time",
    "available_hours",
    "average_us_aqi",
    "minimum_us_aqi",
    "maximum_us_aqi",
    "average_pm2_5",
    "maximum_pm2_5",
    "average_pm10",
    "maximum_pm10",
    "average_ozone",
    "maximum_ozone",
    "good_hours",
    "moderate_hours",
    "sensitive_group_hours",
    "unhealthy_hours",
    "very_unhealthy_hours",
    "hazardous_hours",
    "source_batch_count",
    "latest_source_ingested_at",
    "worst_forecast_time",
    "worst_hour_source_batch_id",
    "aqi_level",
    "aqi_severity",
    "coverage_status",
    "mart_created_at",
)

SNAPSHOT_AIR_QUALITY_RECORD_COLUMNS: tuple[str, ...] = (
    "point_id",
    "location_id",
    "point_name",
    "point_type",
    "location_name",
    "region",
    "admin_type",
    "latitude",
    "longitude",
    "forecast_time",
    *POLLUTANT_COLUMNS,
    *AQI_COLUMNS,
    "source",
    "batch_id",
    "schema_version",
    "ingested_at",
)

AQI_LEVEL_VALUES: tuple[str, ...] = (
    "Good",
    "Moderate",
    "Unhealthy for Sensitive Groups",
    "Unhealthy",
    "Very Unhealthy",
    "Hazardous",
)

POINT_TYPE_VALUES: tuple[str, ...] = (
    "urban_center",
    "regional_center",
)

COVERAGE_STATUS_VALUES: tuple[str, ...] = (
    "COMPLETE",
    "PARTIAL",
)


@dataclass(frozen=True)
class ContractIssue:
    code: str
    field: str | None
    message: str
    invalid_count: int = 0


class DataContractError(ValueError):
    """Raised when data violates a declared contract."""

    def __init__(
        self,
        contract_name: str,
        issues: list[ContractIssue],
    ) -> None:
        self.contract_name = contract_name
        self.issues = tuple(issues)

        details = "; ".join(
            (
                f"{issue.code}"
                + (f"[{issue.field}]" if issue.field else "")
                + f": {issue.message}"
            )
            for issue in issues
        )

        super().__init__(f"Contract {contract_name!r} failed: {details}")


@dataclass(frozen=True)
class ColumnContract:
    name: str
    data_type: ContractType
    nullable: bool = False
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: tuple[str, ...] = ()
    timezone_aware: bool = False
    description: str = ""


@dataclass(frozen=True)
class DataFrameContract:
    name: str
    version: str
    description: str
    columns: tuple[ColumnContract, ...]
    key_columns: tuple[str, ...] = ()
    allow_extra_columns: bool = False
    compatibility_policy: str = (
        "Backward-compatible additions require a "
        "minor version. Rename, removal, type change "
        "or semantic change requires a major version."
    )

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "key_columns": list(self.key_columns),
            "allow_extra_columns": (self.allow_extra_columns),
            "compatibility_policy": (self.compatibility_policy),
            "columns": [
                {
                    **asdict(column),
                    "allowed_values": list(column.allowed_values),
                }
                for column in self.columns
            ],
        }

    def validate(
        self,
        dataframe: pd.DataFrame,
        *,
        exact_columns: bool = True,
    ) -> list[ContractIssue]:
        issues: list[ContractIssue] = []

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            return [
                ContractIssue(
                    code="NOT_DATAFRAME",
                    field=None,
                    message=("Input must be a Pandas DataFrame."),
                )
            ]

        actual_columns = tuple(str(column) for column in dataframe.columns)
        actual_set = set(actual_columns)
        expected_set = set(self.column_names)

        missing_columns = sorted(expected_set - actual_set)
        if missing_columns:
            issues.append(
                ContractIssue(
                    code="MISSING_COLUMNS",
                    field=None,
                    message=", ".join(missing_columns),
                    invalid_count=len(missing_columns),
                )
            )

        if exact_columns and not self.allow_extra_columns:
            extra_columns = sorted(actual_set - expected_set)
            if extra_columns:
                issues.append(
                    ContractIssue(
                        code="EXTRA_COLUMNS",
                        field=None,
                        message=", ".join(extra_columns),
                        invalid_count=len(extra_columns),
                    )
                )

        if missing_columns:
            return issues

        for column in self.columns:
            issues.extend(
                _validate_column(
                    dataframe[column.name],
                    column,
                )
            )

        if self.key_columns:
            duplicate_mask = dataframe.duplicated(
                subset=list(self.key_columns),
                keep=False,
            )
            duplicate_count = int(duplicate_mask.sum())
            if duplicate_count:
                issues.append(
                    ContractIssue(
                        code="DUPLICATE_KEY",
                        field=",".join(self.key_columns),
                        message=("Logical key must be unique."),
                        invalid_count=(duplicate_count),
                    )
                )

        return issues

    def assert_valid(
        self,
        dataframe: pd.DataFrame,
        *,
        exact_columns: bool = True,
    ) -> None:
        issues = self.validate(
            dataframe,
            exact_columns=exact_columns,
        )
        if issues:
            raise DataContractError(
                self.name,
                issues,
            )


def _blank_mask(
    series: pd.Series,
) -> pd.Series:
    return series.isna() | series.astype("string").str.strip().eq("").fillna(True)


def _timezone_aware_mask(
    series: pd.Series,
) -> pd.Series:
    def is_aware(value: Any) -> bool:
        if value is None:
            return False

        try:
            if bool(pd.isna(value)):
                return False
        except (TypeError, ValueError):
            pass

        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError):
            return False

        return timestamp.tzinfo is not None and timestamp.utcoffset() is not None

    return series.map(is_aware)


def _validate_column(
    series: pd.Series,
    contract: ColumnContract,
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    null_mask = series.isna()

    if contract.data_type == "string":
        null_mask = _blank_mask(series)

    if not contract.nullable:
        null_count = int(null_mask.sum())
        if null_count:
            issues.append(
                ContractIssue(
                    code="NULL_NOT_ALLOWED",
                    field=contract.name,
                    message=("Null or blank values are not allowed."),
                    invalid_count=null_count,
                )
            )

    valid_source = series.loc[~null_mask]

    if valid_source.empty:
        return issues

    if contract.data_type == "string":
        invalid_type_mask = ~valid_source.map(
            lambda value: isinstance(
                value,
                str,
            )
        )
        invalid_type_count = int(invalid_type_mask.sum())
        if invalid_type_count:
            issues.append(
                ContractIssue(
                    code="INVALID_STRING",
                    field=contract.name,
                    message=(
                        "Values must remain strings. Do not allow CSV NA coercion."
                    ),
                    invalid_count=(invalid_type_count),
                )
            )

        normalized_values = valid_source.astype(str).str.strip()
        if contract.allowed_values:
            allowed_mask = normalized_values.isin(contract.allowed_values)
            invalid_count = int((~allowed_mask).sum())
            if invalid_count:
                issues.append(
                    ContractIssue(
                        code="VALUE_NOT_ALLOWED",
                        field=contract.name,
                        message=(
                            "Allowed values: " + ", ".join(contract.allowed_values)
                        ),
                        invalid_count=(invalid_count),
                    )
                )

    elif contract.data_type in {
        "number",
        "integer",
    }:
        numeric = pd.to_numeric(
            valid_source,
            errors="coerce",
        )
        invalid_numeric_mask = numeric.isna()
        invalid_numeric_count = int(invalid_numeric_mask.sum())
        if invalid_numeric_count:
            issues.append(
                ContractIssue(
                    code="INVALID_NUMBER",
                    field=contract.name,
                    message=("Values must be numeric."),
                    invalid_count=(invalid_numeric_count),
                )
            )

        valid_numeric = numeric.loc[~invalid_numeric_mask]

        if contract.data_type == "integer":
            integer_mask = valid_numeric.mod(1).eq(0)
            invalid_integer_count = int((~integer_mask).sum())
            if invalid_integer_count:
                issues.append(
                    ContractIssue(
                        code="INVALID_INTEGER",
                        field=contract.name,
                        message=("Values must be whole numbers."),
                        invalid_count=(invalid_integer_count),
                    )
                )

        if contract.minimum is not None:
            below_count = int(valid_numeric.lt(contract.minimum).sum())
            if below_count:
                issues.append(
                    ContractIssue(
                        code="BELOW_MINIMUM",
                        field=contract.name,
                        message=(f"Minimum is {contract.minimum}."),
                        invalid_count=below_count,
                    )
                )

        if contract.maximum is not None:
            above_count = int(valid_numeric.gt(contract.maximum).sum())
            if above_count:
                issues.append(
                    ContractIssue(
                        code="ABOVE_MAXIMUM",
                        field=contract.name,
                        message=(f"Maximum is {contract.maximum}."),
                        invalid_count=above_count,
                    )
                )

    elif contract.data_type == "datetime":
        parsed = pd.to_datetime(
            valid_source,
            errors="coerce",
            utc=False,
        )
        invalid_count = int(parsed.isna().sum())
        if invalid_count:
            issues.append(
                ContractIssue(
                    code="INVALID_DATETIME",
                    field=contract.name,
                    message=("Values must be valid datetimes."),
                    invalid_count=invalid_count,
                )
            )

        if contract.timezone_aware:
            aware_mask = _timezone_aware_mask(valid_source)
            aware_invalid_count = int((~aware_mask).sum())
            if aware_invalid_count:
                issues.append(
                    ContractIssue(
                        code="TIMEZONE_REQUIRED",
                        field=contract.name,
                        message=("Datetime must include timezone information."),
                        invalid_count=(aware_invalid_count),
                    )
                )

    elif contract.data_type == "date":

        def is_date_value(value: Any) -> bool:
            if isinstance(value, date):
                return True

            try:
                pd.Timestamp(value)
            except (TypeError, ValueError):
                return False

            return True

        invalid_count = int((~valid_source.map(is_date_value)).sum())
        if invalid_count:
            issues.append(
                ContractIssue(
                    code="INVALID_DATE",
                    field=contract.name,
                    message=("Values must be dates."),
                    invalid_count=invalid_count,
                )
            )

    elif contract.data_type == "boolean":
        invalid_count = int(
            (
                ~valid_source.map(
                    lambda value: isinstance(
                        value,
                        bool,
                    )
                )
            ).sum()
        )
        if invalid_count:
            issues.append(
                ContractIssue(
                    code="INVALID_BOOLEAN",
                    field=contract.name,
                    message=("Values must be booleans."),
                    invalid_count=invalid_count,
                )
            )

    return issues


def _string_column(
    name: str,
    *,
    allowed_values: tuple[str, ...] = (),
    nullable: bool = False,
    description: str = "",
) -> ColumnContract:
    return ColumnContract(
        name=name,
        data_type="string",
        nullable=nullable,
        allowed_values=allowed_values,
        description=description,
    )


def _number_column(
    name: str,
    *,
    unit: str | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    nullable: bool = False,
    description: str = "",
) -> ColumnContract:
    return ColumnContract(
        name=name,
        data_type="number",
        nullable=nullable,
        unit=unit,
        minimum=minimum,
        maximum=maximum,
        description=description,
    )


def _integer_column(
    name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    nullable: bool = False,
    description: str = "",
) -> ColumnContract:
    return ColumnContract(
        name=name,
        data_type="integer",
        nullable=nullable,
        minimum=minimum,
        maximum=maximum,
        description=description,
    )


def _datetime_column(
    name: str,
    *,
    nullable: bool = False,
    description: str = "",
) -> ColumnContract:
    return ColumnContract(
        name=name,
        data_type="datetime",
        nullable=nullable,
        timezone_aware=True,
        description=description,
    )


def _pollutant_contracts() -> tuple[
    ColumnContract,
    ...,
]:
    return tuple(
        _number_column(
            column,
            unit="µg/m³",
            minimum=0,
        )
        for column in POLLUTANT_COLUMNS
    )


def _aqi_contracts() -> tuple[
    ColumnContract,
    ...,
]:
    return tuple(
        _integer_column(
            column,
            minimum=0,
        )
        for column in AQI_COLUMNS
    )


CLEAN_HOURLY_CONTRACT = DataFrameContract(
    name="clean_air_quality_hourly",
    version="1.0",
    description=(
        "Canonical hourly clean record written to MinIO and loaded into TimescaleDB."
    ),
    key_columns=(
        "point_id",
        "forecast_time",
        "source",
    ),
    columns=(
        _string_column("point_id"),
        _string_column(
            "location_id",
            description=(
                "Must stay a string. The literal "
                "'NA' represents Nghệ An and must "
                "not become a missing value."
            ),
        ),
        _string_column("point_name"),
        _string_column(
            "point_type",
            allowed_values=POINT_TYPE_VALUES,
        ),
        _number_column(
            "latitude",
            unit="decimal_degree",
            minimum=-90,
            maximum=90,
        ),
        _number_column(
            "longitude",
            unit="decimal_degree",
            minimum=-180,
            maximum=180,
        ),
        _datetime_column(
            "forecast_time",
            description=("Timezone-aware forecast time."),
        ),
        *_pollutant_contracts(),
        *_aqi_contracts(),
        _string_column(
            "source",
            allowed_values=("open_meteo",),
        ),
        _string_column("batch_id"),
        _string_column(
            "schema_version",
            allowed_values=("1.0",),
        ),
        _datetime_column(
            "ingested_at",
            description=("Timezone-aware ingestion time, stored in UTC."),
        ),
    ),
)

MART_SOURCE_CONTRACT = DataFrameContract(
    name="mart_source_clean_hourly",
    version="1.0",
    description=("Minimum clean columns required by the MinIO mart builder."),
    allow_extra_columns=True,
    key_columns=(
        "point_id",
        "forecast_time",
        "source",
    ),
    columns=tuple(
        next(
            column for column in (CLEAN_HOURLY_CONTRACT.columns) if column.name == name
        )
        for name in (MART_SOURCE_REQUIRED_COLUMNS)
    ),
)

MART_CURRENT_AQI_CONTRACT = DataFrameContract(
    name="mart_current_aqi",
    version="1.0",
    description=(
        "Nearest forecast record per monitoring point for current AQI presentation."
    ),
    key_columns=("point_id",),
    columns=(
        _string_column("point_id"),
        _string_column("location_id"),
        _string_column("location_name"),
        _string_column("region"),
        _string_column("point_name"),
        _string_column(
            "point_type",
            allowed_values=POINT_TYPE_VALUES,
        ),
        _number_column(
            "latitude",
            minimum=-90,
            maximum=90,
            unit="decimal_degree",
        ),
        _number_column(
            "longitude",
            minimum=-180,
            maximum=180,
            unit="decimal_degree",
        ),
        _datetime_column("forecast_time"),
        _integer_column(
            "us_aqi",
            minimum=0,
        ),
        _string_column(
            "aqi_level",
            allowed_values=AQI_LEVEL_VALUES,
        ),
        _integer_column(
            "aqi_severity",
            minimum=1,
            maximum=6,
        ),
        *_pollutant_contracts(),
        _string_column(
            "source",
            allowed_values=("open_meteo",),
        ),
        _string_column("source_batch_id"),
        _string_column(
            "schema_version",
            allowed_values=("1.0",),
        ),
        _datetime_column("source_ingested_at"),
        _datetime_column("mart_created_at"),
    ),
)

MART_LOCATION_SUMMARY_CONTRACT = DataFrameContract(
    name="mart_location_summary",
    version="1.0",
    description=("One aggregated current AQI row per province-level location."),
    key_columns=("location_id",),
    columns=(
        _string_column("location_id"),
        _string_column("location_name"),
        _string_column("region"),
        _integer_column(
            "monitoring_point_count",
            minimum=1,
        ),
        _datetime_column("forecast_time"),
        _number_column(
            "average_us_aqi",
            minimum=0,
        ),
        _integer_column(
            "minimum_us_aqi",
            minimum=0,
        ),
        _integer_column(
            "maximum_us_aqi",
            minimum=0,
        ),
        _number_column(
            "average_pm2_5",
            minimum=0,
            unit="µg/m³",
        ),
        _number_column(
            "maximum_pm2_5",
            minimum=0,
            unit="µg/m³",
        ),
        _number_column(
            "average_pm10",
            minimum=0,
            unit="µg/m³",
        ),
        _number_column(
            "maximum_pm10",
            minimum=0,
            unit="µg/m³",
        ),
        _number_column(
            "average_ozone",
            minimum=0,
            unit="µg/m³",
        ),
        _number_column(
            "maximum_ozone",
            minimum=0,
            unit="µg/m³",
        ),
        _number_column(
            "latitude",
            minimum=-90,
            maximum=90,
            unit="decimal_degree",
        ),
        _number_column(
            "longitude",
            minimum=-180,
            maximum=180,
            unit="decimal_degree",
        ),
        _integer_column(
            "source_batch_count",
            minimum=1,
        ),
        _string_column("worst_point_id"),
        _string_column("worst_point_name"),
        _integer_column(
            "worst_point_us_aqi",
            minimum=0,
        ),
        _string_column(
            "aqi_level",
            allowed_values=AQI_LEVEL_VALUES,
        ),
        _integer_column(
            "aqi_severity",
            minimum=1,
            maximum=6,
        ),
        _datetime_column("mart_created_at"),
    ),
)

MART_DAILY_SUMMARY_CONTRACT = DataFrameContract(
    name="mart_daily_summary",
    version="1.0",
    description=("Daily point-level AQI and pollutant summary."),
    key_columns=(
        "forecast_date",
        "point_id",
    ),
    columns=(
        ColumnContract(
            name="forecast_date",
            data_type="date",
        ),
        _string_column("point_id"),
        _string_column("location_id"),
        _string_column("location_name"),
        _string_column("region"),
        _string_column("point_name"),
        _string_column(
            "point_type",
            allowed_values=POINT_TYPE_VALUES,
        ),
        _number_column(
            "latitude",
            minimum=-90,
            maximum=90,
            unit="decimal_degree",
        ),
        _number_column(
            "longitude",
            minimum=-180,
            maximum=180,
            unit="decimal_degree",
        ),
        _datetime_column("first_forecast_time"),
        _datetime_column("last_forecast_time"),
        _integer_column(
            "available_hours",
            minimum=1,
        ),
        _number_column(
            "average_us_aqi",
            minimum=0,
        ),
        _integer_column(
            "minimum_us_aqi",
            minimum=0,
        ),
        _integer_column(
            "maximum_us_aqi",
            minimum=0,
        ),
        _number_column(
            "average_pm2_5",
            minimum=0,
            unit="µg/m³",
        ),
        _number_column(
            "maximum_pm2_5",
            minimum=0,
            unit="µg/m³",
        ),
        _number_column(
            "average_pm10",
            minimum=0,
            unit="µg/m³",
        ),
        _number_column(
            "maximum_pm10",
            minimum=0,
            unit="µg/m³",
        ),
        _number_column(
            "average_ozone",
            minimum=0,
            unit="µg/m³",
        ),
        _number_column(
            "maximum_ozone",
            minimum=0,
            unit="µg/m³",
        ),
        *tuple(
            _integer_column(
                name,
                minimum=0,
            )
            for name in (
                "good_hours",
                "moderate_hours",
                "sensitive_group_hours",
                "unhealthy_hours",
                "very_unhealthy_hours",
                "hazardous_hours",
            )
        ),
        _integer_column(
            "source_batch_count",
            minimum=1,
        ),
        _datetime_column("latest_source_ingested_at"),
        _datetime_column("worst_forecast_time"),
        _string_column("worst_hour_source_batch_id"),
        _string_column(
            "aqi_level",
            allowed_values=AQI_LEVEL_VALUES,
        ),
        _integer_column(
            "aqi_severity",
            minimum=1,
            maximum=6,
        ),
        _string_column(
            "coverage_status",
            allowed_values=(COVERAGE_STATUS_VALUES),
        ),
        _datetime_column("mart_created_at"),
    ),
)

SNAPSHOT_AIR_QUALITY_RECORD_CONTRACT = DataFrameContract(
    name="snapshot_air_quality_record",
    version="1.0",
    description=("Public snapshot record returned by the latest air-quality endpoint."),
    key_columns=(
        "point_id",
        "forecast_time",
        "source",
    ),
    columns=(
        _string_column("point_id"),
        _string_column("location_id"),
        _string_column("point_name"),
        _string_column(
            "point_type",
            allowed_values=(POINT_TYPE_VALUES),
        ),
        _string_column("location_name"),
        _string_column("region"),
        _string_column("admin_type"),
        _number_column(
            "latitude",
            minimum=-90,
            maximum=90,
            unit="decimal_degree",
        ),
        _number_column(
            "longitude",
            minimum=-180,
            maximum=180,
            unit="decimal_degree",
        ),
        _datetime_column("forecast_time"),
        *_pollutant_contracts(),
        *_aqi_contracts(),
        _string_column(
            "source",
            allowed_values=("open_meteo",),
        ),
        _string_column("batch_id"),
        _string_column(
            "schema_version",
            allowed_values=("1.0",),
        ),
        _datetime_column("ingested_at"),
    ),
)

ALL_DATAFRAME_CONTRACTS: tuple[
    DataFrameContract,
    ...,
] = (
    CLEAN_HOURLY_CONTRACT,
    MART_SOURCE_CONTRACT,
    MART_CURRENT_AQI_CONTRACT,
    MART_LOCATION_SUMMARY_CONTRACT,
    MART_DAILY_SUMMARY_CONTRACT,
    SNAPSHOT_AIR_QUALITY_RECORD_CONTRACT,
)


def contract_catalog() -> dict[str, Any]:
    return {
        "catalog_version": "1.0",
        "project": ("vietnam-air-quality-pipeline"),
        "timezone_policy": {
            "forecast_time": (
                "Timezone-aware; source and clean records use Asia/Ho_Chi_Minh."
            ),
            "ingested_at": ("Timezone-aware and normalized to UTC."),
        },
        "identifier_policy": {
            "location_id": (
                "Always a string. The literal NA is a valid ID for Nghệ An."
            ),
            "batch_id": ("Immutable identifier for one pipeline ingestion batch."),
        },
        "contracts": [contract.to_dict() for contract in (ALL_DATAFRAME_CONTRACTS)],
    }


def _parse_aware_timestamp(
    value: Any,
) -> bool:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return False

    return timestamp.tzinfo is not None and timestamp.utcoffset() is not None


def validate_raw_envelope(
    payload: Mapping[str, Any],
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []

    if not isinstance(payload, Mapping):
        return [
            ContractIssue(
                code="RAW_NOT_OBJECT",
                field=None,
                message=("Raw payload must be a JSON object."),
            )
        ]

    for field in (
        "schema_version",
        "batch_id",
        "source",
        "extracted_at",
        "point",
        "api_response",
    ):
        if field not in payload:
            issues.append(
                ContractIssue(
                    code="RAW_FIELD_MISSING",
                    field=field,
                    message=("Required raw envelope field is missing."),
                )
            )

    if issues:
        return issues

    if payload.get("schema_version") != "1.0":
        issues.append(
            ContractIssue(
                code="RAW_SCHEMA_VERSION",
                field="schema_version",
                message=("Expected raw schema version 1.0."),
            )
        )

    if payload.get("source") != "open_meteo":
        issues.append(
            ContractIssue(
                code="RAW_SOURCE",
                field="source",
                message=("Expected source open_meteo."),
            )
        )

    batch_id = payload.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id.strip():
        issues.append(
            ContractIssue(
                code="RAW_BATCH_ID",
                field="batch_id",
                message=("batch_id must be a non-empty string."),
            )
        )

    if not _parse_aware_timestamp(payload.get("extracted_at")):
        issues.append(
            ContractIssue(
                code="RAW_EXTRACTED_AT",
                field="extracted_at",
                message=("extracted_at must be a timezone-aware timestamp."),
            )
        )

    point = payload.get("point")
    if not isinstance(point, Mapping):
        issues.append(
            ContractIssue(
                code="RAW_POINT_OBJECT",
                field="point",
                message=("point must be a JSON object."),
            )
        )
        return issues

    for field in (
        "point_id",
        "location_id",
        "point_name",
        "point_type",
        "latitude",
        "longitude",
    ):
        if field not in point:
            issues.append(
                ContractIssue(
                    code="RAW_POINT_FIELD_MISSING",
                    field=f"point.{field}",
                    message=("Required point field is missing."),
                )
            )

    for field in (
        "point_id",
        "location_id",
        "point_name",
        "point_type",
    ):
        value = point.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(
                ContractIssue(
                    code="RAW_POINT_STRING",
                    field=f"point.{field}",
                    message=("Value must be a non-empty string."),
                )
            )

    for field, minimum, maximum in (
        ("latitude", -90, 90),
        ("longitude", -180, 180),
    ):
        value = pd.to_numeric(
            pd.Series([point.get(field)]),
            errors="coerce",
        ).iloc[0]
        if pd.isna(value) or value < minimum or value > maximum:
            issues.append(
                ContractIssue(
                    code="RAW_COORDINATE_RANGE",
                    field=f"point.{field}",
                    message=(f"Value must be between {minimum} and {maximum}."),
                )
            )

    api_response = payload.get("api_response")
    if not isinstance(
        api_response,
        Mapping,
    ):
        issues.append(
            ContractIssue(
                code="RAW_API_RESPONSE",
                field="api_response",
                message=("api_response must be a JSON object."),
            )
        )
        return issues

    response = api_response.get(
        "response",
        api_response,
    )
    if not isinstance(response, Mapping):
        issues.append(
            ContractIssue(
                code="RAW_RESPONSE_OBJECT",
                field="api_response.response",
                message=("Open-Meteo response must be a JSON object."),
            )
        )
        return issues

    hourly = response.get("hourly")
    if not isinstance(hourly, Mapping):
        issues.append(
            ContractIssue(
                code="RAW_HOURLY_OBJECT",
                field=("api_response.response.hourly"),
                message=("hourly must be a JSON object."),
            )
        )
        return issues

    required_hourly = (
        "time",
        *POLLUTANT_COLUMNS,
        *AQI_COLUMNS,
    )
    time_values = hourly.get("time")
    if not isinstance(time_values, list) or not time_values:
        issues.append(
            ContractIssue(
                code="RAW_HOURLY_TIME",
                field="hourly.time",
                message=("hourly.time must be a non-empty list."),
            )
        )
        return issues

    expected_length = len(time_values)
    for field in required_hourly[1:]:
        values = hourly.get(field)
        if not isinstance(values, list):
            issues.append(
                ContractIssue(
                    code="RAW_HOURLY_FIELD",
                    field=f"hourly.{field}",
                    message=("Hourly variable must be a list."),
                )
            )
            continue

        if len(values) != expected_length:
            issues.append(
                ContractIssue(
                    code="RAW_HOURLY_LENGTH",
                    field=f"hourly.{field}",
                    message=("Hourly variable length must match hourly.time."),
                    invalid_count=abs(len(values) - expected_length),
                )
            )

    return issues


def assert_raw_envelope(
    payload: Mapping[str, Any],
) -> None:
    issues = validate_raw_envelope(payload)
    if issues:
        raise DataContractError(
            "raw_air_quality_envelope",
            issues,
        )


def validate_snapshot_payload(
    payload: Mapping[str, Any],
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []

    if not isinstance(payload, Mapping):
        return [
            ContractIssue(
                code="SNAPSHOT_NOT_OBJECT",
                field=None,
                message=("Snapshot payload must be a JSON object."),
            )
        ]

    for field in (
        "status",
        "record_count",
        "data",
    ):
        if field not in payload:
            issues.append(
                ContractIssue(
                    code=("SNAPSHOT_FIELD_MISSING"),
                    field=field,
                    message=("Required snapshot field is missing."),
                )
            )

    if issues:
        return issues

    if payload.get("status") != "SUCCESS":
        issues.append(
            ContractIssue(
                code="SNAPSHOT_STATUS",
                field="status",
                message=("Published snapshot status must be SUCCESS."),
            )
        )

    data = payload.get("data")
    if not isinstance(data, list):
        issues.append(
            ContractIssue(
                code="SNAPSHOT_DATA_LIST",
                field="data",
                message="data must be a list.",
            )
        )
        return issues

    record_count = payload.get("record_count")
    if not isinstance(record_count, int) or isinstance(record_count, bool):
        issues.append(
            ContractIssue(
                code="SNAPSHOT_RECORD_COUNT",
                field="record_count",
                message=("record_count must be an integer."),
            )
        )
    elif record_count != len(data):
        issues.append(
            ContractIssue(
                code=("SNAPSHOT_COUNT_MISMATCH"),
                field="record_count",
                message=("record_count must equal the number of data records."),
                invalid_count=abs(record_count - len(data)),
            )
        )

    invalid_record_count = sum(not isinstance(record, Mapping) for record in data)
    if invalid_record_count:
        issues.append(
            ContractIssue(
                code="SNAPSHOT_RECORD_OBJECT",
                field="data",
                message=("Every data item must be a JSON object."),
                invalid_count=(invalid_record_count),
            )
        )
        return issues

    if data:
        dataframe = pd.DataFrame(data)
        issues.extend(
            SNAPSHOT_AIR_QUALITY_RECORD_CONTRACT.validate(
                dataframe,
                exact_columns=True,
            )
        )

        batch_id = payload.get("batch_id")
        if not isinstance(batch_id, str) or not batch_id.strip():
            issues.append(
                ContractIssue(
                    code="SNAPSHOT_BATCH_ID",
                    field="batch_id",
                    message=("Non-empty data requires a non-empty batch_id."),
                )
            )

    return issues


def assert_snapshot_payload(
    payload: Mapping[str, Any],
) -> None:
    issues = validate_snapshot_payload(payload)
    if issues:
        raise DataContractError(
            "snapshot_latest_air_quality",
            issues,
        )
