from __future__ import annotations

from typing import Any

from src.utils.db import (
    DatabaseConfigurationError,
    DatabaseSettings,
    get_database_connection,
)


# Compatibility function retained because api.main and older tests may import it.
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings.from_environment()


def check_database_connection() -> dict[str, Any]:
    """Return the minimal health payload required by the FastAPI service."""

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    NOW() AS database_time,
                    current_database() AS database_name
                """
            )
            row = cursor.fetchone()

    if row is None:
        raise RuntimeError("Database không trả về kết quả.")

    return dict(row)


__all__ = [
    "DatabaseConfigurationError",
    "DatabaseSettings",
    "check_database_connection",
    "get_database_connection",
    "get_database_settings",
]
