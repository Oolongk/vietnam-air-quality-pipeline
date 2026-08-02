# FastAPI and Runtime Inventory

## Decision

FastAPI remains an **active internal, read-only operational service**. It is not
the public website backend and is not exposed directly to the Internet.

Since Part 4, public AQI snapshots are read from MinIO Mart. FastAPI continues
to supply operational and dimension data required by Snapshot Publisher:

- health
- locations
- monitoring points
- alerts
- pipeline health
- data-quality status

The public serving flow is:

````text
MinIO Mart ────────────────┐
                           ├──→ Snapshot Publisher → private S3 → Lambda → Dashboard
TimescaleDB → FastAPI ─────┘
             operational data
````

Docker Compose binds FastAPI to `127.0.0.1` on the host. Airflow reaches it
through the private Docker network at `http://api:8000`.

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

## Legacy local-lake pipeline retirement

Part 5 removed the superseded local-filesystem execution path after full tests,
a successful runtime DAG and Mart snapshot verification.

The temporary environment switch `ALLOW_LEGACY_LOCAL_PIPELINE` and its guard
module were removed because no legacy entrypoint remains.

Historical mapping from removed modules to active replacements is preserved in:

````text
src/operations/runtime_inventory.py
contracts/runtime_components.v1.json
docs/legacy_local_pipeline_retirement.md
````

## Maintenance utilities

`scripts.sync_local_lake_to_minio` remains as a one-way migration utility for
old local artifacts. It is not a DAG stage and cannot create a second
production write path.

## Machine-readable inventory

Source of truth:

````text
src/operations/runtime_inventory.py
````

Generated catalog:

````text
contracts/runtime_components.v1.json
````

Validate with:

````powershell
python -m scripts.check_runtime_inventory
python -m scripts.verify_legacy_pipeline_retired
````
