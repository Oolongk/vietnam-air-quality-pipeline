from __future__ import annotations

import psycopg

from src.utils.db import (
    DatabaseConfigurationError,
    check_database_connection,
)


def main() -> None:
    try:
        database_info = check_database_connection()
    except (
        DatabaseConfigurationError,
        psycopg.Error,
        RuntimeError,
    ) as error:
        print(f"Kết nối TimescaleDB thất bại: {error}")

        raise SystemExit(1) from error

    print("Kết nối TimescaleDB thành công.")
    print(f"Database: {database_info['database_name']}")
    print(f"User: {database_info['database_user']}")
    print(f"PostgreSQL version: {database_info['postgres_version']}")
    print(f"TimescaleDB version: {database_info['timescaledb_version']}")
    print(f"Locations: {database_info['location_count']}")
    print(f"Monitoring points: {database_info['point_count']}")
    print(f"fact_air_quality_hourly is hypertable: {database_info['is_hypertable']}")


if __name__ == "__main__":
    main()
