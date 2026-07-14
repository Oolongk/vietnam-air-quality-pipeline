from __future__ import annotations

from dotenv import load_dotenv
import os
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

load_dotenv()

class DatabaseConfigurationError(
    RuntimeError
):
    """Cấu hình kết nối database không hợp lệ."""


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    database: str
    user: str
    password: str

    @classmethod
    def from_environment(
        cls,
    ) -> "DatabaseSettings":
        host = os.getenv(
            "POSTGRES_HOST",
            "localhost",
        ).strip()

        port_text = os.getenv(
            "POSTGRES_PORT",
            "5432",
        ).strip()

        database = os.getenv(
            "POSTGRES_DB",
            "",
        ).strip()

        user = os.getenv(
            "POSTGRES_USER",
            "",
        ).strip()

        password = os.getenv(
            "POSTGRES_PASSWORD",
            "",
        )

        missing_fields = []

        if not host:
            missing_fields.append(
                "POSTGRES_HOST"
            )

        if not database:
            missing_fields.append(
                "POSTGRES_DB"
            )

        if not user:
            missing_fields.append(
                "POSTGRES_USER"
            )

        if not password:
            missing_fields.append(
                "POSTGRES_PASSWORD"
            )

        try:
            port = int(
                port_text
            )
        except ValueError as error:
            raise DatabaseConfigurationError(
                "POSTGRES_PORT phải là số nguyên."
            ) from error

        if missing_fields:
            missing_text = ", ".join(
                missing_fields
            )

            raise DatabaseConfigurationError(
                "Thiếu biến môi trường: "
                f"{missing_text}"
            )

        return cls(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
        )

    def connect(
        self,
    ) -> psycopg.Connection[
        dict[str, Any]
    ]:
        return psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
            row_factory=dict_row,
            autocommit=True,
            connect_timeout=10,
        )


def get_database_settings() -> (
    DatabaseSettings
):
    return (
        DatabaseSettings
        .from_environment()
    )


def check_database_connection() -> dict[
    str,
    Any,
]:
    settings = get_database_settings()

    with settings.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    NOW() AS database_time,
                    current_database()
                        AS database_name
                """
            )

            row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            "Database không trả về kết quả."
        )

    return row