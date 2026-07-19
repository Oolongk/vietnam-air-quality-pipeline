import pytest

from src.ingestion.minio_air_quality_extractor import (
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