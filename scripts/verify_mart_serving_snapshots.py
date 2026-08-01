from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any


class MartServingVerificationError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MartServingVerificationError(
            f"Không thể đọc JSON hợp lệ: {path}"
        ) from error
    if not isinstance(payload, dict):
        raise MartServingVerificationError(f"JSON root phải là object: {path}")
    return payload


def _validate_records(
    payload: dict[str, Any],
    path: Path,
    expected_batch_id: str,
) -> int:
    actual_batch_id = str(payload.get("batch_id", "")).strip()
    if actual_batch_id != expected_batch_id:
        raise MartServingVerificationError(
            f"Sai batch_id tại {path}. "
            f"Expected={expected_batch_id}; actual={actual_batch_id or 'EMPTY'}."
        )
    records = payload.get("data")
    if not isinstance(records, list):
        raise MartServingVerificationError(f"Field data không phải list: {path}")
    record_count = payload.get("record_count")
    if record_count != len(records):
        raise MartServingVerificationError(
            f"Sai record_count tại {path}. "
            f"Declared={record_count}; actual={len(records)}."
        )
    if not records:
        raise MartServingVerificationError(f"Snapshot đang rỗng: {path}")
    return len(records)


def main() -> int:
    output_value = os.getenv(
        "SNAPSHOT_OUTPUT_DIRECTORY",
        "data/public_snapshots",
    )
    output_directory = Path(output_value).expanduser().resolve()
    manifest_path = output_directory / "manifest.json"

    try:
        manifest = _read_json(manifest_path)
        batch_id = str(manifest.get("latest_batch_id", "")).strip()
        if not batch_id:
            raise MartServingVerificationError("manifest.json thiếu latest_batch_id.")

        source = manifest.get("source")
        if not isinstance(source, dict):
            raise MartServingVerificationError("manifest.json thiếu source object.")
        air_quality_source = source.get("air_quality")
        if not isinstance(air_quality_source, dict):
            raise MartServingVerificationError(
                "manifest.json thiếu source.air_quality object."
            )
        if air_quality_source.get("type") != "minio_mart":
            raise MartServingVerificationError(
                "Snapshot AQI chưa dùng source type minio_mart."
            )

        snapshot_paths = {
            "current_aqi": output_directory / "air_quality/latest.json",
            "location_summary": (
                output_directory / "air_quality/location_summary.json"
            ),
            "daily_summary": output_directory / "air_quality/daily_summary.json",
        }
        counts = {
            name: _validate_records(_read_json(path), path, batch_id)
            for name, path in snapshot_paths.items()
        }
    except MartServingVerificationError as error:
        print(f"MART SERVING VERIFY FAILED: {error}", file=sys.stderr)
        return 1

    print("MART SERVING VERIFY SUCCESS")
    print(f"Output directory: {output_directory}")
    print(f"Batch ID: {batch_id}")
    for name, count in counts.items():
        print(f"{name}: {count} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
