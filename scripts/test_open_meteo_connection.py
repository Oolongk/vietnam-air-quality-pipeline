from __future__ import annotations

import json
from pathlib import Path

from src.ingestion.minio_air_quality_extractor import (
    load_active_monitoring_points,
)
from src.ingestion.open_meteo_client import (
    OpenMeteoClient,
    OpenMeteoClientError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MONITORING_POINTS_PATH = PROJECT_ROOT / "configs" / "monitoring_points.csv"
OUTPUT_DIRECTORY = PROJECT_ROOT / "data" / "local_test"
TARGET_POINT_ID = "HN_CENTER"


def main() -> None:
    monitoring_points = load_active_monitoring_points(MONITORING_POINTS_PATH)

    point = next(
        (
            monitoring_point
            for monitoring_point in monitoring_points
            if monitoring_point.point_id == TARGET_POINT_ID
        ),
        None,
    )

    if point is None:
        raise ValueError(
            f"Không tìm thấy điểm đang hoạt động có point_id='{TARGET_POINT_ID}'."
        )

    client = OpenMeteoClient()

    try:
        raw_payload = client.fetch_hourly_air_quality(
            point_id=point.point_id,
            location_id=point.location_id,
            latitude=point.latitude,
            longitude=point.longitude,
            forecast_hours=24,
        )
    except OpenMeteoClientError as error:
        print(f"Gọi Open-Meteo thất bại: {error}")
        raise SystemExit(1) from error
    finally:
        client.close()

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = OUTPUT_DIRECTORY / (f"open_meteo_{TARGET_POINT_ID}_sample.json")

    with output_path.open(
        mode="w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            raw_payload,
            output_file,
            ensure_ascii=False,
            indent=2,
        )

    response_data = raw_payload["response"]
    hourly_data = response_data["hourly"]

    print("Gọi Open-Meteo thành công.")
    print(f"Point ID: {raw_payload['request']['point_id']}")
    print(f"Location ID: {raw_payload['request']['location_id']}")
    print(
        "Requested coordinates: "
        f"{raw_payload['request']['latitude']}, "
        f"{raw_payload['request']['longitude']}"
    )
    print(
        "API grid coordinates: "
        f"{response_data.get('latitude')}, "
        f"{response_data.get('longitude')}"
    )
    print(f"Timezone: {response_data.get('timezone')}")
    print(f"Số mốc thời gian: {len(hourly_data['time'])}")
    print(f"Thời gian đầu tiên: {hourly_data['time'][0]}")
    print(f"Thời gian cuối cùng: {hourly_data['time'][-1]}")
    print(f"File raw mẫu: {output_path}")
    print()
    print("Năm bản ghi đầu tiên:")

    preview_count = min(
        5,
        len(hourly_data["time"]),
    )

    for index in range(preview_count):
        print(
            f"- {hourly_data['time'][index]} | "
            f"AQI={hourly_data['us_aqi'][index]} | "
            f"PM2.5={hourly_data['pm2_5'][index]} | "
            f"PM10={hourly_data['pm10'][index]}"
        )


if __name__ == "__main__":
    main()
