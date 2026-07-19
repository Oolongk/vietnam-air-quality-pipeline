from __future__ import annotations

import psycopg

from src.load.dimension_loader import (
    DimensionLoaderError,
    sync_dimensions,
)


def main() -> None:
    try:
        result = sync_dimensions()

    except (
        DimensionLoaderError,
        psycopg.Error,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
    ) as error:
        print(
            "Đồng bộ dimension thất bại: "
            f"{error}"
        )

        raise SystemExit(
            1
        ) from error

    status = result.get(
        "status",
        "UNKNOWN",
    )

    locations_upserted = result.get(
        "locations_upserted",
        0,
    )

    monitoring_points_upserted = (
        result.get(
            "monitoring_points_upserted",
            0,
        )
    )

    print(
        "Đồng bộ dimension hoàn tất."
    )

    print(
        f"Status: {status}"
    )

    print(
        "Locations upserted: "
        f"{locations_upserted}"
    )

    print(
        "Monitoring points upserted: "
        f"{monitoring_points_upserted}"
    )


if __name__ == "__main__":
    main()