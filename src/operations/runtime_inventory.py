from __future__ import annotations

from typing import Any

CATALOG_VERSION = "2.0"

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

RETIRED_COMPONENTS: tuple[tuple[str, str, str], ...] = (
    (
        "scripts.extract_all_monitoring_points",
        "scripts.extract_all_points_to_minio",
        "local-filesystem extraction entrypoint",
    ),
    (
        "scripts.transform_latest_raw_batch",
        "scripts.transform_latest_minio_batch",
        "local-filesystem transform entrypoint",
    ),
    (
        "scripts.run_data_quality_latest_batch",
        "scripts.run_latest_minio_data_quality",
        "local-filesystem data-quality entrypoint",
    ),
    (
        "scripts.load_latest_clean_batch",
        "scripts.load_latest_minio_clean_batch",
        "local-filesystem TimescaleDB load entrypoint",
    ),
    (
        "scripts.sync_latest_pipeline_health_logs",
        "scripts.sync_latest_minio_pipeline_health",
        "local-filesystem pipeline-health entrypoint",
    ),
    (
        "src.ingestion.air_quality_extractor",
        "src.ingestion.minio_air_quality_extractor",
        "local extraction implementation",
    ),
    (
        "src.transform.air_quality_transform",
        "src.transform.minio_batch_transformer",
        "local single-payload transform implementation",
    ),
    (
        "src.transform.batch_transformer",
        "src.transform.minio_batch_transformer",
        "local batch transform implementation",
    ),
    (
        "src.quality.quality_processor",
        "src.quality.minio_quality_processor",
        "local quality-output implementation",
    ),
    (
        "src.load.timescaledb_loader",
        "src.load.minio_timescaledb_loader",
        "local clean-file loader",
    ),
    (
        "src.load.pipeline_log_loader",
        "src.load.minio_pipeline_log_sync",
        "local pipeline-log loader",
    ),
    (
        "src.utils.config_loader",
        "active layer-specific configuration readers",
        "legacy local pipeline configuration loader",
    ),
    (
        "src.operations.legacy_runtime",
        "not applicable",
        "temporary execution guard removed with the guarded pipeline",
    ),
)

RETIRED_MODULES: tuple[str, ...] = tuple(
    module for module, _replacement, _reason in RETIRED_COMPONENTS
)

MAINTENANCE_ENTRYPOINTS: tuple[str, ...] = (
    "scripts.setup_minio_buckets",
    "scripts.inspect_latest_minio_quality",
    "scripts.inspect_latest_minio_transform",
    "scripts.sync_local_lake_to_minio",
    "scripts.test_minio_object_io",
    "scripts.test_open_meteo_connection",
    "scripts.test_timescaledb_connection",
    "scripts.verify_mart_serving_snapshots",
    "scripts.verify_legacy_pipeline_retired",
)

SNAPSHOT_REQUIRED_API_ROUTES: tuple[str, ...] = (
    "/health",
    "/api/v1/locations",
    "/api/v1/monitoring-points",
    "/api/v1/alerts/latest",
    "/api/v1/pipeline/health/latest",
    "/api/v1/data-quality/latest",
)

MART_SNAPSHOT_DATASETS: tuple[str, ...] = (
    "current_aqi",
    "location_summary",
    "daily_summary",
)


def module_to_path(module_name: str) -> str:
    return module_name.replace(".", "/") + ".py"


def runtime_catalog() -> dict[str, Any]:
    return {
        "catalog_version": CATALOG_VERSION,
        "project": "vietnam-air-quality-pipeline",
        "active_dag_entrypoints": list(ACTIVE_DAG_ENTRYPOINTS),
        "maintenance_entrypoints": list(MAINTENANCE_ENTRYPOINTS),
        "mart_serving": {
            "status": "active",
            "source": "minio_mart",
            "datasets": list(MART_SNAPSHOT_DATASETS),
            "consumer": "snapshot_publisher",
        },
        "fastapi_role": {
            "status": "active_internal_operational_service",
            "public_exposure": False,
            "read_only": True,
            "consumer": "snapshot_publisher",
            "reason": (
                "Snapshot Publisher reads health, dimensions, alerts, pipeline "
                "health and data-quality metadata from FastAPI. Public AQI data "
                "is read from MinIO Mart."
            ),
            "required_routes": list(SNAPSHOT_REQUIRED_API_ROUTES),
        },
        "retired_components": [
            {
                "module": module,
                "replacement": replacement,
                "reason": reason,
                "retired_in": "part_5_legacy_local_pipeline_cleanup",
                "execution_policy": "removed_from_repository",
            }
            for module, replacement, reason in RETIRED_COMPONENTS
        ],
    }
