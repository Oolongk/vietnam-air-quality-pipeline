import pytest

from src.alerts.alert_rules import (
    AQIClassificationError,
    build_alert_message,
    classify_us_aqi,
)


@pytest.mark.parametrize(
    (
        "aqi_value",
        "expected_level",
        "expected_severity",
        "expected_alert",
    ),
    [
        (
            0,
            "Tốt",
            "GOOD",
            None,
        ),
        (
            50,
            "Tốt",
            "GOOD",
            None,
        ),
        (
            51,
            "Trung bình",
            "MODERATE",
            None,
        ),
        (
            100,
            "Trung bình",
            "MODERATE",
            None,
        ),
        (
            101,
            "Không tốt cho nhóm nhạy cảm",
            "UNHEALTHY_SENSITIVE",
            "MEDIUM",
        ),
        (
            150,
            "Không tốt cho nhóm nhạy cảm",
            "UNHEALTHY_SENSITIVE",
            "MEDIUM",
        ),
        (
            151,
            "Không tốt",
            "UNHEALTHY",
            "HIGH",
        ),
        (
            200,
            "Không tốt",
            "UNHEALTHY",
            "HIGH",
        ),
        (
            201,
            "Rất không tốt",
            "VERY_UNHEALTHY",
            "CRITICAL",
        ),
        (
            300,
            "Rất không tốt",
            "VERY_UNHEALTHY",
            "CRITICAL",
        ),
        (
            301,
            "Nguy hại",
            "HAZARDOUS",
            "CRITICAL",
        ),
    ],
)
def test_classify_aqi_boundaries(
    aqi_value: int,
    expected_level: str,
    expected_severity: str,
    expected_alert: str | None,
) -> None:
    result = classify_us_aqi(
        aqi_value
    )

    assert result is not None
    assert result.aqi_level == expected_level

    assert (
        result.aqi_severity
        == expected_severity
    )

    assert (
        result.alert_severity
        == expected_alert
    )


def test_classify_null_aqi_returns_none() -> None:
    assert classify_us_aqi(None) is None


def test_classify_rejects_negative_aqi() -> None:
    with pytest.raises(
        AQIClassificationError,
        match="âm",
    ):
        classify_us_aqi(-1)


def test_classify_rejects_fractional_aqi() -> None:
    with pytest.raises(
        AQIClassificationError,
        match="số nguyên",
    ):
        classify_us_aqi(100.5)


def test_build_alert_message() -> None:
    classification = classify_us_aqi(
        175
    )

    assert classification is not None

    message = build_alert_message(
        point_id="HN_CENTER",
        location_id="HN",
        classification=classification,
    )

    assert "HN_CENTER" in message
    assert "HN" in message
    assert "175" in message
    assert "Không tốt" in message