import pytest

from src.load.pipeline_log_loader import (
    PipelineLogLoadError,
    build_data_quality_log_records,
    build_pipeline_log_records,
)


BATCH_ID = "20260713T110000_test"


def build_test_summaries() -> dict:
    common = {
        "source": "open_meteo",
        "status": "SUCCESS",
        "batch_id": BATCH_ID,
        "partition_date": "2026-07-13",
        "partition_hour": "11",
        "started_at": (
            "2026-07-13T04:00:00+00:00"
        ),
        "finished_at": (
            "2026-07-13T04:00:05+00:00"
        ),
        "duration_seconds": 5.0,
    }

    return {
        "extraction": {
            **common,
            "pipeline_name": (
                "open_meteo_air_quality_extraction"
            ),
            "records_extracted": 240,
            "failures": [],
        },
        "transform": {
            **common,
            "pipeline_name": (
                "open_meteo_air_quality_transform"
            ),
            "records_transformed": 240,
            "failures": [],
        },
        "data_quality": {
            **common,
            "pipeline_name": (
                "open_meteo_air_quality_data_quality"
            ),
            "input_records": 240,
            "valid_records": 240,
            "bad_records": 0,
            "checks": [
                {
                    "check_name": (
                        "POINT_ID_REQUIRED"
                    ),
                    "status": "PASSED",
                    "bad_records_count": 0,
                    "message": (
                        "point_id không được rỗng."
                    ),
                },
                {
                    "check_name": (
                        "PM2_5_NON_NEGATIVE"
                    ),
                    "status": "PASSED",
                    "bad_records_count": 0,
                    "message": (
                        "pm2_5 không được âm."
                    ),
                },
            ],
        },
        "database_load": {
            **common,
            "pipeline_name": (
                "open_meteo_air_quality_timescaledb_load"
            ),
            "input_records": 240,
            "inserted_records": 240,
            "updated_records": 0,
        },
        "alert_processing": {
            **common,
            "pipeline_name": (
                "open_meteo_air_quality_alert_processing"
            ),
            "input_records": 240,
            "alerts_generated": 12,
        },
    }


def test_builds_five_pipeline_log_records() -> None:
    summaries = build_test_summaries()

    records = build_pipeline_log_records(
        summaries
    )

    assert len(records) == 5

    run_ids = {
        record["run_id"]
        for record in records
    }

    assert run_ids == {
        f"{BATCH_ID}:extraction",
        f"{BATCH_ID}:transform",
        f"{BATCH_ID}:data_quality",
        f"{BATCH_ID}:database_load",
        f"{BATCH_ID}:alert_processing",
    }


def test_maps_stage_record_counts() -> None:
    records = build_pipeline_log_records(
        build_test_summaries()
    )

    records_by_stage = {
        record["run_id"].split(":")[-1]:
        record
        for record in records
    }

    assert (
        records_by_stage[
            "extraction"
        ]["records_extracted"]
        == 240
    )

    assert (
        records_by_stage[
            "extraction"
        ]["records_loaded"]
        == 0
    )

    assert (
        records_by_stage[
            "data_quality"
        ]["records_loaded"]
        == 240
    )

    assert (
        records_by_stage[
            "database_load"
        ]["records_loaded"]
        == 240
    )

    assert (
        records_by_stage[
            "alert_processing"
        ]["records_loaded"]
        == 12
    )


def test_builds_data_quality_logs() -> None:
    records = (
        build_data_quality_log_records(
            build_test_summaries()
        )
    )

    assert len(records) == 2

    assert all(
        record["run_id"]
        == f"{BATCH_ID}:data_quality"
        for record in records
    )

    assert {
        record["check_name"]
        for record in records
    } == {
        "POINT_ID_REQUIRED",
        "PM2_5_NON_NEGATIVE",
    }


def test_rejects_mixed_batch_ids() -> None:
    summaries = build_test_summaries()

    summaries[
        "transform"
    ]["batch_id"] = "another_batch"

    with pytest.raises(
        PipelineLogLoadError,
        match="không cùng batch_id",
    ):
        build_pipeline_log_records(
            summaries
        )


def test_rejects_timestamp_without_timezone() -> None:
    summaries = build_test_summaries()

    summaries[
        "extraction"
    ]["started_at"] = (
        "2026-07-13T04:00:00"
    )

    with pytest.raises(
        PipelineLogLoadError,
        match="timezone",
    ):
        build_pipeline_log_records(
            summaries
        )