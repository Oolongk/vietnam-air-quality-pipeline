import pytest

from src.utils.db import (
    DatabaseConfigurationError,
    DatabaseSettings,
)


def set_valid_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "POSTGRES_HOST",
        "localhost",
    )

    monkeypatch.setenv(
        "POSTGRES_PORT",
        "5433",
    )

    monkeypatch.setenv(
        "POSTGRES_DB",
        "air_quality_db",
    )

    monkeypatch.setenv(
        "POSTGRES_USER",
        "air_quality_user",
    )

    monkeypatch.setenv(
        "POSTGRES_PASSWORD",
        "test_password",
    )

    monkeypatch.setenv(
        "POSTGRES_CONNECT_TIMEOUT",
        "15",
    )


def test_database_settings_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_valid_environment(
        monkeypatch
    )

    settings = (
        DatabaseSettings.from_environment()
    )

    assert settings.host == "localhost"
    assert settings.port == 5433

    assert (
        settings.database
        == "air_quality_db"
    )

    assert (
        settings.user
        == "air_quality_user"
    )

    assert (
        settings.password
        == "test_password"
    )

    assert settings.connect_timeout == 15


def test_database_settings_reject_invalid_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_valid_environment(
        monkeypatch
    )

    monkeypatch.setenv(
        "POSTGRES_PORT",
        "not-a-number",
    )

    with pytest.raises(
        DatabaseConfigurationError,
        match="POSTGRES_PORT",
    ):
        DatabaseSettings.from_environment()


def test_database_settings_reject_empty_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_valid_environment(
        monkeypatch
    )

    monkeypatch.setenv(
        "POSTGRES_PASSWORD",
        "   ",
    )

    with pytest.raises(
        DatabaseConfigurationError,
        match="POSTGRES_PASSWORD",
    ):
        DatabaseSettings.from_environment()