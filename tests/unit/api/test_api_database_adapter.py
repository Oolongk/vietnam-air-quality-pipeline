from __future__ import annotations

from datetime import datetime, timezone

from api import database as api_database
from src.utils import db as shared_database


class FakeCursor:
    def __init__(self) -> None:
        self.executed_query = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query: str) -> None:
        self.executed_query = query

    def fetchone(self):
        return {
            "database_time": datetime(
                2026,
                7,
                29,
                tzinfo=timezone.utc,
            ),
            "database_name": "air_quality_db",
        }


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_api_reuses_shared_database_settings() -> None:
    assert api_database.DatabaseSettings is shared_database.DatabaseSettings
    assert (
        api_database.DatabaseConfigurationError
        is shared_database.DatabaseConfigurationError
    )


def test_api_health_database_query(monkeypatch) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(
        api_database,
        "get_database_connection",
        lambda: connection,
    )

    result = api_database.check_database_connection()

    assert result["database_name"] == "air_quality_db"
    assert "NOW()" in connection.cursor_instance.executed_query
