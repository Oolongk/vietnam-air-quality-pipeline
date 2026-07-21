from __future__ import annotations

from src.quality.minio_quality_processor import (
    QUALITY_SNAPSHOT_LATEST_OBJECT,
    build_clean_prefix,
    build_quality_prefix,
    build_quality_snapshot_prefix,
)


def test_quality_object_paths_are_partitioned() -> None:
    partition_date = "2026-07-20"
    partition_hour = "12"
    batch_id = "20260720T120000Z_test"

    assert build_clean_prefix(
        partition_date,
        partition_hour,
        batch_id,
    ) == (
        "clean/air_quality/hourly/"
        "date=2026-07-20/"
        "hour=12/"
        "batch_id=20260720T120000Z_test"
    )

    assert build_quality_prefix(
        partition_date,
        partition_hour,
        batch_id,
    ) == (
        "quality/air_quality/hourly/"
        "date=2026-07-20/"
        "hour=12/"
        "batch_id=20260720T120000Z_test"
    )

    assert build_quality_snapshot_prefix(
        partition_date,
        partition_hour,
        batch_id,
    ) == (
        "data_quality/history/"
        "date=2026-07-20/"
        "hour=12/"
        "batch_id=20260720T120000Z_test"
    )


def test_latest_snapshot_has_stable_object_name() -> None:
    assert QUALITY_SNAPSHOT_LATEST_OBJECT == (
        "data_quality/latest/"
        "quality_snapshot.json"
    )
