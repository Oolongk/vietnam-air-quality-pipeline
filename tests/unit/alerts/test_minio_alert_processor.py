from __future__ import annotations

from pathlib import Path

import pytest

import src.alerts.minio_alert_processor as processor


def test_upload_alert_directory_uses_bytes_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    alert_directory = tmp_path / "alerts"
    alert_directory.mkdir()
    summary_path = alert_directory / "alert_summary.json"
    summary_path.write_text('{"status":"SUCCESS"}\n', encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_put_bytes_object(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "size_bytes": len(kwargs["payload"]),
            "etag": "etag-1",
        }

    monkeypatch.setattr(processor, "put_bytes_object", fake_put_bytes_object)

    uploaded = processor.upload_alert_directory_to_minio(
        alert_directory=alert_directory,
        bucket_name="air-quality-mart",
        object_prefix=(
            "alerts/air_quality/hourly/date=2026-07-25/hour=08/batch_id=BATCH_1"
        ),
        settings=object(),
        client=object(),
    )

    assert captured["payload"] == summary_path.read_bytes()
    assert captured["content_type"] == "application/json; charset=utf-8"
    assert captured["object_name"] == (
        "alerts/air_quality/hourly/date=2026-07-25/hour=08/"
        "batch_id=BATCH_1/alert_summary.json"
    )
    assert uploaded[0]["local_name"] == "alert_summary.json"


def test_upload_alert_directory_rejects_empty_output(tmp_path: Path) -> None:
    alert_directory = tmp_path / "alerts"
    alert_directory.mkdir()

    with pytest.raises(
        processor.MinioAlertProcessingError,
        match="không tạo ra file output",
    ):
        processor.upload_alert_directory_to_minio(
            alert_directory=alert_directory,
            bucket_name="air-quality-mart",
            object_prefix="alerts/batch_id=BATCH_1",
            settings=object(),
            client=object(),
        )
