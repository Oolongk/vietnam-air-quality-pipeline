# Part 5 — Legacy Local Pipeline Retirement

## Status

Completed after the MinIO pipeline, fixed batch context and Mart serving layer
passed full static and runtime verification.

## Decision

The repository now has one production pipeline only:

````text
Open-Meteo
    ↓
Airflow
    ↓
MinIO Raw → Transform → Data Quality → MinIO Clean
    ├──→ TimescaleDB
    ├──→ AQI Alerts
    └──→ MinIO Mart
              ↓
       Snapshot Publisher
              ↓
       Private S3 release
````

The superseded local-filesystem pipeline was deleted rather than left behind as
a disabled parallel implementation.

## Removed entrypoints

- `scripts.extract_all_monitoring_points`
- `scripts.transform_latest_raw_batch`
- `scripts.run_data_quality_latest_batch`
- `scripts.load_latest_clean_batch`
- `scripts.sync_latest_pipeline_health_logs`

## Removed implementation modules

- `src.ingestion.air_quality_extractor`
- `src.transform.air_quality_transform`
- `src.transform.batch_transformer`
- `src.quality.quality_processor`
- `src.load.timescaledb_loader`
- `src.load.pipeline_log_loader`
- `src.utils.config_loader`
- `src.operations.legacy_runtime`

The local-only transform smoke script and tests dedicated to these modules were
also removed.

## Retained migration utility

`scripts.sync_local_lake_to_minio` and `src.load.minio_lake_sync` remain
available only to migrate historical files already present under
`data/local_lake`.

They are not referenced by the Airflow DAG and do not write to TimescaleDB.

## Safety controls

Runtime inventory version 2 enforces:

1. The Airflow DAG uses exactly the ten active entrypoints.
2. Every retired component path is absent.
3. Retained Python code does not import retired modules.
4. Active and maintenance entrypoints resolve to real files.
5. FastAPI remains read-only and provides required operational routes.
6. Snapshot AQI datasets come from MinIO Mart.

## Rollback

The removed code remains recoverable from Git history. For historical
investigation, check out the commit before Part 5 in a separate branch or
worktree. Do not reconnect the old implementation to the active DAG.

## Verification

````powershell
python -m scripts.check_runtime_inventory
python -m scripts.verify_legacy_pipeline_retired
python -m pytest
.\scripts\check_backend_code_quality.ps1
````
