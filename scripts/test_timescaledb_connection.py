from __future__ import annotations

import psycopg

from src.utils.db import (
    DatabaseConfigurationError,
    check_database_connection,
)


def main() -> None:
    try:
        database_info = (
            check_database_connection()
        )
    except (
        DatabaseConfigurationError,
        psycopg.Error,
        RuntimeError,
    ) as error:
        print(
            "Kết nối TimescaleDB thất bại: "
            f"{error}"
        )

        raise SystemExit(1) from error

    print("Kết nối TimescaleDB thành công.")
    print(
        "Database: "
        f"{database_info['database_name']}"
    )
    print(
        "User: "
        f"{database_info['database_user']}"
    )
    print(
        "PostgreSQL version: "
        f"{database_info['postgres_version']}"
    )
    print(
        "TimescaleDB version: "
        f"{database_info['timescaledb_version']}"
    )
    print(
        "Locations: "
        f"{database_info['location_count']}"
    )
    print(
        "Monitoring points: "
        f"{database_info['point_count']}"
    )
    print(
        "fact_air_quality_hourly "
        "is hypertable: "
        f"{database_info['is_hypertable']}"
    )


if __name__ == "__main__":
    main()