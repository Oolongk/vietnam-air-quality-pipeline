from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "aws_cost_assumptions.json"
DEFAULT_SNAPSHOT_DIRECTORY = PROJECT_ROOT / "data" / "public_snapshots"
DAYS_PER_MONTH = 365.25 / 12
BYTES_PER_GB = 1024**3
BYTES_PER_MB = 1024**2


class CostConfigurationError(ValueError):
    """AWS cost model configuration is invalid."""


@dataclass(frozen=True)
class SnapshotMetrics:
    file_count: int
    total_bytes: int
    source: str

    @property
    def total_size_mb(self) -> float:
        return self.total_bytes / BYTES_PER_MB


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CostConfigurationError(
            f"Cannot read JSON file {path}: {error}"
        ) from error

    if not isinstance(value, dict):
        raise CostConfigurationError(f"JSON root must be an object: {path}")
    return value


def _require_mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise CostConfigurationError(f"Field {key!r} must be an object.")
    return value


def _require_positive_number(
    parent: dict[str, Any],
    key: str,
    *,
    allow_zero: bool = False,
) -> float:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CostConfigurationError(f"Field {key!r} must be numeric.")

    numeric = float(value)
    minimum_valid = numeric >= 0 if allow_zero else numeric > 0
    if not minimum_valid:
        operator = "non-negative" if allow_zero else "positive"
        raise CostConfigurationError(f"Field {key!r} must be {operator}.")
    return numeric


def validate_cost_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != "1.0":
        raise CostConfigurationError("schema_version must be '1.0'.")

    for field_name in ("pricing_date", "region", "currency"):
        value = config.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise CostConfigurationError(f"Field {field_name!r} must be non-empty.")

    workload = _require_mapping(config, "workload")
    fallback = _require_mapping(config, "fallback_snapshot")
    pricing = _require_mapping(config, "pricing")
    free_tier = _require_mapping(config, "free_tier")

    for key in (
        "pipeline_runs_per_day",
        "release_retention_days",
        "dashboard_requests_per_day",
        "s3_get_requests_per_dashboard_request",
        "lambda_memory_mb",
        "lambda_average_duration_ms",
        "average_response_kb",
        "cloudwatch_log_kb_per_request",
    ):
        _require_positive_number(
            workload, key, allow_zero=key == "dashboard_requests_per_day"
        )

    _require_positive_number(fallback, "file_count")
    _require_positive_number(fallback, "total_size_mb")

    for key in (
        "s3_standard_storage_gb_month_usd",
        "s3_put_per_1000_usd",
        "s3_get_per_1000_usd",
        "lambda_request_per_million_usd",
        "lambda_gb_second_usd",
        "cloudwatch_log_ingestion_gb_usd",
        "internet_data_transfer_out_gb_usd",
    ):
        _require_positive_number(pricing, key, allow_zero=True)

    for key in (
        "lambda_requests_per_month",
        "lambda_gb_seconds_per_month",
        "internet_data_transfer_out_gb_per_month",
    ):
        _require_positive_number(free_tier, key, allow_zero=True)


def load_cost_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config = _load_json_object(path)
    validate_cost_config(config)
    return config


def measure_snapshot_directory(
    snapshot_directory: Path,
    fallback: dict[str, Any],
) -> SnapshotMetrics:
    manifest_path = snapshot_directory / "manifest.json"
    if not manifest_path.is_file():
        file_count = int(_require_positive_number(fallback, "file_count"))
        total_size_mb = _require_positive_number(fallback, "total_size_mb")
        return SnapshotMetrics(
            file_count=file_count,
            total_bytes=round(total_size_mb * BYTES_PER_MB),
            source="fallback_config",
        )

    manifest = _load_json_object(manifest_path)
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise CostConfigurationError(
            "Snapshot manifest files must be a non-empty list."
        )

    normalized_paths: list[str] = []
    seen: set[str] = set()
    total_bytes = 0

    for raw_path in raw_files:
        if not isinstance(raw_path, str):
            raise CostConfigurationError("Every manifest file path must be a string.")

        relative_path = raw_path.replace("\\", "/").strip("/")
        if not relative_path or "/../" in f"/{relative_path}/":
            raise CostConfigurationError(f"Unsafe snapshot path: {raw_path!r}.")
        if relative_path in seen:
            raise CostConfigurationError(f"Duplicate snapshot path: {relative_path!r}.")

        file_path = (snapshot_directory / relative_path).resolve()
        try:
            file_path.relative_to(snapshot_directory.resolve())
        except ValueError as error:
            raise CostConfigurationError(
                f"Snapshot path escapes directory: {relative_path!r}."
            ) from error

        if not file_path.is_file():
            raise CostConfigurationError(
                f"Manifest file does not exist: {relative_path!r}."
            )

        seen.add(relative_path)
        normalized_paths.append(relative_path)
        total_bytes += file_path.stat().st_size

    return SnapshotMetrics(
        file_count=len(normalized_paths),
        total_bytes=total_bytes,
        source="snapshot_manifest",
    )


def estimate_monthly_cost(
    config: dict[str, Any],
    snapshot_metrics: SnapshotMetrics,
) -> dict[str, Any]:
    validate_cost_config(config)
    workload = _require_mapping(config, "workload")
    pricing = _require_mapping(config, "pricing")
    free_tier = _require_mapping(config, "free_tier")

    runs_per_day = float(workload["pipeline_runs_per_day"])
    retention_days = float(workload["release_retention_days"])
    public_requests_per_day = float(workload["dashboard_requests_per_day"])

    releases_per_month = runs_per_day * DAYS_PER_MONTH
    retained_releases = runs_per_day * retention_days
    public_requests_per_month = public_requests_per_day * DAYS_PER_MONTH

    release_size_gb = snapshot_metrics.total_bytes / BYTES_PER_GB
    steady_state_storage_gb = retained_releases * release_size_gb

    put_requests = releases_per_month * (snapshot_metrics.file_count + 1)
    uploader_head_requests = releases_per_month * (snapshot_metrics.file_count + 1)
    public_get_requests = public_requests_per_month * float(
        workload["s3_get_requests_per_dashboard_request"]
    )
    get_like_requests = uploader_head_requests + public_get_requests

    lambda_requests = public_requests_per_month
    lambda_memory_gb = float(workload["lambda_memory_mb"]) / 1024
    lambda_duration_seconds = float(workload["lambda_average_duration_ms"]) / 1000
    lambda_gb_seconds = lambda_requests * lambda_memory_gb * lambda_duration_seconds

    billable_lambda_requests = max(
        0.0,
        lambda_requests - float(free_tier["lambda_requests_per_month"]),
    )
    billable_lambda_gb_seconds = max(
        0.0,
        lambda_gb_seconds - float(free_tier["lambda_gb_seconds_per_month"]),
    )

    transfer_gb = (
        public_requests_per_month * float(workload["average_response_kb"]) / 1024 / 1024
    )
    billable_transfer_gb = max(
        0.0,
        transfer_gb - float(free_tier["internet_data_transfer_out_gb_per_month"]),
    )
    log_ingestion_gb = (
        public_requests_per_month
        * float(workload["cloudwatch_log_kb_per_request"])
        / 1024
        / 1024
    )

    costs = {
        "s3_storage_usd": steady_state_storage_gb
        * float(pricing["s3_standard_storage_gb_month_usd"]),
        "s3_put_usd": put_requests / 1000 * float(pricing["s3_put_per_1000_usd"]),
        "s3_get_head_usd": get_like_requests
        / 1000
        * float(pricing["s3_get_per_1000_usd"]),
        "lambda_requests_usd": billable_lambda_requests
        / 1_000_000
        * float(pricing["lambda_request_per_million_usd"]),
        "lambda_compute_usd": billable_lambda_gb_seconds
        * float(pricing["lambda_gb_second_usd"]),
        "cloudwatch_logs_usd": log_ingestion_gb
        * float(pricing["cloudwatch_log_ingestion_gb_usd"]),
        "data_transfer_out_usd": billable_transfer_gb
        * float(pricing["internet_data_transfer_out_gb_usd"]),
    }
    total_cost = sum(costs.values())

    return {
        "schema_version": "1.0",
        "pricing_date": config["pricing_date"],
        "region": config["region"],
        "currency": config["currency"],
        "disclaimer": "Reference estimate only; verify current AWS regional pricing.",
        "snapshot": {
            "source": snapshot_metrics.source,
            "file_count": snapshot_metrics.file_count,
            "total_size_mb": round(snapshot_metrics.total_size_mb, 4),
        },
        "monthly_quantities": {
            "releases": round(releases_per_month, 2),
            "retained_releases_steady_state": round(retained_releases, 2),
            "s3_storage_gb_steady_state": round(steady_state_storage_gb, 6),
            "s3_put_requests": round(put_requests),
            "s3_get_head_requests": round(get_like_requests),
            "lambda_requests": round(lambda_requests),
            "lambda_gb_seconds": round(lambda_gb_seconds, 4),
            "data_transfer_out_gb": round(transfer_gb, 6),
            "cloudwatch_log_ingestion_gb": round(log_ingestion_gb, 6),
        },
        "estimated_cost_usd": {
            **{key: round(value, 6) for key, value in costs.items()},
            "total_usd": round(total_cost, 6),
        },
    }


def _print_report(report: dict[str, Any]) -> None:
    snapshot = report["snapshot"]
    quantities = report["monthly_quantities"]
    costs = report["estimated_cost_usd"]

    print("AWS SNAPSHOT COST ESTIMATE")
    print(f"Region: {report['region']}")
    print(f"Pricing date: {report['pricing_date']}")
    print(f"Snapshot source: {snapshot['source']}")
    print(f"Files per release: {snapshot['file_count']}")
    print(f"Release size: {snapshot['total_size_mb']:.4f} MB")
    print(f"Releases/month: {quantities['releases']}")
    print(f"Steady-state storage: {quantities['s3_storage_gb_steady_state']:.6f} GB")
    print("")
    print("Estimated monthly cost (USD):")
    for key, value in costs.items():
        print(f"- {key}: {value:.6f}")
    print("")
    print(report["disclaimer"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
    )
    parser.add_argument(
        "--snapshot-directory",
        type=Path,
        default=DEFAULT_SNAPSHOT_DIRECTORY,
    )
    parser.add_argument(
        "--output-json",
        type=Path,
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
    )
    arguments = parser.parse_args()

    config = load_cost_config(arguments.config)
    if arguments.check_config:
        print("AWS cost assumptions are valid.")
        return 0

    metrics = measure_snapshot_directory(
        arguments.snapshot_directory,
        _require_mapping(config, "fallback_snapshot"),
    )
    report = estimate_monthly_cost(config, metrics)
    _print_report(report)

    if arguments.output_json is not None:
        output_path = arguments.output_json
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"Wrote estimate: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
