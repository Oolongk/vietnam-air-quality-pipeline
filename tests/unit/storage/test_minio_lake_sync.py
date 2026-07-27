from pathlib import Path

from src.load.minio_lake_sync import (
    build_sync_plan,
)
from src.utils.minio_client import (
    MinioSettings,
)


def build_test_settings() -> MinioSettings:
    return MinioSettings(
        endpoint="localhost:9000",
        access_key="testaccess",
        secret_key="testsecret",
        secure=False,
        raw_bucket="air-quality-raw",
        clean_bucket="air-quality-clean",
        mart_bucket="air-quality-mart",
    )


def create_test_file(
    file_path: Path,
    content: str,
) -> None:
    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path.write_text(
        content,
        encoding="utf-8",
    )


def test_builds_expected_sync_plan(
    tmp_path: Path,
) -> None:
    local_lake_root = (
        tmp_path
        / "local_lake"
    )

    create_test_file(
        local_lake_root
        / "raw"
        / "open_meteo"
        / "data.json",
        "{}",
    )

    create_test_file(
        local_lake_root
        / "clean"
        / "air_quality"
        / "data.parquet",
        "test parquet",
    )

    create_test_file(
        local_lake_root
        / "alerts"
        / "alert_summary.json",
        "{}",
    )

    plan = build_sync_plan(
        local_lake_root=local_lake_root,
        settings=build_test_settings(),
    )

    assert len(plan) == 3

    mapping = {
        (
            entry.bucket_name,
            entry.object_name,
        )
        for entry in plan
    }

    assert (
        "air-quality-raw",
        "open_meteo/data.json",
    ) in mapping

    assert (
        "air-quality-clean",
        "clean/air_quality/data.parquet",
    ) in mapping

    assert (
        "air-quality-mart",
        "alerts/alert_summary.json",
    ) in mapping


def test_ignores_temporary_files(
    tmp_path: Path,
) -> None:
    local_lake_root = (
        tmp_path
        / "local_lake"
    )

    create_test_file(
        local_lake_root
        / "raw"
        / "data.json.tmp",
        "{}",
    )

    plan = build_sync_plan(
        local_lake_root=local_lake_root,
        settings=build_test_settings(),
    )

    assert plan == []