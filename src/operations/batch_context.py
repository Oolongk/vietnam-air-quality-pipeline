from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from os import environ as process_environment
from re import fullmatch
from typing import Any, Mapping
from zoneinfo import ZoneInfo

BATCH_ID_ENV = "PIPELINE_BATCH_ID"
PARTITION_DATE_ENV = "PIPELINE_PARTITION_DATE"
PARTITION_HOUR_ENV = "PIPELINE_PARTITION_HOUR"
STARTED_AT_ENV = "PIPELINE_STARTED_AT"

BATCH_CONTEXT_ENV_NAMES: tuple[str, ...] = (
    BATCH_ID_ENV,
    PARTITION_DATE_ENV,
    PARTITION_HOUR_ENV,
    STARTED_AT_ENV,
)

BATCH_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
LOCAL_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


class PipelineBatchContextError(ValueError):
    """Batch context is missing, inconsistent, or unsafe."""


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise PipelineBatchContextError(f"{field_name} phải là chuỗi.")

    normalized = value.strip()
    if not normalized:
        raise PipelineBatchContextError(f"{field_name} không được rỗng.")

    return normalized


def _parse_started_at(value: Any) -> datetime:
    normalized = _require_text(value, STARTED_AT_ENV).replace("Z", "+00:00")

    try:
        started_at = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise PipelineBatchContextError(
            f"{STARTED_AT_ENV} phải là ISO datetime hợp lệ."
        ) from error

    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise PipelineBatchContextError(f"{STARTED_AT_ENV} phải có timezone.")

    return started_at


@dataclass(frozen=True, slots=True)
class PipelineBatchContext:
    batch_id: str
    partition_date: str
    partition_hour: str
    started_at: datetime

    @classmethod
    def from_values(
        cls,
        *,
        batch_id: Any,
        partition_date: Any,
        partition_hour: Any,
        started_at: Any,
    ) -> PipelineBatchContext:
        normalized_batch_id = _require_text(batch_id, BATCH_ID_ENV)
        if fullmatch(BATCH_ID_PATTERN, normalized_batch_id) is None:
            raise PipelineBatchContextError(
                f"{BATCH_ID_ENV} chỉ được chứa chữ, số, dấu chấm, gạch dưới "
                "hoặc gạch ngang; tối đa 128 ký tự."
            )

        normalized_partition_date = _require_text(
            partition_date,
            PARTITION_DATE_ENV,
        )
        try:
            datetime.strptime(normalized_partition_date, "%Y-%m-%d")
        except ValueError as error:
            raise PipelineBatchContextError(
                f"{PARTITION_DATE_ENV} phải có định dạng YYYY-MM-DD."
            ) from error

        normalized_partition_hour = _require_text(
            partition_hour,
            PARTITION_HOUR_ENV,
        )
        if fullmatch(r"(?:[01][0-9]|2[0-3])", normalized_partition_hour) is None:
            raise PipelineBatchContextError(
                f"{PARTITION_HOUR_ENV} phải nằm trong khoảng 00-23."
            )

        normalized_started_at = _parse_started_at(started_at)
        local_started_at = normalized_started_at.astimezone(LOCAL_TIMEZONE)

        actual_partition_date = local_started_at.strftime("%Y-%m-%d")
        actual_partition_hour = local_started_at.strftime("%H")

        if actual_partition_date != normalized_partition_date:
            raise PipelineBatchContextError(
                "Partition date không khớp PIPELINE_STARTED_AT theo timezone "
                "Asia/Ho_Chi_Minh. "
                f"Expected={actual_partition_date}; "
                f"actual={normalized_partition_date}."
            )

        if actual_partition_hour != normalized_partition_hour:
            raise PipelineBatchContextError(
                "Partition hour không khớp PIPELINE_STARTED_AT theo timezone "
                "Asia/Ho_Chi_Minh. "
                f"Expected={actual_partition_hour}; "
                f"actual={normalized_partition_hour}."
            )

        return cls(
            batch_id=normalized_batch_id,
            partition_date=normalized_partition_date,
            partition_hour=normalized_partition_hour,
            started_at=normalized_started_at,
        )

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        required: bool = False,
    ) -> PipelineBatchContext | None:
        source = environment if environment is not None else process_environment
        values = {name: source.get(name) for name in BATCH_CONTEXT_ENV_NAMES}
        present_names = [name for name, value in values.items() if value is not None]

        if not present_names:
            if required:
                raise PipelineBatchContextError(
                    "Thiếu Airflow batch context: " + ", ".join(BATCH_CONTEXT_ENV_NAMES)
                )
            return None

        missing_names = [name for name, value in values.items() if value is None]
        if missing_names:
            raise PipelineBatchContextError(
                "Batch context chỉ được cấu hình một phần. Thiếu: "
                + ", ".join(missing_names)
            )

        return cls.from_values(
            batch_id=values[BATCH_ID_ENV],
            partition_date=values[PARTITION_DATE_ENV],
            partition_hour=values[PARTITION_HOUR_ENV],
            started_at=values[STARTED_AT_ENV],
        )

    def validate_summary(
        self,
        summary: Mapping[str, Any],
        summary_name: str,
    ) -> None:
        if not isinstance(summary, Mapping):
            raise PipelineBatchContextError(f"{summary_name} phải là JSON object.")

        expected_values = {
            "batch_id": self.batch_id,
            "partition_date": self.partition_date,
            "partition_hour": self.partition_hour,
        }

        for field_name, expected_value in expected_values.items():
            actual_value = str(summary.get(field_name, "")).strip()
            if actual_value != expected_value:
                raise PipelineBatchContextError(
                    f"{summary_name} không khớp {field_name}. "
                    f"Expected={expected_value}; actual={actual_value or 'EMPTY'}."
                )

    def as_dict(self) -> dict[str, str]:
        return {
            "batch_id": self.batch_id,
            "partition_date": self.partition_date,
            "partition_hour": self.partition_hour,
            "started_at": self.started_at.isoformat(),
        }
