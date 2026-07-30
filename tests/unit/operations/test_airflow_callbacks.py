from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

from src.operations import airflow_callbacks


def build_context() -> dict[str, object]:
    task_instance = SimpleNamespace(
        dag_id=("vietnam_air_quality_minio_pipeline"),
        task_id="extract_to_minio",
        run_id="scheduled__test",
        try_number=2,
        max_tries=2,
        duration=12.5,
        state="failed",
        log_url="http://airflow/log",
    )
    dag_run = SimpleNamespace(
        dag_id=task_instance.dag_id,
        run_id=task_instance.run_id,
    )

    return {
        "task_instance": task_instance,
        "dag_run": dag_run,
        "logical_date": datetime(
            2026,
            7,
            29,
            tzinfo=timezone.utc,
        ),
        "exception": RuntimeError("test failure"),
    }


def test_build_airflow_event() -> None:
    event = airflow_callbacks.build_airflow_event(
        build_context(),
        "TASK_FAILURE",
    )

    assert event["event_type"] == ("TASK_FAILURE")
    assert event["task_id"] == ("extract_to_minio")
    assert event["try_number"] == 2
    assert event["exception_type"] == ("RuntimeError")
    assert event["exception_message"] == ("test failure")


def test_notify_task_failure_writes_jsonl(
    tmp_path,
    monkeypatch,
) -> None:
    output_path = tmp_path / "airflow_events.jsonl"
    monkeypatch.setenv(
        "AIRFLOW_ALERT_LOG_PATH",
        str(output_path),
    )
    monkeypatch.delenv(
        "AIRFLOW_ALERT_WEBHOOK_URL",
        raising=False,
    )

    airflow_callbacks.notify_task_failure(build_context())

    lines = output_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event_type"] == ("TASK_FAILURE")


def test_failure_webhook_payload(
    tmp_path,
    monkeypatch,
) -> None:
    output_path = tmp_path / "airflow_events.jsonl"
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(
        url,
        *,
        json,
        timeout,
    ):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv(
        "AIRFLOW_ALERT_LOG_PATH",
        str(output_path),
    )
    monkeypatch.setenv(
        "AIRFLOW_ALERT_WEBHOOK_URL",
        "https://example.invalid/webhook",
    )
    monkeypatch.setattr(
        airflow_callbacks.requests,
        "post",
        fake_post,
    )

    airflow_callbacks.notify_task_failure(build_context())

    assert captured["url"] == ("https://example.invalid/webhook")
    payload = captured["json"]
    assert payload["event"]["event_type"] == ("TASK_FAILURE")
    assert "TASK_FAILURE" in payload["text"]


def test_retry_does_not_call_webhook_by_default(
    tmp_path,
    monkeypatch,
) -> None:
    output_path = tmp_path / "airflow_events.jsonl"

    def unexpected_post(*args, **kwargs):
        raise AssertionError("Retry webhook must be disabled by default.")

    monkeypatch.setenv(
        "AIRFLOW_ALERT_LOG_PATH",
        str(output_path),
    )
    monkeypatch.setenv(
        "AIRFLOW_ALERT_WEBHOOK_URL",
        "https://example.invalid/webhook",
    )
    monkeypatch.delenv(
        "AIRFLOW_ALERT_ON_RETRY",
        raising=False,
    )
    monkeypatch.setattr(
        airflow_callbacks.requests,
        "post",
        unexpected_post,
    )

    airflow_callbacks.notify_task_retry(build_context())

    event = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])
    assert event["event_type"] == "TASK_RETRY"
