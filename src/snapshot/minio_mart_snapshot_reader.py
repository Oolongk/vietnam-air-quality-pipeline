from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Any

from minio import Minio
import numpy as np
import pandas as pd

from src.utils.minio_client import MinioSettings, get_minio_client
from src.utils.minio_object_io import (
    MinioObjectIOError,
    get_json_object,
    get_parquet_object,
    list_object_names,
)

MART_SUMMARY_PREFIX = "air_quality/build_summary"
MART_SUMMARY_SUFFIX = "/mart_summary.json"

CURRENT_AQI_REQUIRED_COLUMNS = {
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
    "pm2_5",
    "pm10",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
    "source",
    "source_batch_id",
    "schema_version",
    "source_ingested_at",
    "mart_created_at",
}

LOCATION_SUMMARY_REQUIRED_COLUMNS = {
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
}

DAILY_SUMMARY_REQUIRED_COLUMNS = {
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
}


class MartSnapshotReaderError(RuntimeError):
    """Không thể đọc một Mart snapshot nhất quán từ MinIO."""


class MartSnapshotValidationError(MartSnapshotReaderError):
    """Mart summary hoặc dataset không đúng contract."""


@dataclass(frozen=True)
class MartSnapshotBundle:
    summary_object_name: str
    summary: dict[str, Any]
    current_aqi: list[dict[str, Any]]
    location_summary: list[dict[str, Any]]
    daily_summary: list[dict[str, Any]]

    @property
    def batch_id(self) -> str:
        return str(self.summary["batch_id"])

    @property
    def generated_at(self) -> str:
        return str(
            self.summary.get("finished_at") or self.summary.get("started_at") or ""
        )

    @property
    def outputs(self) -> dict[str, str]:
        return dict(self.summary["outputs"])


class MinioMartSnapshotReader:
    """
    Đọc mart_summary.json trước, sau đó dùng outputs trong summary để đọc
    đúng ba Parquet thuộc cùng một batch.
    """

    def __init__(
        self,
        settings: MinioSettings | None = None,
        client: Minio | None = None,
        expected_batch_id: str | None = None,
    ) -> None:
        self.settings = settings or MinioSettings.from_environment()
        self.client = client or get_minio_client(self.settings)
        self.expected_batch_id = _normalize_optional_batch_id(expected_batch_id)

    def read(self) -> MartSnapshotBundle:
        summary_object_name, summary = self._read_summary()
        batch_id = _require_non_empty_string(summary, "batch_id")
        outputs = _require_outputs(summary, batch_id)

        current_dataframe = self._read_parquet(
            outputs["current_aqi"],
            dataset_name="current_aqi",
        )
        location_dataframe = self._read_parquet(
            outputs["location_summary"],
            dataset_name="location_summary",
        )
        daily_dataframe = self._read_parquet(
            outputs["daily_summary"],
            dataset_name="daily_summary",
        )

        _validate_dataframe(
            current_dataframe,
            dataset_name="current_aqi",
            required_columns=CURRENT_AQI_REQUIRED_COLUMNS,
            expected_rows=_require_non_negative_integer(summary, "current_aqi_rows"),
            unique_columns=("point_id",),
        )
        _validate_dataframe(
            location_dataframe,
            dataset_name="location_summary",
            required_columns=LOCATION_SUMMARY_REQUIRED_COLUMNS,
            expected_rows=_require_non_negative_integer(
                summary,
                "location_summary_rows",
            ),
            unique_columns=("location_id",),
        )
        _validate_dataframe(
            daily_dataframe,
            dataset_name="daily_summary",
            required_columns=DAILY_SUMMARY_REQUIRED_COLUMNS,
            expected_rows=_require_non_negative_integer(summary, "daily_summary_rows"),
            unique_columns=("forecast_date", "point_id"),
        )

        _validate_current_batch(current_dataframe, batch_id)

        current_records = _dataframe_to_records(current_dataframe)
        location_records = _dataframe_to_records(location_dataframe)
        daily_records = _dataframe_to_records(daily_dataframe)

        _add_current_compatibility_fields(current_records)
        _add_daily_compatibility_fields(daily_records)

        return MartSnapshotBundle(
            summary_object_name=summary_object_name,
            summary=summary,
            current_aqi=current_records,
            location_summary=location_records,
            daily_summary=daily_records,
        )

    def _read_summary(self) -> tuple[str, dict[str, Any]]:
        try:
            object_names = list_object_names(
                bucket_name=self.settings.mart_bucket,
                prefix=MART_SUMMARY_PREFIX,
                recursive=True,
                settings=self.settings,
                client=self.client,
            )
        except MinioObjectIOError as error:
            raise MartSnapshotReaderError(
                "Không thể liệt kê Mart build summary trên MinIO."
            ) from error

        candidates = sorted(
            (
                object_name
                for object_name in object_names
                if object_name.endswith(MART_SUMMARY_SUFFIX)
            ),
            reverse=True,
        )

        if self.expected_batch_id is not None:
            expected_segment = f"/batch_id={self.expected_batch_id}/"
            candidates = [
                object_name
                for object_name in candidates
                if expected_segment in f"/{object_name}"
            ]

        if not candidates:
            suffix = (
                f" cho batch_id={self.expected_batch_id}"
                if self.expected_batch_id is not None
                else ""
            )
            raise MartSnapshotReaderError(
                "Không tìm thấy mart_summary.json" + suffix + "."
            )

        validation_errors: list[str] = []
        for object_name in candidates:
            try:
                raw_summary = get_json_object(
                    bucket_name=self.settings.mart_bucket,
                    object_name=object_name,
                    settings=self.settings,
                    client=self.client,
                )
                summary = _validate_summary(
                    raw_summary,
                    object_name=object_name,
                    expected_batch_id=self.expected_batch_id,
                )
                return object_name, summary
            except (MinioObjectIOError, MartSnapshotValidationError) as error:
                validation_errors.append(f"{object_name}: {error}")

        raise MartSnapshotReaderError(
            "Không có Mart summary SUCCESS hợp lệ. " + " | ".join(validation_errors)
        )

    def _read_parquet(
        self,
        object_name: str,
        dataset_name: str,
    ) -> pd.DataFrame:
        try:
            return get_parquet_object(
                bucket_name=self.settings.mart_bucket,
                object_name=object_name,
                settings=self.settings,
                client=self.client,
            )
        except MinioObjectIOError as error:
            raise MartSnapshotReaderError(
                f"Không thể đọc dataset {dataset_name}: {object_name}"
            ) from error


def _normalize_optional_batch_id(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized:
        raise MartSnapshotValidationError("expected_batch_id không được rỗng.")
    if "/" in normalized or "\\" in normalized or ".." in normalized:
        raise MartSnapshotValidationError("expected_batch_id không an toàn.")
    return normalized


def _validate_summary(
    raw_summary: Any,
    object_name: str,
    expected_batch_id: str | None,
) -> dict[str, Any]:
    if not isinstance(raw_summary, dict):
        raise MartSnapshotValidationError("Mart summary phải là JSON object.")

    summary = dict(raw_summary)
    status = _require_non_empty_string(summary, "status").upper()
    if status != "SUCCESS":
        raise MartSnapshotValidationError(
            f"Mart summary không SUCCESS: status={status}."
        )

    batch_id = _require_non_empty_string(summary, "batch_id")
    if expected_batch_id is not None and batch_id != expected_batch_id:
        raise MartSnapshotValidationError(
            "Mart summary sai batch_id. "
            f"Expected={expected_batch_id}; actual={batch_id}."
        )

    expected_segment = f"/batch_id={batch_id}/"
    if expected_segment not in f"/{object_name}":
        raise MartSnapshotValidationError(
            "Đường dẫn mart_summary.json không khớp batch_id trong payload."
        )

    _require_outputs(summary, batch_id)
    _require_non_negative_integer(summary, "current_aqi_rows")
    _require_non_negative_integer(summary, "location_summary_rows")
    _require_non_negative_integer(summary, "daily_summary_rows")

    return summary


def _require_outputs(summary: dict[str, Any], batch_id: str) -> dict[str, str]:
    raw_outputs = summary.get("outputs")
    if not isinstance(raw_outputs, dict):
        raise MartSnapshotValidationError("Mart summary thiếu outputs object.")

    required_names = {
        "current_aqi",
        "location_summary",
        "daily_summary",
        "mart_summary",
    }
    missing_names = sorted(required_names - set(raw_outputs))
    if missing_names:
        raise MartSnapshotValidationError(
            "Mart summary thiếu output: " + ", ".join(missing_names)
        )

    expected_segment = f"/batch_id={batch_id}/"
    outputs: dict[str, str] = {}
    for output_name in sorted(required_names):
        object_name = raw_outputs.get(output_name)
        if not isinstance(object_name, str) or not object_name.strip():
            raise MartSnapshotValidationError(
                f"outputs.{output_name} phải là object path không rỗng."
            )
        normalized = object_name.replace("\\", "/").strip("/")
        if ".." in normalized or expected_segment not in f"/{normalized}":
            raise MartSnapshotValidationError(
                f"outputs.{output_name} không khớp batch_id={batch_id}."
            )
        outputs[output_name] = normalized

    return outputs


def _require_non_empty_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise MartSnapshotValidationError(
            f"Mart summary field {field_name} phải là string không rỗng."
        )
    return value.strip()


def _require_non_negative_integer(
    payload: dict[str, Any],
    field_name: str,
) -> int:
    value = payload.get(field_name)
    if isinstance(value, bool):
        raise MartSnapshotValidationError(
            f"Mart summary field {field_name} phải là số nguyên."
        )
    try:
        integer_value = int(value)
    except (TypeError, ValueError) as error:
        raise MartSnapshotValidationError(
            f"Mart summary field {field_name} phải là số nguyên."
        ) from error
    if integer_value < 0:
        raise MartSnapshotValidationError(
            f"Mart summary field {field_name} không được âm."
        )
    return integer_value


def _validate_dataframe(
    dataframe: pd.DataFrame,
    dataset_name: str,
    required_columns: set[str],
    expected_rows: int,
    unique_columns: tuple[str, ...],
) -> None:
    if not isinstance(dataframe, pd.DataFrame):
        raise MartSnapshotValidationError(
            f"Dataset {dataset_name} không phải DataFrame."
        )

    missing_columns = sorted(required_columns - set(dataframe.columns))
    if missing_columns:
        raise MartSnapshotValidationError(
            f"Dataset {dataset_name} thiếu cột: " + ", ".join(missing_columns)
        )

    actual_rows = len(dataframe)
    if actual_rows != expected_rows:
        raise MartSnapshotValidationError(
            f"Dataset {dataset_name} sai row count. "
            f"Expected={expected_rows}; actual={actual_rows}."
        )
    if actual_rows == 0:
        raise MartSnapshotValidationError(f"Dataset {dataset_name} đang rỗng.")

    duplicate_mask = dataframe.duplicated(
        subset=list(unique_columns),
        keep=False,
    )
    if bool(duplicate_mask.any()):
        raise MartSnapshotValidationError(
            f"Dataset {dataset_name} trùng logical key {unique_columns}."
        )


def _validate_current_batch(dataframe: pd.DataFrame, batch_id: str) -> None:
    batch_values = (
        dataframe["source_batch_id"]
        .astype("string")
        .fillna("")
        .str.strip()
        .drop_duplicates()
        .tolist()
    )
    if batch_values != [batch_id]:
        raise MartSnapshotValidationError(
            "current_aqi.source_batch_id không đồng nhất với Mart batch_id. "
            f"Expected={batch_id}; actual={batch_values}."
        )


def _dataframe_to_records(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_record in dataframe.to_dict(orient="records"):
        records.append(
            {str(key): _json_safe_value(value) for key, value in raw_record.items()}
        )
    return records


def _json_safe_value(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _add_current_compatibility_fields(records: list[dict[str, Any]]) -> None:
    for record in records:
        record.setdefault("batch_id", record.get("source_batch_id"))
        record.setdefault("ingested_at", record.get("source_ingested_at"))


def _add_daily_compatibility_fields(records: list[dict[str, Any]]) -> None:
    for record in records:
        record.setdefault(
            "forecast_time",
            record.get("worst_forecast_time") or record.get("last_forecast_time"),
        )
        record.setdefault("us_aqi", record.get("average_us_aqi"))
        record.setdefault("pm2_5", record.get("average_pm2_5"))
        record.setdefault("pm10", record.get("average_pm10"))
        record.setdefault("ozone", record.get("average_ozone"))
        record.setdefault("batch_id", record.get("worst_hour_source_batch_id"))
        record.setdefault("ingested_at", record.get("latest_source_ingested_at"))
