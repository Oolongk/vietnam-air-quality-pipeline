from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg

from src.load.pipeline_log_loader import (
    PipelineLogLoadError,
    sync_pipeline_health_logs,
)
from src.utils.db import (
    DatabaseConfigurationError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "raw"
)

TRANSFORMED_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "transformed"
)

QUALITY_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "quality"
)

LOAD_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "load"
)

ALERT_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "alerts"
)

MONITORING_ROOT = (
    PROJECT_ROOT
    / "data"
    / "local_lake"
    / "monitoring"
)


def _read_json(
    input_path: Path,
) -> dict[str, Any]:
    try:
        with input_path.open(
            mode="r",
            encoding="utf-8",
        ) as input_file:
            data = json.load(input_file)
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise FileNotFoundError(
            f"Không thể đọc JSON: {input_path}"
        ) from error

    if not isinstance(data, dict):
        raise ValueError(
            f"JSON phải là object: {input_path}"
        )

    return data


def find_latest_alert_batch_id(
    alert_root: Path,
) -> str:
    if not alert_root.exists():
        raise FileNotFoundError(
            f"Alert root chưa tồn tại: "
            f"{alert_root}"
        )

    alert_summaries = sorted(
        alert_root.rglob(
            "alert_summary.json"
        ),
        key=lambda path: (
            path.stat().st_mtime
        ),
        reverse=True,
    )

    if not alert_summaries:
        raise FileNotFoundError(
            "Không tìm thấy alert_summary.json."
        )

    for summary_path in alert_summaries:
        summary = _read_json(
            summary_path
        )

        batch_id = summary.get(
            "batch_id"
        )

        if (
            isinstance(batch_id, str)
            and batch_id.strip()
        ):
            return batch_id.strip()

    raise FileNotFoundError(
        "Không tìm thấy Alert summary "
        "có batch_id hợp lệ."
    )


def find_summary_for_batch(
    root: Path,
    filename: str,
    batch_id: str,
) -> tuple[Path, dict[str, Any]]:
    if not root.exists():
        raise FileNotFoundError(
            f"Root chưa tồn tại: {root}"
        )

    candidate_files = sorted(
        root.rglob(filename),
        key=lambda path: (
            path.stat().st_mtime
        ),
        reverse=True,
    )

    for candidate_path in candidate_files:
        summary = _read_json(
            candidate_path
        )

        candidate_batch_id = (
            summary.get("batch_id")
        )

        if (
            isinstance(
                candidate_batch_id,
                str,
            )
            and candidate_batch_id.strip()
            == batch_id
        ):
            return candidate_path, summary

    raise FileNotFoundError(
        f"Không tìm thấy {filename} "
        f"cho batch_id={batch_id}."
    )


def load_batch_summaries(
    batch_id: str,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, Path],
]:
    summary_definitions = {
        "extraction": (
            RAW_ROOT,
            "run_summary.json",
        ),
        "transform": (
            TRANSFORMED_ROOT,
            "transform_summary.json",
        ),
        "data_quality": (
            QUALITY_ROOT,
            "data_quality_summary.json",
        ),
        "database_load": (
            LOAD_ROOT,
            "load_summary.json",
        ),
        "alert_processing": (
            ALERT_ROOT,
            "alert_summary.json",
        ),
    }

    summaries: dict[
        str,
        dict[str, Any]
    ] = {}

    summary_paths: dict[str, Path] = {}

    for stage, (
        root,
        filename,
    ) in summary_definitions.items():
        (
            summary_path,
            summary,
        ) = find_summary_for_batch(
            root=root,
            filename=filename,
            batch_id=batch_id,
        )

        summaries[stage] = summary
        summary_paths[stage] = (
            summary_path
        )

    return summaries, summary_paths


def main() -> None:
    try:
        batch_id = (
            find_latest_alert_batch_id(
                ALERT_ROOT
            )
        )

        (
            summaries,
            summary_paths,
        ) = load_batch_summaries(
            batch_id
        )

        sync_summary = (
            sync_pipeline_health_logs(
                summaries=summaries,
                monitoring_root=(
                    MONITORING_ROOT
                ),
            )
        )
    except (
        FileNotFoundError,
        ValueError,
        PipelineLogLoadError,
        DatabaseConfigurationError,
        psycopg.Error,
    ) as error:
        print(
            "Đồng bộ Pipeline Health logs "
            f"thất bại: {error}"
        )

        raise SystemExit(1) from error

    print(
        "Đồng bộ Pipeline Health logs "
        "thành công."
    )
    print(
        "Batch ID: "
        f"{sync_summary['batch_id']}"
    )
    print(
        "Pipeline logs upserted: "
        f"{sync_summary['pipeline_logs_upserted']}"
    )
    print(
        "Data Quality logs upserted: "
        f"{sync_summary['data_quality_logs_upserted']}"
    )
    print(
        "Pipeline logs trong database: "
        f"{sync_summary['database_pipeline_logs_for_batch']}"
    )
    print(
        "DQ logs trong database: "
        f"{sync_summary['database_quality_logs_for_batch']}"
    )
    print(
        "Thời gian đồng bộ: "
        f"{sync_summary['duration_seconds']:.2f} giây"
    )
    print(
        "Sync summary: "
        f"{sync_summary['summary_path']}"
    )

    print()
    print("Các summary nguồn:")

    for stage, path in (
        summary_paths.items()
    ):
        print(
            f"- {stage}: {path}"
        )


if __name__ == "__main__":
    main()