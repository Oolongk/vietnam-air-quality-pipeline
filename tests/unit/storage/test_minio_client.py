import pytest

from src.utils.minio_client import (
    MinioConfigurationError,
    MinioSettings,
    normalize_object_name,
)


def set_valid_minio_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MINIO_ENDPOINT",
        "localhost:9000",
    )

    monkeypatch.setenv(
        "MINIO_ACCESS_KEY",
        "testaccess",
    )

    monkeypatch.setenv(
        "MINIO_SECRET_KEY",
        "testsecret",
    )

    monkeypatch.setenv(
        "MINIO_SECURE",
        "false",
    )

    monkeypatch.setenv(
        "MINIO_RAW_BUCKET",
        "air-quality-raw",
    )

    monkeypatch.setenv(
        "MINIO_CLEAN_BUCKET",
        "air-quality-clean",
    )

    monkeypatch.setenv(
        "MINIO_MART_BUCKET",
        "air-quality-mart",
    )


def test_loads_minio_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_valid_minio_environment(
        monkeypatch
    )

    settings = (
        MinioSettings.from_environment()
    )

    assert (
        settings.endpoint
        == "localhost:9000"
    )

    assert settings.secure is False

    assert settings.bucket_names == (
        "air-quality-raw",
        "air-quality-clean",
        "air-quality-mart",
    )


def test_rejects_endpoint_with_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_valid_minio_environment(
        monkeypatch
    )

    monkeypatch.setenv(
        "MINIO_ENDPOINT",
        "http://localhost:9000",
    )

    with pytest.raises(
        MinioConfigurationError,
        match="http://",
    ):
        MinioSettings.from_environment()


def test_rejects_invalid_bucket_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_valid_minio_environment(
        monkeypatch
    )

    monkeypatch.setenv(
        "MINIO_RAW_BUCKET",
        "Air_Quality_Raw",
    )

    with pytest.raises(
        MinioConfigurationError,
        match="Bucket name",
    ):
        MinioSettings.from_environment()


def test_normalizes_windows_object_path() -> None:
    result = normalize_object_name(
        r"open_meteo\air_quality\data.json"
    )

    assert result == (
        "open_meteo/"
        "air_quality/"
        "data.json"
    )