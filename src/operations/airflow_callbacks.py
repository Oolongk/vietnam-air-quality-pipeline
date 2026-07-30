from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

LOGGER = logging.getLogger(__name__)

DEFAULT_ALERT_LOG_PATH = "/opt/airflow/logs/alerts/airflow_events.jsonl"
DEFAULT_WEBHOOK_TIMEOUT_SECONDS = 5.0


def _clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback

    normalized = str(value).strip()
    return normalized or fallback


def _iso_timestamp(value: Any) -> str | None:
    if value is None:
        return None

    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())

    return _clean_text(value) or None


def _safe_integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_enabled(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(
        name,
        "true" if default else "false",
    )
    return raw_value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def build_airflow_event(
    context: dict[str, Any],
    event_type: str,
) -> dict[str, Any]:
    task_instance = context.get("task_instance")
    dag_run = context.get("dag_run")
    exception = context.get("exception")

    dag_id = _clean_text(
        getattr(task_instance, "dag_id", None),
        _clean_text(
            getattr(dag_run, "dag_id", None),
            "unknown_dag",
        ),
    )
    task_id = _clean_text(
        getattr(task_instance, "task_id", None),
        "dag_level",
    )
    run_id = _clean_text(
        getattr(task_instance, "run_id", None),
        _clean_text(
            getattr(dag_run, "run_id", None),
            "unknown_run",
        ),
    )

    log_url = _clean_text(getattr(task_instance, "log_url", None))

    event = {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "deployment_environment": os.getenv(
            "AIRFLOW_DEPLOYMENT_ENV",
            "local",
        ),
        "dag_id": dag_id,
        "task_id": task_id,
        "run_id": run_id,
        "try_number": _safe_integer(getattr(task_instance, "try_number", None)),
        "max_tries": _safe_integer(getattr(task_instance, "max_tries", None)),
        "duration_seconds": _safe_float(getattr(task_instance, "duration", None)),
        "state": _clean_text(
            getattr(task_instance, "state", None),
            _clean_text(context.get("reason")),
        ),
        "logical_date": _iso_timestamp(
            context.get("logical_date") or context.get("execution_date")
        ),
        "exception_type": (type(exception).__name__ if exception is not None else None),
        "exception_message": (
            _clean_text(exception) if exception is not None else None
        ),
        "log_url": log_url or None,
    }

    return event


def write_event_to_jsonl(
    event: dict[str, Any],
) -> Path:
    output_path = Path(
        os.getenv(
            "AIRFLOW_ALERT_LOG_PATH",
            DEFAULT_ALERT_LOG_PATH,
        )
    )
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    serialized = json.dumps(
        event,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )

    with output_path.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as file_handle:
        file_handle.write(serialized)
        file_handle.write("\n")

    return output_path


def _build_notification_text(
    event: dict[str, Any],
) -> str:
    event_type = _clean_text(
        event.get("event_type"),
        "AIRFLOW_EVENT",
    )

    parts = [
        f"[{event_type}]",
        f"DAG={event.get('dag_id')}",
        f"task={event.get('task_id')}",
        f"run={event.get('run_id')}",
    ]

    exception_message = _clean_text(event.get("exception_message"))
    if exception_message:
        parts.append(f"error={exception_message}")

    log_url = _clean_text(event.get("log_url"))
    if log_url:
        parts.append(f"log={log_url}")

    return " | ".join(parts)


def send_event_to_webhook(
    event: dict[str, Any],
) -> bool:
    webhook_url = os.getenv(
        "AIRFLOW_ALERT_WEBHOOK_URL",
        "",
    ).strip()
    if not webhook_url:
        return False

    try:
        timeout_seconds = float(
            os.getenv(
                "AIRFLOW_ALERT_WEBHOOK_TIMEOUT_SECONDS",
                str(DEFAULT_WEBHOOK_TIMEOUT_SECONDS),
            )
        )
    except ValueError:
        timeout_seconds = DEFAULT_WEBHOOK_TIMEOUT_SECONDS

    notification_text = _build_notification_text(event)
    webhook_payload = {
        "text": notification_text,
        "content": notification_text,
        "event": event,
    }

    response = requests.post(
        webhook_url,
        json=webhook_payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return True


def emit_airflow_event(
    context: dict[str, Any],
    event_type: str,
    *,
    notify_webhook: bool,
) -> None:
    try:
        event = build_airflow_event(
            context,
            event_type,
        )

        output_path = write_event_to_jsonl(event)

        LOGGER.error(
            "Airflow operational event: %s",
            json.dumps(
                event,
                ensure_ascii=False,
                default=str,
            ),
        )
        LOGGER.info(
            "Airflow event persisted at %s",
            output_path,
        )

        if notify_webhook:
            try:
                sent = send_event_to_webhook(event)
                if sent:
                    LOGGER.info("Airflow webhook alert sent.")
            except Exception:
                LOGGER.exception("Could not send Airflow webhook alert.")
    except Exception:
        LOGGER.exception("Could not persist Airflow operational event.")


def notify_task_failure(
    context: dict[str, Any],
) -> None:
    emit_airflow_event(
        context,
        "TASK_FAILURE",
        notify_webhook=True,
    )


def notify_task_retry(
    context: dict[str, Any],
) -> None:
    emit_airflow_event(
        context,
        "TASK_RETRY",
        notify_webhook=_is_enabled(
            "AIRFLOW_ALERT_ON_RETRY",
            default=False,
        ),
    )


def notify_dag_failure(
    context: dict[str, Any],
) -> None:
    emit_airflow_event(
        context,
        "DAG_FAILURE",
        notify_webhook=True,
    )
