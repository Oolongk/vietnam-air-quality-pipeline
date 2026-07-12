from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


class DatabaseConfigurationError(
    ValueError
):
    """Cấu hình kết nối database không hợp lệ."""


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    database: str
    user: str
    password: str
    connect_timeout: int = 10

    @classmethod
    def from_environment(
        cls,
    ) -> "DatabaseSettings":
        load_dotenv()

        host = _get_required_environment(
            "POSTGRES_HOST"
        )

        database = (
            _get_required_environment(
                "POSTGRES_DB"
            )
        )

        user = _get_required_environment(
            "POSTGRES_USER"
        )

        password = (
            _get_required_environment(
                "POSTGRES_PASSWORD"
            )
        )

        port = _get_integer_environment(
            name="POSTGRES_PORT",
            default=5432,
            minimum=1,
            maximum=65535,
        )

        connect_timeout = (
            _get_integer_environment(
                name=(
                    "POSTGRES_CONNECT_TIMEOUT"
                ),
                default=10,
                minimum=1,
                maximum=300,
            )
        )

        return cls(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            connect_timeout=connect_timeout,
        )

    def connection_parameters(
        self,
    ) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.database,
            "user": self.user,
            "password": self.password,
            "connect_timeout": (
                self.connect_timeout
            ),
            "application_name": (
                "vietnam_air_quality_pipeline"
            ),
        }


def _get_required_environment(
    name: str,
) -> str:
    value = os.getenv(name)

    if value is None:
        raise DatabaseConfigurationError(
            f"Thiếu biến môi trường: {name}"
        )

    cleaned_value = value.strip()

    if not cleaned_value:
        raise DatabaseConfigurationError(
            f"Biến môi trường {name} "
            "không được rỗng."
        )

    return cleaned_value


def _get_integer_environment(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(
        name,
        str(default),
    )

    try:
        value = int(raw_value)
    except ValueError as error:
        raise DatabaseConfigurationError(
            f"{name} phải là số nguyên."
        ) from error

    if not minimum <= value <= maximum:
        raise DatabaseConfigurationError(
            f"{name} phải nằm trong khoảng "
            f"{minimum} đến {maximum}."
        )

    return value


def get_database_connection(
    settings: DatabaseSettings | None = None,
) -> psycopg.Connection:
    resolved_settings = (
        settings
        or DatabaseSettings.from_environment()
    )

    return psycopg.connect(
        **resolved_settings.connection_parameters(),
        row_factory=dict_row,
    )


def check_database_connection(
) -> dict[str, Any]:
    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_database()
                        AS database_name,
                    current_user
                        AS database_user,
                    current_setting(
                        'server_version'
                    )
                        AS postgres_version,
                    (
                        SELECT extversion
                        FROM pg_extension
                        WHERE extname = 'timescaledb'
                    )
                        AS timescaledb_version;
                """
            )

            server_info = cursor.fetchone()

            cursor.execute(
                """
                SELECT COUNT(*) AS location_count
                FROM dim_location;
                """
            )

            location_info = cursor.fetchone()

            cursor.execute(
                """
                SELECT COUNT(*) AS point_count
                FROM dim_monitoring_point;
                """
            )

            point_info = cursor.fetchone()

            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM
                        timescaledb_information
                        .hypertables
                    WHERE hypertable_name =
                        'fact_air_quality_hourly'
                ) AS is_hypertable;
                """
            )

            hypertable_info = cursor.fetchone()

    if server_info is None:
        raise RuntimeError(
            "Database không trả thông tin server."
        )

    if location_info is None:
        raise RuntimeError(
            "Không đọc được số location."
        )

    if point_info is None:
        raise RuntimeError(
            "Không đọc được số monitoring point."
        )

    if hypertable_info is None:
        raise RuntimeError(
            "Không kiểm tra được hypertable."
        )

    return {
        **server_info,
        **location_info,
        **point_info,
        **hypertable_info,
    }