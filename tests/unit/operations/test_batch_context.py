from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.operations.batch_context import (
    PipelineBatchContext,
    PipelineBatchContextError,
)


def valid_environment() -> dict[str, str]:
    return {
        "PIPELINE_BATCH_ID": "20260731T140000Z_airflow",
        "PIPELINE_PARTITION_DATE": "2026-07-31",
        "PIPELINE_PARTITION_HOUR": "21",
        "PIPELINE_STARTED_AT": "2026-07-31T14:00:00+00:00",
    }


def test_returns_none_when_context_is_absent() -> None:
    assert PipelineBatchContext.from_environment({}) is None


def test_rejects_missing_required_context() -> None:
    with pytest.raises(PipelineBatchContextError, match="Thiếu Airflow batch context"):
        PipelineBatchContext.from_environment({}, required=True)


def test_rejects_partial_context() -> None:
    environment = valid_environment()
    environment.pop("PIPELINE_PARTITION_HOUR")

    with pytest.raises(PipelineBatchContextError, match="cấu hình một phần"):
        PipelineBatchContext.from_environment(environment)


def test_parses_valid_context() -> None:
    context = PipelineBatchContext.from_environment(valid_environment())

    assert context is not None
    assert context.batch_id == "20260731T140000Z_airflow"
    assert context.partition_date == "2026-07-31"
    assert context.partition_hour == "21"
    assert context.started_at == datetime(2026, 7, 31, 14, 0, tzinfo=timezone.utc)


def test_rejects_partition_that_does_not_match_started_at() -> None:
    environment = valid_environment()
    environment["PIPELINE_PARTITION_HOUR"] = "20"

    with pytest.raises(PipelineBatchContextError, match="Partition hour"):
        PipelineBatchContext.from_environment(environment)


def test_rejects_unsafe_batch_id() -> None:
    environment = valid_environment()
    environment["PIPELINE_BATCH_ID"] = "../../unsafe"

    with pytest.raises(PipelineBatchContextError, match="chỉ được chứa"):
        PipelineBatchContext.from_environment(environment)


def test_validates_summary_identity() -> None:
    context = PipelineBatchContext.from_environment(valid_environment())
    assert context is not None

    context.validate_summary(
        {
            "batch_id": context.batch_id,
            "partition_date": context.partition_date,
            "partition_hour": context.partition_hour,
        },
        "Transform summary",
    )

    with pytest.raises(PipelineBatchContextError, match="không khớp batch_id"):
        context.validate_summary(
            {
                "batch_id": "another_batch",
                "partition_date": context.partition_date,
                "partition_hour": context.partition_hour,
            },
            "Transform summary",
        )
