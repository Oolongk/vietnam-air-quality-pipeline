from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


class AQIClassificationError(ValueError):
    """Giá trị AQI không thể phân loại."""


@dataclass(frozen=True)
class AQIClassification:
    aqi_value: int
    aqi_level: str
    aqi_severity: str
    alert_severity: str | None


def _normalize_aqi_value(
    value: Any,
) -> int | None:
    if value is None or value is pd.NA:
        return None

    try:
        if bool(pd.isna(value)):
            return None
    except (
        TypeError,
        ValueError,
    ):
        pass

    try:
        numeric_value = float(value)
    except (
        TypeError,
        ValueError,
    ) as error:
        raise AQIClassificationError(
            f"AQI phải là số, nhận được: {value!r}"
        ) from error

    if not numeric_value.is_integer():
        raise AQIClassificationError(
            "AQI phải là số nguyên, "
            f"nhận được: {numeric_value}"
        )

    aqi_value = int(numeric_value)

    if aqi_value < 0:
        raise AQIClassificationError(
            "AQI không được âm."
        )

    return aqi_value


def classify_us_aqi(
    value: Any,
) -> AQIClassification | None:
    aqi_value = _normalize_aqi_value(
        value
    )

    if aqi_value is None:
        return None

    if aqi_value <= 50:
        return AQIClassification(
            aqi_value=aqi_value,
            aqi_level="Tốt",
            aqi_severity="GOOD",
            alert_severity=None,
        )

    if aqi_value <= 100:
        return AQIClassification(
            aqi_value=aqi_value,
            aqi_level="Trung bình",
            aqi_severity="MODERATE",
            alert_severity=None,
        )

    if aqi_value <= 150:
        return AQIClassification(
            aqi_value=aqi_value,
            aqi_level=(
                "Không tốt cho nhóm nhạy cảm"
            ),
            aqi_severity=(
                "UNHEALTHY_SENSITIVE"
            ),
            alert_severity="MEDIUM",
        )

    if aqi_value <= 200:
        return AQIClassification(
            aqi_value=aqi_value,
            aqi_level="Không tốt",
            aqi_severity="UNHEALTHY",
            alert_severity="HIGH",
        )

    if aqi_value <= 300:
        return AQIClassification(
            aqi_value=aqi_value,
            aqi_level="Rất không tốt",
            aqi_severity="VERY_UNHEALTHY",
            alert_severity="CRITICAL",
        )

    return AQIClassification(
        aqi_value=aqi_value,
        aqi_level="Nguy hại",
        aqi_severity="HAZARDOUS",
        alert_severity="CRITICAL",
    )


def build_alert_message(
    point_id: str,
    location_id: str,
    classification: AQIClassification,
) -> str:
    return (
        f"Cảnh báo chất lượng không khí: "
        f"{point_id} ({location_id}) có "
        f"US AQI={classification.aqi_value}, "
        f"mức '{classification.aqi_level}'."
    )