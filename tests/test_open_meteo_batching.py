import pytest

from scripts.extract_all_points_to_minio import (
    prefetch_air_quality_batches,
)
from src.ingestion.minio_air_quality_extractor import (
    MonitoringPoint,
    chunk_monitoring_points,
)


def make_points(
    count: int,
) -> list[dict[str, object]]:
    return [
        {
            "point_id": f"POINT_{index}",
            "location_id": "TEST",
            "latitude": 10.0 + index,
            "longitude": 106.0 + index,
        }
        for index in range(
            count
        )
    ]


def test_chunk_ten_points_by_ten() -> None:
    points = make_points(
        10
    )

    batches = list(
        chunk_monitoring_points(
            monitoring_points=points,
            batch_size=10,
        )
    )

    assert len(batches) == 1
    assert len(batches[0]) == 10


def test_chunk_ten_points_by_three() -> None:
    points = make_points(
        10
    )

    batches = list(
        chunk_monitoring_points(
            monitoring_points=points,
            batch_size=3,
        )
    )

    assert len(batches) == 4

    assert [
        len(batch)
        for batch in batches
    ] == [
        3,
        3,
        3,
        1,
    ]


def test_reject_zero_batch_size() -> None:
    points = make_points(
        1
    )

    with pytest.raises(
        ValueError
    ):
        list(
            chunk_monitoring_points(
                monitoring_points=points,
                batch_size=0,
            )
        )
        
def test_prefetches_points_in_http_batches() -> None:
    monitoring_points = [
        MonitoringPoint(
            point_id=f"POINT_{index}",
            location_id="TEST",
            point_name=(
                f"Test point {index}"
            ),
            point_type="urban_center",
            latitude=10.0 + index,
            longitude=106.0 + index,
            is_active=True,
        )
        for index in range(
            5
        )
    ]

    class FakeOpenMeteoClient:
        def __init__(
            self,
        ) -> None:
            self.batch_sizes: list[
                int
            ] = []

        def fetch_hourly_air_quality_batch(
            self,
            monitoring_points,
        ):
            self.batch_sizes.append(
                len(
                    monitoring_points
                )
            )

            return [
                {
                    "request": {
                        "point_id": point[
                            "point_id"
                        ],
                        "location_id": point[
                            "location_id"
                        ],
                    },
                    "response": {
                        "hourly": {
                            "time": [
                                "2026-07-25T00:00",
                            ]
                        }
                    },
                }
                for point in monitoring_points
            ]

    client = FakeOpenMeteoClient()

    (
        responses,
        failures,
    ) = prefetch_air_quality_batches(
        client=client,
        monitoring_points=(
            monitoring_points
        ),
        batch_size=2,
    )

    assert client.batch_sizes == [
        2,
        2,
        1,
    ]

    assert len(
        responses
    ) == 5

    assert failures == {}

    assert (
        responses["POINT_0"]
        ["request"]
        ["point_id"]
        == "POINT_0"
    )