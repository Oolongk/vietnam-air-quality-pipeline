from __future__ import annotations

import json
from pathlib import Path

from src.ingestion.open_meteo_client import (
    OpenMeteoClient,
    OpenMeteoClientError,
)
from src.utils.config_loader import (
    load_project_config,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "local_test"
)

TARGET_POINT_ID = "HN_CENTER"


def main() -> None:
    _, monitoring_points = load_project_config()

    active_points = monitoring_points[
        monitoring_points["is_active"]
    ]

    selected_points = active_points[
        active_points["point_id"]
        == TARGET_POINT_ID
    ]

    if selected_points.empty:
        raise ValueError(
            "Không tìm thấy điểm đang hoạt động "
            f"có point_id='{TARGET_POINT_ID}'."
        )

    point = selected_points.iloc[0]

    client = OpenMeteoClient()

    try:
        raw_payload = (
            client.fetch_hourly_air_quality(
                point_id=str(point["point_id"]),
                location_id=str(
                    point["location_id"]
                ),
                latitude=float(
                    point["latitude"]
                ),
                longitude=float(
                    point["longitude"]
                ),
                forecast_hours=24,
            )
        )
    except OpenMeteoClientError as error:
        print(
            "Gọi Open-Meteo thất bại: "
            f"{error}"
        )

        raise SystemExit(1) from error
    finally:
        client.close()

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        OUTPUT_DIRECTORY
        / (
            "open_meteo_"
            f"{TARGET_POINT_ID}_sample.json"
        )
    )

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
    print(
        "Point ID: "
        f"{raw_payload['request']['point_id']}"
    )
    print(
        "Location ID: "
        f"{raw_payload['request']['location_id']}"
    )
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
    print(
        "Timezone: "
        f"{response_data.get('timezone')}"
    )
    print(
        "Số mốc thời gian: "
        f"{len(hourly_data['time'])}"
    )
    print(
        "Thời gian đầu tiên: "
        f"{hourly_data['time'][0]}"
    )
    print(
        "Thời gian cuối cùng: "
        f"{hourly_data['time'][-1]}"
    )
    print(
        "File raw mẫu: "
        f"{output_path}"
    )

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