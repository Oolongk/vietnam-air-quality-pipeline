# FastAPI and Runtime Inventory

## Decision

FastAPI remains an **active internal, read-only service**. It is not the
public website backend and should not be exposed directly to the Internet.

The active flow is:

`TimescaleDB -> FastAPI -> Snapshot Publisher -> private S3 -> Lambda -> Dashboard`

The Snapshot Publisher depends on the API for health, dimensions, current AQI,
point/location files, history, alerts, pipeline health and data-quality output.
Removing FastAPI would break snapshot publication.

Docker Compose binds the API to `127.0.0.1` on the host while Airflow reaches it
through the private Docker network as `http://api:8000`.

## Database configuration cleanup

The API previously maintained a second PostgreSQL environment parser in
`api/database.py`. The project now has one canonical implementation in
`src/utils/db.py`.

`api/database.py` is retained as a thin compatibility adapter because existing
API imports and tests use that module path. It no longer duplicates password,
port or timeout validation.

## Active Airflow entrypoints

The production DAG uses only the MinIO pipeline:

1. `scripts.sync_dimensions_to_timescaledb`
2. `scripts.extract_all_points_to_minio`
3. `scripts.transform_latest_minio_batch`
4. `scripts.run_latest_minio_data_quality`
5. `scripts.load_latest_minio_clean_batch`
6. `scripts.process_latest_aqi_alerts`
7. `scripts.build_latest_minio_mart`
8. `scripts.sync_latest_minio_pipeline_health`
9. `scripts.publish_latest_snapshots`
10. `scripts.upload_public_snapshots_to_s3`

The runtime inventory test requires the DAG sequence to remain exactly aligned
with this list.

## Legacy local-lake pipeline

The following entrypoints belong to the superseded local filesystem pipeline:

- `scripts.extract_all_monitoring_points`
- `scripts.transform_latest_raw_batch`
- `scripts.run_data_quality_latest_batch`
- `scripts.load_latest_clean_batch`
- `scripts.sync_latest_pipeline_health_logs`

They are retained temporarily for historical verification and recovery, but are
disabled by default. A deliberate run requires:

`ALLOW_LEGACY_LOCAL_PIPELINE=true`

This prevents an accidental parallel write path while avoiding a risky deletion
before the final full test and Git review.

## Maintenance utilities

The MinIO setup, inspection, connection tests and
`scripts.sync_local_lake_to_minio` are maintenance tools. They are not DAG
stages and are not legacy production entrypoints.

## Removed obsolete helper

`src.utils.logging_config` was an empty, unreferenced module. It was removed
after the full-suite test and Git review confirmed that the active pipeline did
not depend on it.

## Machine-readable inventory

The source of truth is `src/operations/runtime_inventory.py`.

Generated catalog:

`contracts/runtime_components.v1.json`

Validate with:

`python -m scripts.check_runtime_inventory`
