from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import psycopg
from minio import Minio

from src.load.minio_timescaledb_loader import (
    TimescaleDBSettings,
)
from src.utils.minio_client import (
    MinioSettings,
    get_minio_client,
)
from src.utils.minio_object_io import (
    get_json_object,
    list_object_names,
)


LOAD_SUMMARY_PREFIX = (
    "pipeline/load/timescaledb"
)

ALERT_SUMMARY_ROOT_PREFIX = (
    "alerts/air_quality/hourly"
)


class MinioPipelineLogSyncError(
    RuntimeError
):
    """Lỗi khi đồng bộ pipeline logs từ MinIO."""


def _clean_text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    cleaned_value = str(
        value
    ).strip()

    return (
        cleaned_value
        if cleaned_value
        else default
    )


def _safe_integer(
    value: Any,
    default: int = 0,
) -> int:
    if value is None:
        return default

    try:
        return int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return default


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    if value is None:
        return default

    try:
        return float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return default


def _parse_datetime(
    value: Any,
) -> datetime | None:
    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        parsed_value = value
    else:
        normalized_value = (
            str(value)
            .strip()
            .replace(
                "Z",
                "+00:00",
            )
        )

        if not normalized_value:
            return None

        try:
            parsed_value = (
                datetime.fromisoformat(
                    normalized_value
                )
            )
        except ValueError:
            return None

    if (
        parsed_value.tzinfo is None
        or parsed_value.utcoffset()
        is None
    ):
        parsed_value = (
            parsed_value.replace(
                tzinfo=timezone.utc
            )
        )

    return parsed_value


def _summary_timestamp(
    summary: Mapping[str, Any],
) -> datetime:
    parsed_value = _parse_datetime(
        summary.get("finished_at")
        or summary.get("started_at")
    )

    if parsed_value is None:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )

    return parsed_value


def find_latest_load_summary(
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> tuple[str, dict[str, Any]]:
    resolved_settings = (
        settings
        or MinioSettings.from_environment()
    )

    resolved_client = (
        client
        or get_minio_client(
            resolved_settings
        )
    )

    object_names = [
        object_name
        for object_name in list_object_names(
            bucket_name=(
                resolved_settings.mart_bucket
            ),
            prefix=LOAD_SUMMARY_PREFIX,
            recursive=True,
            settings=resolved_settings,
            client=resolved_client,
        )
        if object_name.endswith(
            "/load_summary.json"
        )
    ]

    if not object_names:
        raise MinioPipelineLogSyncError(
            "Không tìm thấy load_summary.json "
            "trong MinIO Mart."
        )

    candidates: list[
        tuple[
            datetime,
            str,
            dict[str, Any],
        ]
    ] = []

    for object_name in object_names:
        try:
            summary = get_json_object(
                bucket_name=(
                    resolved_settings
                    .mart_bucket
                ),
                object_name=object_name,
                settings=resolved_settings,
                client=resolved_client,
            )

            if not isinstance(
                summary,
                dict,
            ):
                continue

            batch_id = _clean_text(
                summary.get("batch_id")
            )

            if not batch_id:
                continue

            candidates.append(
                (
                    _summary_timestamp(
                        summary
                    ),
                    object_name,
                    summary,
                )
            )

        except Exception:
            continue

    if not candidates:
        raise MinioPipelineLogSyncError(
            "Không tìm thấy Load summary hợp lệ."
        )

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    (
        _,
        object_name,
        summary,
    ) = candidates[0]

    return (
        object_name,
        summary,
    )


def _read_required_summary(
    bucket_name: str,
    object_name: Any,
    summary_name: str,
    settings: MinioSettings,
    client: Minio,
) -> dict[str, Any]:
    normalized_object_name = (
        _clean_text(
            object_name
        )
    )

    if not normalized_object_name:
        raise MinioPipelineLogSyncError(
            f"Thiếu object name của "
            f"{summary_name}."
        )

    summary = get_json_object(
        bucket_name=bucket_name,
        object_name=normalized_object_name,
        settings=settings,
        client=client,
    )

    if not isinstance(
        summary,
        dict,
    ):
        raise MinioPipelineLogSyncError(
            f"{summary_name} không phải "
            "JSON object hợp lệ."
        )

    return summary


def _find_alert_summary(
    batch_id: str,
    partition_date: str,
    partition_hour: str,
    settings: MinioSettings,
    client: Minio,
) -> tuple[
    str | None,
    dict[str, Any] | None,
]:
    expected_prefix = (
        f"{ALERT_SUMMARY_ROOT_PREFIX}/"
        f"date={partition_date}/"
        f"hour={partition_hour}/"
        f"batch_id={batch_id}"
    )

    object_names = [
        object_name
        for object_name in list_object_names(
            bucket_name=(
                settings.mart_bucket
            ),
            prefix=expected_prefix,
            recursive=True,
            settings=settings,
            client=client,
        )
        if object_name.endswith(
            "/alert_summary.json"
        )
        or object_name.endswith(
            "alert_summary.json"
        )
    ]

    if not object_names:
        return (
            None,
            None,
        )

    object_name = sorted(
        object_names
    )[0]

    summary = get_json_object(
        bucket_name=(
            settings.mart_bucket
        ),
        object_name=object_name,
        settings=settings,
        client=client,
    )

    if not isinstance(
        summary,
        dict,
    ):
        return (
            None,
            None,
        )

    return (
        object_name,
        summary,
    )


def collect_latest_pipeline_summaries(
    settings: MinioSettings | None = None,
    client: Minio | None = None,
) -> dict[str, Any]:
    resolved_settings = (
        settings
        or MinioSettings.from_environment()
    )

    resolved_client = (
        client
        or get_minio_client(
            resolved_settings
        )
    )

    (
        load_object_name,
        load_summary,
    ) = find_latest_load_summary(
        settings=resolved_settings,
        client=resolved_client,
    )

    batch_id = _clean_text(
        load_summary.get(
            "batch_id"
        )
    )

    partition_date = _clean_text(
        load_summary.get(
            "partition_date"
        )
    )

    partition_hour = _clean_text(
        load_summary.get(
            "partition_hour"
        )
    )

    quality_summary = (
        _read_required_summary(
            bucket_name=(
                resolved_settings
                .clean_bucket
            ),
            object_name=(
                load_summary.get(
                    "quality_summary_object_name"
                )
            ),
            summary_name=(
                "Data Quality summary"
            ),
            settings=resolved_settings,
            client=resolved_client,
        )
    )

    transform_summary = (
        _read_required_summary(
            bucket_name=(
                resolved_settings
                .clean_bucket
            ),
            object_name=(
                quality_summary.get(
                    "transform_summary_object_name"
                )
            ),
            summary_name=(
                "Transform summary"
            ),
            settings=resolved_settings,
            client=resolved_client,
        )
    )

    raw_summary = (
        _read_required_summary(
            bucket_name=(
                resolved_settings
                .raw_bucket
            ),
            object_name=(
                transform_summary.get(
                    "raw_summary_object_name"
                )
            ),
            summary_name=(
                "Extraction summary"
            ),
            settings=resolved_settings,
            client=resolved_client,
        )
    )

    (
        alert_object_name,
        alert_summary,
    ) = _find_alert_summary(
        batch_id=batch_id,
        partition_date=partition_date,
        partition_hour=partition_hour,
        settings=resolved_settings,
        client=resolved_client,
    )

    return {
        "batch_id": batch_id,
        "partition_date": (
            partition_date
        ),
        "partition_hour": (
            partition_hour
        ),
        "raw": {
            "bucket_name": (
                resolved_settings.raw_bucket
            ),
            "object_name": (
                transform_summary.get(
                    "raw_summary_object_name"
                )
            ),
            "summary": raw_summary,
        },
        "transform": {
            "bucket_name": (
                resolved_settings.clean_bucket
            ),
            "object_name": (
                quality_summary.get(
                    "transform_summary_object_name"
                )
            ),
            "summary": transform_summary,
        },
        "quality": {
            "bucket_name": (
                resolved_settings.clean_bucket
            ),
            "object_name": (
                load_summary.get(
                    "quality_summary_object_name"
                )
            ),
            "summary": quality_summary,
        },
        "load": {
            "bucket_name": (
                resolved_settings.mart_bucket
            ),
            "object_name": (
                load_object_name
            ),
            "summary": load_summary,
        },
        "alerts": {
            "bucket_name": (
                resolved_settings.mart_bucket
            ),
            "object_name": (
                alert_object_name
            ),
            "summary": alert_summary,
        },
    }


def _first_count(
    summary: Mapping[str, Any],
    *keys: str,
) -> int:
    for key in keys:
        if key in summary:
            return _safe_integer(
                summary.get(key)
            )

    return 0


def build_pipeline_log_rows(
    summaries: Mapping[str, Any],
) -> list[dict[str, Any]]:
    batch_id = _clean_text(
        summaries.get(
            "batch_id"
        )
    )

    if not batch_id:
        raise MinioPipelineLogSyncError(
            "Không xác định được batch_id."
        )

    stage_definitions = [
        (
            "extract",
            "raw",
            (
                "records_extracted",
                "total_records",
            ),
            (
                "records_extracted",
                "total_records",
            ),
            (
                "failed_points",
            ),
        ),
        (
            "transform",
            "transform",
            (
                "input_objects",
            ),
            (
                "records_transformed",
            ),
            (
                "failed_objects",
            ),
        ),
        (
            "data_quality",
            "quality",
            (
                "input_records",
            ),
            (
                "valid_records",
            ),
            (
                "bad_records",
            ),
        ),
        (
            "load_timescaledb",
            "load",
            (
                "input_rows",
            ),
            (
                "processed_rows",
            ),
            (),
        ),
        (
            "alerts",
            "alerts",
            (
                "input_records",
                "processed_records",
                "total_records",
            ),
            (
                "alert_records",
                "alerts_created",
                "alerts_generated",
                "total_alerts",
            ),
            (),
        ),
    ]

    rows: list[
        dict[str, Any]
    ] = []

    for (
        stage_name,
        summary_key,
        input_keys,
        output_keys,
        failed_keys,
    ) in stage_definitions:
        stage_container = summaries.get(
            summary_key
        )

        if not isinstance(
            stage_container,
            Mapping,
        ):
            continue

        summary = stage_container.get(
            "summary"
        )

        if not isinstance(
            summary,
            Mapping,
        ):
            continue

        failures = summary.get(
            "failures"
        )

        error_message = None

        if isinstance(
            failures,
            list,
        ) and failures:
            error_message = (
                str(failures[0])[:2000]
            )
        run_id = (
            f"{batch_id}:"
            f"{stage_name}"
        )

        rows.append(
            {
                "run_id": run_id,
                "batch_id": batch_id,
                "pipeline_name": (
                    _clean_text(
                        summary.get(
                            "pipeline_name"
                        ),
                        default=(
                            "air_quality_pipeline"
                        ),
                    )
                ),
                "source": (
                    _clean_text(
                        summary.get(
                            "source"
                        ),
                        default="open_meteo",
                    )
                ),
                "stage_name": stage_name,
                "status": (
                    _clean_text(
                        summary.get(
                            "status"
                        ),
                        default="UNKNOWN",
                    ).upper()
                ),
                "started_at": (
                    _parse_datetime(
                        summary.get(
                            "started_at"
                        )
                    )
                ),
                "finished_at": (
                    _parse_datetime(
                        summary.get(
                            "finished_at"
                        )
                    )
                ),
                "duration_seconds": (
                    _safe_float(
                        summary.get(
                            "duration_seconds"
                        )
                    )
                ),
                "input_records": (
                    _first_count(
                        summary,
                        *input_keys,
                    )
                ),
                "output_records": (
                    _first_count(
                        summary,
                        *output_keys,
                    )
                ),
                "failed_records": (
                    _first_count(
                        summary,
                        *failed_keys,
                    )
                ),
                "records_extracted": (
                    _first_count(
                        summary,
                        *input_keys,
                    )
                ),
                "records_loaded": (
                    _first_count(
                        summary,
                        *output_keys,
                    )
                ),
                "summary_bucket": (
                    stage_container.get(
                        "bucket_name"
                    )
                ),
                "summary_object_name": (
                    stage_container.get(
                        "object_name"
                    )
                ),
                "error_message": (
                    error_message
                ),
            }
        )

    return rows


def build_data_quality_log_rows(
    summaries: Mapping[str, Any],
) -> list[dict[str, Any]]:
    quality_container = summaries.get(
        "quality"
    )

    if not isinstance(
        quality_container,
        Mapping,
    ):
        raise MinioPipelineLogSyncError(
            "Thiếu Data Quality summary."
        )

    quality_summary = (
        quality_container.get(
            "summary"
        )
    )

    if not isinstance(
        quality_summary,
        Mapping,
    ):
        raise MinioPipelineLogSyncError(
            "Data Quality summary không hợp lệ."
        )

    checks = quality_summary.get(
        "checks"
    )

    if not isinstance(
        checks,
        list,
    ):
        raise MinioPipelineLogSyncError(
            "Data Quality summary thiếu checks."
        )

    batch_id = _clean_text(
        summaries.get(
            "batch_id"
        )
    )

    checked_at = (
        _parse_datetime(
            quality_summary.get(
                "finished_at"
            )
        )
        or datetime.now(
            timezone.utc
        )
    )

    rows: list[
        dict[str, Any]
    ] = []
    
    data_quality_run_id = (
        f"{batch_id}:data_quality"
    )
    
    for check in checks:
        if not isinstance(
            check,
            Mapping,
        ):
            continue

        check_name = _clean_text(
            check.get(
                "check_name"
            )
        )

        if not check_name:
            continue

        rows.append(
            {
                "run_id": data_quality_run_id,
                "batch_id": batch_id,
                "check_name": (
                    check_name
                ),
                "status": (
                    _clean_text(
                        check.get(
                            "status"
                        ),
                        default="UNKNOWN",
                    ).upper()
                ),
                "bad_records_count": (
                    _safe_integer(
                        check.get(
                            "bad_records_count"
                        )
                    )
                ),
                "message": (
                    _clean_text(
                        check.get(
                            "message"
                        )
                    )
                ),
                "checked_at": (
                    checked_at
                ),
                "summary_bucket": (
                    quality_container.get(
                        "bucket_name"
                    )
                ),
                "summary_object_name": (
                    quality_container.get(
                        "object_name"
                    )
                ),
            }
        )

    return rows


def upsert_pipeline_log_rows(
    connection: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0

    query = """
        INSERT INTO pipeline_run_logs (
            run_id,
            pipeline_name,
            source,
            started_at,
            finished_at,
            status,
            records_extracted,
            records_loaded,
            error_message,
            duration_seconds,
            batch_id,
            stage_name,
            input_records,
            output_records,
            failed_records,
            summary_bucket,
            summary_object_name,
            created_at,
            updated_at
        )
        VALUES (
            %(run_id)s,
            %(pipeline_name)s,
            %(source)s,
            %(started_at)s,
            %(finished_at)s,
            %(status)s,
            %(records_extracted)s,
            %(records_loaded)s,
            %(error_message)s,
            %(duration_seconds)s,
            %(batch_id)s,
            %(stage_name)s,
            %(input_records)s,
            %(output_records)s,
            %(failed_records)s,
            %(summary_bucket)s,
            %(summary_object_name)s,
            NOW(),
            NOW()
        )
        ON CONFLICT (
            batch_id,
            stage_name
        )
        DO UPDATE SET
            run_id = EXCLUDED.run_id,
            pipeline_name = EXCLUDED.pipeline_name,
            source = EXCLUDED.source,
            started_at = EXCLUDED.started_at,
            finished_at = EXCLUDED.finished_at,
            status = EXCLUDED.status,
            records_extracted = EXCLUDED.records_extracted,
            records_loaded = EXCLUDED.records_loaded,
            error_message = EXCLUDED.error_message,
            duration_seconds = EXCLUDED.duration_seconds,
            input_records = EXCLUDED.input_records,
            output_records = EXCLUDED.output_records,
            failed_records = EXCLUDED.failed_records,
            summary_bucket = EXCLUDED.summary_bucket,
            summary_object_name = EXCLUDED.summary_object_name,
            updated_at = NOW()
    """

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            rows,
        )

    return len(rows)

def upsert_data_quality_log_rows(
    connection: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0

    query = """
        INSERT INTO data_quality_logs (
            run_id,
            check_name,
            status,
            bad_records_count,
            message,
            batch_id,
            checked_at,
            summary_bucket,
            summary_object_name,
            created_at,
            updated_at
        )
        VALUES (
            %(run_id)s,
            %(check_name)s,
            %(status)s,
            %(bad_records_count)s,
            %(message)s,
            %(batch_id)s,
            %(checked_at)s,
            %(summary_bucket)s,
            %(summary_object_name)s,
            NOW(),
            NOW()
        )
        ON CONFLICT (
            batch_id,
            check_name
        )
        DO UPDATE SET
            run_id = EXCLUDED.run_id,
            status = EXCLUDED.status,
            bad_records_count = EXCLUDED.bad_records_count,
            message = EXCLUDED.message,
            checked_at = EXCLUDED.checked_at,
            summary_bucket = EXCLUDED.summary_bucket,
            summary_object_name = EXCLUDED.summary_object_name,
            updated_at = NOW()
    """

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            rows,
        )

    return len(rows)

def sync_latest_minio_pipeline_health(
    minio_settings: MinioSettings | None = None,
    minio_client: Minio | None = None,
    database_settings: TimescaleDBSettings | None = None,
) -> dict[str, Any]:
    resolved_minio_settings = (
        minio_settings
        or MinioSettings.from_environment()
    )

    resolved_minio_client = (
        minio_client
        or get_minio_client(
            resolved_minio_settings
        )
    )

    resolved_database_settings = (
        database_settings
        or TimescaleDBSettings.from_environment()
    )

    summaries = (
        collect_latest_pipeline_summaries(
            settings=resolved_minio_settings,
            client=resolved_minio_client,
        )
    )

    pipeline_rows = (
        build_pipeline_log_rows(
            summaries
        )
    )

    quality_rows = (
        build_data_quality_log_rows(
            summaries
        )
    )

    if not pipeline_rows:
        raise MinioPipelineLogSyncError(
            "Không tạo được pipeline log row."
        )

    if not quality_rows:
        raise MinioPipelineLogSyncError(
            "Không tạo được Data Quality log row."
        )

    connection = (
        resolved_database_settings.connect()
    )

    try:
        pipeline_log_count = (
            upsert_pipeline_log_rows(
                connection=connection,
                rows=pipeline_rows,
            )
        )

        quality_log_count = (
            upsert_data_quality_log_rows(
                connection=connection,
                rows=quality_rows,
            )
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    return {
        "status": "SUCCESS",
        "batch_id": (
            summaries["batch_id"]
        ),
        "pipeline_logs_upserted": (
            pipeline_log_count
        ),
        "data_quality_logs_upserted": (
            quality_log_count
        ),
        "stages": [
            row["stage_name"]
            for row in pipeline_rows
        ],
    }