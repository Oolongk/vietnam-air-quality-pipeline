from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import psycopg

from src.utils.db import (
    get_database_connection,
)


PIPELINE_STAGES: tuple[str, ...] = (
    "extraction",
    "transform",
    "data_quality",
    "database_load",
    "alert_processing",
)

ALLOWED_PIPELINE_STATUSES: set[str] = {
    "RUNNING",
    "SUCCESS",
    "PARTIAL_SUCCESS",
    "FAILED",
}

ALLOWED_DQ_STATUSES: set[str] = {
    "PASSED",
    "FAILED",
    "WARNING",
}


UPSERT_PIPELINE_LOG_SQL = """
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
        duration_seconds
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
        %(duration_seconds)s
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        pipeline_name =
            EXCLUDED.pipeline_name,

        source =
            EXCLUDED.source,

        started_at =
            EXCLUDED.started_at,

        finished_at =
            EXCLUDED.finished_at,

        status =
            EXCLUDED.status,

        records_extracted =
            EXCLUDED.records_extracted,

        records_loaded =
            EXCLUDED.records_loaded,

        error_message =
            EXCLUDED.error_message,

        duration_seconds =
            EXCLUDED.duration_seconds;
"""


UPSERT_DATA_QUALITY_LOG_SQL = """
    INSERT INTO data_quality_logs (
        run_id,
        check_name,
        status,
        bad_records_count,
        message
    )
    VALUES (
        %(run_id)s,
        %(check_name)s,
        %(status)s,
        %(bad_records_count)s,
        %(message)s
    )
    ON CONFLICT (
        run_id,
        check_name
    )
    DO UPDATE SET
        status =
            EXCLUDED.status,

        bad_records_count =
            EXCLUDED.bad_records_count,

        message =
            EXCLUDED.message;
"""


class PipelineLogLoadError(RuntimeError):
    """Lỗi khi chuẩn hóa hoặc ghi Pipeline Health logs."""


def _require_non_empty_string(
    container: Mapping[str, Any],
    key: str,
    context: str,
) -> str:
    value = container.get(key)

    if not isinstance(value, str):
        raise PipelineLogLoadError(
            f"{context} thiếu chuỗi '{key}'."
        )

    cleaned_value = value.strip()

    if not cleaned_value:
        raise PipelineLogLoadError(
            f"{context}.{key} không được rỗng."
        )

    return cleaned_value


def _parse_aware_datetime(
    value: Any,
    field_name: str,
) -> datetime:
    if not isinstance(value, str):
        raise PipelineLogLoadError(
            f"{field_name} phải là chuỗi datetime."
        )

    cleaned_value = value.strip()

    if not cleaned_value:
        raise PipelineLogLoadError(
            f"{field_name} không được rỗng."
        )

    normalized_value = cleaned_value.replace(
        "Z",
        "+00:00",
    )

    try:
        parsed_value = datetime.fromisoformat(
            normalized_value
        )
    except ValueError as error:
        raise PipelineLogLoadError(
            f"{field_name} không phải ISO datetime "
            f"hợp lệ: {value!r}"
        ) from error

    if (
        parsed_value.tzinfo is None
        or parsed_value.utcoffset() is None
    ):
        raise PipelineLogLoadError(
            f"{field_name} phải có timezone."
        )

    return parsed_value


def _parse_optional_aware_datetime(
    value: Any,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None

    return _parse_aware_datetime(
        value=value,
        field_name=field_name,
    )


def _non_negative_integer(
    value: Any,
    field_name: str,
    default: int = 0,
) -> int:
    if value is None:
        return default

    if isinstance(value, bool):
        raise PipelineLogLoadError(
            f"{field_name} phải là số nguyên."
        )

    try:
        converted_value = int(value)
    except (
        TypeError,
        ValueError,
    ) as error:
        raise PipelineLogLoadError(
            f"{field_name} phải là số nguyên."
        ) from error

    if converted_value < 0:
        raise PipelineLogLoadError(
            f"{field_name} không được âm."
        )

    return converted_value


def _optional_non_negative_float(
    value: Any,
    field_name: str,
) -> float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        raise PipelineLogLoadError(
            f"{field_name} phải là số."
        )

    try:
        converted_value = float(value)
    except (
        TypeError,
        ValueError,
    ) as error:
        raise PipelineLogLoadError(
            f"{field_name} phải là số."
        ) from error

    if converted_value < 0:
        raise PipelineLogLoadError(
            f"{field_name} không được âm."
        )

    return converted_value


def _validate_pipeline_status(
    value: Any,
    context: str,
) -> str:
    if not isinstance(value, str):
        raise PipelineLogLoadError(
            f"{context}.status phải là chuỗi."
        )

    normalized_value = value.strip().upper()

    if (
        normalized_value
        not in ALLOWED_PIPELINE_STATUSES
    ):
        allowed_text = ", ".join(
            sorted(ALLOWED_PIPELINE_STATUSES)
        )

        raise PipelineLogLoadError(
            f"{context}.status phải thuộc: "
            f"{allowed_text}."
        )

    return normalized_value


def _validate_dq_status(
    value: Any,
    context: str,
) -> str:
    if not isinstance(value, str):
        raise PipelineLogLoadError(
            f"{context}.status phải là chuỗi."
        )

    normalized_value = value.strip().upper()

    if normalized_value not in ALLOWED_DQ_STATUSES:
        allowed_text = ", ".join(
            sorted(ALLOWED_DQ_STATUSES)
        )

        raise PipelineLogLoadError(
            f"{context}.status phải thuộc: "
            f"{allowed_text}."
        )

    return normalized_value


def _build_error_message(
    stage: str,
    summary: Mapping[str, Any],
) -> str | None:
    status = str(
        summary.get("status", "")
    ).strip().upper()

    if status == "SUCCESS":
        return None

    if stage in {
        "extraction",
        "transform",
    }:
        failures = summary.get("failures")

        if isinstance(failures, list) and failures:
            return json.dumps(
                failures,
                ensure_ascii=False,
            )

    if stage == "data_quality":
        bad_records = _non_negative_integer(
            summary.get("bad_records"),
            "data_quality.bad_records",
        )

        failed_checks = []

        checks = summary.get("checks")

        if isinstance(checks, list):
            for check in checks:
                if not isinstance(check, Mapping):
                    continue

                check_status = str(
                    check.get("status", "")
                ).strip().upper()

                if check_status != "PASSED":
                    check_name = str(
                        check.get(
                            "check_name",
                            "UNKNOWN_CHECK",
                        )
                    )

                    failed_checks.append(
                        check_name
                    )

        failed_checks_text = ", ".join(
            failed_checks
        )

        if failed_checks_text:
            return (
                f"Bad records: {bad_records}. "
                f"Failed checks: "
                f"{failed_checks_text}."
            )

        return (
            f"Bad records: {bad_records}."
        )

    existing_message = summary.get(
        "error_message"
    )

    if (
        isinstance(existing_message, str)
        and existing_message.strip()
    ):
        return existing_message.strip()

    return (
        f"Stage {stage} kết thúc với "
        f"status={status or 'UNKNOWN'}."
    )


def _stage_record_counts(
    stage: str,
    summary: Mapping[str, Any],
) -> tuple[int, int]:
    if stage == "extraction":
        return (
            _non_negative_integer(
                summary.get(
                    "records_extracted"
                ),
                "extraction.records_extracted",
            ),
            0,
        )

    if stage == "transform":
        transformed_records = (
            _non_negative_integer(
                summary.get(
                    "records_transformed"
                ),
                "transform.records_transformed",
            )
        )

        return (
            transformed_records,
            transformed_records,
        )

    if stage == "data_quality":
        return (
            _non_negative_integer(
                summary.get("input_records"),
                "data_quality.input_records",
            ),
            _non_negative_integer(
                summary.get("valid_records"),
                "data_quality.valid_records",
            ),
        )

    if stage == "database_load":
        input_records = _non_negative_integer(
            summary.get("input_records"),
            "database_load.input_records",
        )

        inserted_records = (
            _non_negative_integer(
                summary.get(
                    "inserted_records"
                ),
                "database_load.inserted_records",
            )
        )

        updated_records = (
            _non_negative_integer(
                summary.get(
                    "updated_records"
                ),
                "database_load.updated_records",
            )
        )

        loaded_records = (
            inserted_records
            + updated_records
        )

        return input_records, loaded_records

    if stage == "alert_processing":
        return (
            _non_negative_integer(
                summary.get("input_records"),
                "alert_processing.input_records",
            ),
            _non_negative_integer(
                summary.get(
                    "alerts_generated"
                ),
                "alert_processing.alerts_generated",
            ),
        )

    raise PipelineLogLoadError(
        f"Stage không được hỗ trợ: {stage}"
    )


def _validate_summaries(
    summaries: Mapping[
        str,
        Mapping[str, Any]
    ],
) -> str:
    missing_stages = (
        set(PIPELINE_STAGES)
        - set(summaries)
    )

    if missing_stages:
        missing_text = ", ".join(
            sorted(missing_stages)
        )

        raise PipelineLogLoadError(
            "Thiếu summary của các stage: "
            f"{missing_text}"
        )

    batch_ids: set[str] = set()

    for stage in PIPELINE_STAGES:
        summary = summaries[stage]

        if not isinstance(summary, Mapping):
            raise PipelineLogLoadError(
                f"Summary của stage '{stage}' "
                "phải là JSON object."
            )

        batch_id = _require_non_empty_string(
            container=summary,
            key="batch_id",
            context=stage,
        )

        batch_ids.add(batch_id)

    if len(batch_ids) != 1:
        batch_text = ", ".join(
            sorted(batch_ids)
        )

        raise PipelineLogLoadError(
            "Các summary không cùng batch_id: "
            f"{batch_text}"
        )

    return next(iter(batch_ids))


def build_pipeline_log_records(
    summaries: Mapping[
        str,
        Mapping[str, Any]
    ],
) -> list[dict[str, Any]]:
    batch_id = _validate_summaries(
        summaries
    )

    records: list[dict[str, Any]] = []

    for stage in PIPELINE_STAGES:
        summary = summaries[stage]

        context = (
            f"{stage} summary"
        )

        pipeline_name = (
            _require_non_empty_string(
                container=summary,
                key="pipeline_name",
                context=context,
            )
        )

        source = _require_non_empty_string(
            container=summary,
            key="source",
            context=context,
        )

        status = _validate_pipeline_status(
            value=summary.get("status"),
            context=context,
        )

        started_at = _parse_aware_datetime(
            value=summary.get("started_at"),
            field_name=(
                f"{stage}.started_at"
            ),
        )

        finished_at = (
            _parse_optional_aware_datetime(
                value=summary.get(
                    "finished_at"
                ),
                field_name=(
                    f"{stage}.finished_at"
                ),
            )
        )

        duration_seconds = (
            _optional_non_negative_float(
                value=summary.get(
                    "duration_seconds"
                ),
                field_name=(
                    f"{stage}.duration_seconds"
                ),
            )
        )

        (
            records_extracted,
            records_loaded,
        ) = _stage_record_counts(
            stage=stage,
            summary=summary,
        )

        records.append(
            {
                "run_id": (
                    f"{batch_id}:{stage}"
                ),
                "pipeline_name": (
                    pipeline_name
                ),
                "source": source,
                "started_at": started_at,
                "finished_at": finished_at,
                "status": status,
                "records_extracted": (
                    records_extracted
                ),
                "records_loaded": (
                    records_loaded
                ),
                "error_message": (
                    _build_error_message(
                        stage=stage,
                        summary=summary,
                    )
                ),
                "duration_seconds": (
                    duration_seconds
                ),
            }
        )

    return records


def build_data_quality_log_records(
    summaries: Mapping[
        str,
        Mapping[str, Any]
    ],
) -> list[dict[str, Any]]:
    batch_id = _validate_summaries(
        summaries
    )

    quality_summary = summaries[
        "data_quality"
    ]

    checks = quality_summary.get(
        "checks"
    )

    if not isinstance(checks, list):
        raise PipelineLogLoadError(
            "Data Quality summary thiếu "
            "danh sách 'checks'."
        )

    run_id = (
        f"{batch_id}:data_quality"
    )

    records: list[dict[str, Any]] = []

    for index, check in enumerate(checks):
        if not isinstance(check, Mapping):
            raise PipelineLogLoadError(
                "Data Quality check tại "
                f"index {index} không phải object."
            )

        check_name = (
            _require_non_empty_string(
                container=check,
                key="check_name",
                context=(
                    f"data_quality.checks[{index}]"
                ),
            )
        )

        status = _validate_dq_status(
            value=check.get("status"),
            context=(
                f"data_quality.checks[{index}]"
            ),
        )

        bad_records_count = (
            _non_negative_integer(
                check.get(
                    "bad_records_count"
                ),
                (
                    "data_quality.checks"
                    f"[{index}]"
                    ".bad_records_count"
                ),
            )
        )

        message_value = check.get(
            "message"
        )

        message = (
            str(message_value)
            if message_value is not None
            else None
        )

        records.append(
            {
                "run_id": run_id,
                "check_name": check_name,
                "status": status,
                "bad_records_count": (
                    bad_records_count
                ),
                "message": message,
            }
        )

    return records


def _write_json_atomically(
    output_path: Path,
    data: dict[str, Any],
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = output_path.with_name(
        output_path.name + ".tmp"
    )

    try:
        with temporary_path.open(
            mode="w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                data,
                output_file,
                ensure_ascii=False,
                indent=2,
            )

        temporary_path.replace(
            output_path
        )
    except OSError as error:
        raise PipelineLogLoadError(
            "Không thể ghi Pipeline Health "
            f"summary: {output_path}"
        ) from error


def sync_pipeline_health_logs(
    summaries: Mapping[
        str,
        Mapping[str, Any]
    ],
    monitoring_root: Path,
    connection: Any | None = None,
) -> dict[str, Any]:
    pipeline_records = (
        build_pipeline_log_records(
            summaries
        )
    )

    data_quality_records = (
        build_data_quality_log_records(
            summaries
        )
    )

    batch_id = str(
        summaries[
            "data_quality"
        ]["batch_id"]
    )

    partition_date = str(
        summaries[
            "data_quality"
        ]["partition_date"]
    )

    partition_hour = str(
        summaries[
            "data_quality"
        ]["partition_hour"]
    )

    owns_connection = connection is None

    resolved_connection = (
        connection
        or get_database_connection()
    )

    started_at = datetime.now().astimezone()

    try:
        with resolved_connection.transaction():
            with resolved_connection.cursor() as cursor:
                cursor.executemany(
                    UPSERT_PIPELINE_LOG_SQL,
                    pipeline_records,
                )

                if data_quality_records:
                    cursor.executemany(
                        UPSERT_DATA_QUALITY_LOG_SQL,
                        data_quality_records,
                    )

                cursor.execute(
                    """
                    SELECT COUNT(*) AS log_count
                    FROM pipeline_run_logs
                    WHERE run_id LIKE %s;
                    """,
                    (
                        f"{batch_id}:%",
                    ),
                )

                pipeline_count_row = (
                    cursor.fetchone()
                )

                cursor.execute(
                    """
                    SELECT COUNT(*) AS log_count
                    FROM data_quality_logs
                    WHERE run_id = %s;
                    """,
                    (
                        f"{batch_id}:data_quality",
                    ),
                )

                quality_count_row = (
                    cursor.fetchone()
                )

    except psycopg.Error as error:
        raise PipelineLogLoadError(
            "TimescaleDB từ chối Pipeline "
            f"Health logs: {error}"
        ) from error
    finally:
        if owns_connection:
            resolved_connection.close()

    if pipeline_count_row is None:
        raise PipelineLogLoadError(
            "Không kiểm tra được số pipeline logs."
        )

    if quality_count_row is None:
        raise PipelineLogLoadError(
            "Không kiểm tra được số DQ logs."
        )

    if isinstance(pipeline_count_row, dict):
        database_pipeline_logs = int(
            pipeline_count_row["log_count"]
        )
    else:
        database_pipeline_logs = int(
            pipeline_count_row[0]
        )

    if isinstance(quality_count_row, dict):
        database_quality_logs = int(
            quality_count_row["log_count"]
        )
    else:
        database_quality_logs = int(
            quality_count_row[0]
        )

    finished_at = datetime.now().astimezone()

    output_directory = (
        monitoring_root.resolve()
        / "pipeline_health"
        / f"date={partition_date}"
        / f"hour={partition_hour}"
        / f"batch_id={batch_id}"
    )

    summary_path = (
        output_directory
        / "pipeline_log_sync_summary.json"
    )

    summary = {
        "pipeline_name": (
            "pipeline_health_log_sync"
        ),
        "source": "open_meteo",
        "status": "SUCCESS",
        "batch_id": batch_id,
        "partition_date": partition_date,
        "partition_hour": partition_hour,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (
            finished_at - started_at
        ).total_seconds(),
        "pipeline_logs_upserted": len(
            pipeline_records
        ),
        "data_quality_logs_upserted": len(
            data_quality_records
        ),
        "database_pipeline_logs_for_batch": (
            database_pipeline_logs
        ),
        "database_quality_logs_for_batch": (
            database_quality_logs
        ),
        "summary_path": str(
            summary_path
        ),
    }

    _write_json_atomically(
        output_path=summary_path,
        data=summary,
    )

    return summary