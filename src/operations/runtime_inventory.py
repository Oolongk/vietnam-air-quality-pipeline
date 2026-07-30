from __future__ import annotations

from typing import Any

CATALOG_VERSION = "1.0"

ACTIVE_DAG_ENTRYPOINTS: tuple[str, ...] = (
    "scripts.sync_dimensions_to_timescaledb",
    "scripts.extract_all_points_to_minio",
    "scripts.transform_latest_minio_batch",
    "scripts.run_latest_minio_data_quality",
    "scripts.load_latest_minio_clean_batch",
    "scripts.process_latest_aqi_alerts",
    "scripts.build_latest_minio_mart",
    "scripts.sync_latest_minio_pipeline_health",
    "scripts.publish_latest_snapshots",
    "scripts.upload_public_snapshots_to_s3",
)

LEGACY_LOCAL_ENTRYPOINTS: tuple[str, ...] = (
    "scripts.extract_all_monitoring_points",
    "scripts.transform_latest_raw_batch",
    "scripts.run_data_quality_latest_batch",
    "scripts.load_latest_clean_batch",
    "scripts.sync_latest_pipeline_health_logs",
)

LEGACY_LOCAL_MODULES: tuple[str, ...] = (
    "src.ingestion.air_quality_extractor",
    "src.transform.air_quality_transform",
    "src.transform.batch_transformer",
    "src.quality.quality_processor",
    "src.load.timescaledb_loader",
    "src.load.pipeline_log_loader",
    "src.utils.config_loader",
)

MAINTENANCE_ENTRYPOINTS: tuple[str, ...] = (
    "scripts.setup_minio_buckets",
    "scripts.inspect_latest_minio_quality",
    "scripts.inspect_latest_minio_transform",
    "scripts.sync_local_lake_to_minio",
    "scripts.test_air_quality_transform",
    "scripts.test_minio_object_io",
    "scripts.test_open_meteo_connection",
    "scripts.test_timescaledb_connection",
)

SNAPSHOT_REQUIRED_API_ROUTES: tuple[str, ...] = (
    "/health",
    "/api/v1/locations",
    "/api/v1/monitoring-points",
    "/api/v1/air-quality/latest",
    "/api/v1/air-quality/top-polluted",
    "/api/v1/air-quality/locations/{location_id}",
    "/api/v1/air-quality/points/{point_id}",
    "/api/v1/air-quality/history",
    "/api/v1/alerts/latest",
    "/api/v1/pipeline/health/latest",
    "/api/v1/data-quality/latest",
)

UNUSED_CANDIDATES: tuple[str, ...] = ("src.utils.logging_config",)


def module_to_path(module_name: str) -> str:
    return module_name.replace(".", "/") + ".py"


def runtime_catalog() -> dict[str, Any]:
    return {
        "catalog_version": CATALOG_VERSION,
        "project": "vietnam-air-quality-pipeline",
        "fastapi_role": {
            "status": "active_internal_service",
            "public_exposure": False,
            "read_only": True,
            "consumer": "snapshot_publisher",
            "reason": (
                "Airflow Snapshot Publisher reads validated data from "
                "FastAPI before writing public snapshot files."
            ),
            "required_routes": list(SNAPSHOT_REQUIRED_API_ROUTES),
        },
        "active_dag_entrypoints": list(ACTIVE_DAG_ENTRYPOINTS),
        "legacy_local_entrypoints": [
            {
                "module": module,
                "replacement": ACTIVE_DAG_ENTRYPOINTS[index],
                "execution_policy": (
                    "disabled_by_default; set "
                    "ALLOW_LEGACY_LOCAL_PIPELINE=true only for "
                    "deliberate recovery or historical verification"
                ),
            }
            for index, module in enumerate(LEGACY_LOCAL_ENTRYPOINTS)
        ],
        "legacy_local_modules": list(LEGACY_LOCAL_MODULES),
        "maintenance_entrypoints": list(MAINTENANCE_ENTRYPOINTS),
        "unused_candidates": [
            {
                "module": module,
                "action": (
                    "retain until the final full-suite and Git review; "
                    "then remove in a dedicated commit if still unreferenced"
                ),
            }
            for module in UNUSED_CANDIDATES
        ],
    }
