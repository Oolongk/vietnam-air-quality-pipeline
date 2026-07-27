from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import src.quality.minio_quality_processor as quality_processor


def build_settings() -> SimpleNamespace:
    return SimpleNamespace(
        clean_bucket="air-quality-clean",
        mart_bucket="air-quality-mart",
    )


def test_find_latest_quality_candidate_selects_newest_valid_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    object_names = [
        (
            "transformed/air_quality/hourly/"
            "date=2026-07-24/hour=01/"
            "batch_id=BATCH_OLD/"
            "transform_summary.json"
        ),
        (
            "transformed/air_quality/hourly/"
            "date=2026-07-25/hour=01/"
            "batch_id=BATCH_NEW/"
            "transform_summary.json"
        ),
        (
            "transformed/air_quality/hourly/"
            "date=2026-07-26/hour=01/"
            "batch_id=BATCH_FAILED/"
            "transform_summary.json"
        ),
        (
            "transformed/air_quality/hourly/"
            "date=2026-07-26/hour=02/"
            "batch_id=BATCH_EMPTY/"
            "transform_summary.json"
        ),
        "transformed/air_quality/hourly/readme.json",
    ]

    summaries: dict[
        str,
        dict[str, Any],
    ] = {
        object_names[0]: {
            "status": "SUCCESS",
            "batch_id": "BATCH_OLD",
            "transformed_object_name": (
                "transformed/old/data.parquet"
            ),
            "records_transformed": 240,
            "finished_at": (
                "2026-07-24T01:30:00+00:00"
            ),
        },
        object_names[1]: {
            "status": "PARTIAL_SUCCESS",
            "batch_id": "BATCH_NEW",
            "transformed_object_name": (
                "transformed/new/data.parquet"
            ),
            "records_transformed": 2448,
            "finished_at": (
                "2026-07-25T01:30:00+00:00"
            ),
        },
        object_names[2]: {
            "status": "FAILED",
            "batch_id": "BATCH_FAILED",
            "transformed_object_name": (
                "transformed/failed/data.parquet"
            ),
            "records_transformed": 2448,
            "finished_at": (
                "2026-07-26T01:30:00+00:00"
            ),
        },
        object_names[3]: {
            "status": "SUCCESS",
            "batch_id": "BATCH_EMPTY",
            "transformed_object_name": (
                "transformed/empty/data.parquet"
            ),
            "records_transformed": 0,
            "finished_at": (
                "2026-07-26T02:30:00+00:00"
            ),
        },
    }

    captured: dict[str, Any] = {}

    def fake_list_object_names(
        **kwargs: Any,
    ) -> list[str]:
        captured.update(
            kwargs
        )

        return object_names

    def fake_get_json_object(
        **kwargs: Any,
    ) -> dict[str, Any]:
        return summaries[
            kwargs["object_name"]
        ]

    monkeypatch.setattr(
        quality_processor,
        "list_object_names",
        fake_list_object_names,
    )

    monkeypatch.setattr(
        quality_processor,
        "get_json_object",
        fake_get_json_object,
    )

    settings = build_settings()
    client = object()

    (
        selected_object_name,
        selected_summary,
    ) = (
        quality_processor
        .find_latest_quality_candidate(
            settings=settings,
            client=client,
        )
    )

    assert selected_object_name == (
        object_names[1]
    )

    assert selected_summary[
        "batch_id"
    ] == "BATCH_NEW"

    assert captured[
        "bucket_name"
    ] == "air-quality-clean"

    assert captured[
        "prefix"
    ] == (
        "transformed/air_quality/hourly"
    )

    assert captured[
        "recursive"
    ] is True

    assert captured[
        "settings"
    ] is settings

    assert captured[
        "client"
    ] is client


def test_find_latest_quality_candidate_rejects_when_none_are_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    object_name = (
        "transformed/air_quality/hourly/"
        "date=2026-07-25/hour=01/"
        "batch_id=BATCH_FAILED/"
        "transform_summary.json"
    )

    monkeypatch.setattr(
        quality_processor,
        "list_object_names",
        lambda **kwargs: [
            object_name,
        ],
    )

    monkeypatch.setattr(
        quality_processor,
        "get_json_object",
        lambda **kwargs: {
            "status": "FAILED",
            "batch_id": "BATCH_FAILED",
            "transformed_object_name": (
                "transformed/failed/data.parquet"
            ),
            "records_transformed": 2448,
            "finished_at": (
                "2026-07-25T01:30:00+00:00"
            ),
        },
    )

    with pytest.raises(
        quality_processor.MinioDataQualityError,
        match=(
            "Không tìm thấy Transform batch"
        ),
    ):
        (
            quality_processor
            .find_latest_quality_candidate(
                settings=build_settings(),
                client=object(),
            )
        )


def test_find_latest_loadable_quality_batch_selects_newest_valid_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_object = (
        "quality/air_quality/hourly/"
        "date=2026-07-24/hour=01/"
        "batch_id=BATCH_OLD/"
        "data_quality_summary.json"
    )

    new_object = (
        "quality/air_quality/hourly/"
        "date=2026-07-25/hour=01/"
        "batch_id=BATCH_NEW/"
        "data_quality_summary.json"
    )

    invalid_object = (
        "quality/air_quality/hourly/"
        "date=2026-07-26/hour=01/"
        "batch_id=BATCH_NO_VALID_ROWS/"
        "data_quality_summary.json"
    )

    summaries: dict[
        str,
        dict[str, Any],
    ] = {
        old_object: {
            "status": "SUCCESS",
            "batch_id": "BATCH_OLD",
            "clean_object_name": (
                "clean/old/data.parquet"
            ),
            "valid_records": 240,
            "finished_at": (
                "2026-07-24T02:00:00+00:00"
            ),
        },
        new_object: {
            "status": "PARTIAL_SUCCESS",
            "batch_id": "BATCH_NEW",
            "clean_object_name": (
                "clean/new/data.parquet"
            ),
            "valid_records": 2448,
            "finished_at": (
                "2026-07-25T02:00:00+00:00"
            ),
        },
        invalid_object: {
            "status": "SUCCESS",
            "batch_id": (
                "BATCH_NO_VALID_ROWS"
            ),
            "clean_object_name": (
                "clean/invalid/data.parquet"
            ),
            "valid_records": 0,
            "finished_at": (
                "2026-07-26T02:00:00+00:00"
            ),
        },
    }

    monkeypatch.setattr(
        quality_processor,
        "list_object_names",
        lambda **kwargs: [
            old_object,
            new_object,
            invalid_object,
        ],
    )

    monkeypatch.setattr(
        quality_processor,
        "get_json_object",
        lambda **kwargs: summaries[
            kwargs["object_name"]
        ],
    )

    (
        selected_object_name,
        selected_summary,
    ) = (
        quality_processor
        .find_latest_loadable_quality_batch(
            settings=build_settings(),
            client=object(),
        )
    )

    assert selected_object_name == (
        new_object
    )

    assert selected_summary[
        "batch_id"
    ] == "BATCH_NEW"

    assert selected_summary[
        "valid_records"
    ] == 2448