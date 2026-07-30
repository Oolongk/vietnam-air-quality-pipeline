# Air Quality Data Contracts

## Purpose

These contracts define the stable interfaces between ingestion, clean
storage, data quality, TimescaleDB, mart datasets, API responses and public
snapshots.

The contracts are executable. Their machine-readable catalog is generated
from `src/contracts/air_quality_contracts.py` and stored at:

`contracts/air_quality_contracts.v1.json`

## Version policy

Current contract version: **1.0**

- Adding an optional field without changing existing meaning requires a minor
  version.
- Removing or renaming a field requires a major version.
- Changing type, unit, nullability, logical key or meaning requires a major
  version.
- A producer must not silently publish a breaking schema under the same
  version.
- Consumers must reject unsupported major versions instead of guessing.

## Identifier policy

All identifiers are strings.

`location_id="NA"` is the valid identifier for Nghệ An. It must never be
converted to a missing value by CSV readers. Configuration CSV files must
continue to use `keep_default_na=False` or an equivalent explicit string
dtype.

## Time policy

- `forecast_time` must be timezone-aware.
- Clean forecast values use `Asia/Ho_Chi_Minh`.
- `ingested_at`, `source_ingested_at` and `mart_created_at` must be
  timezone-aware and normalized to UTC when persisted.
- Public JSON timestamps must include a UTC offset or `Z`.

## Units

- PM2.5, PM10, CO, NO2, SO2 and O3 use `µg/m³`.
- Latitude and longitude use decimal degrees.
- US AQI and component AQI columns are non-negative integer indexes.

## Raw envelope v1.0

Required top-level fields:

| Field | Type | Rule |
|---|---|---|
| schema_version | string | Exactly `1.0` |
| batch_id | string | Non-empty and immutable |
| source | string | Exactly `open_meteo` |
| extracted_at | datetime | Timezone-aware |
| point | object | Point metadata |
| api_response | object | Original Open-Meteo client response |

`point` requires:

`point_id`, `location_id`, `point_name`, `point_type`, `latitude`,
`longitude`.

The nested hourly response requires `time` plus all pollutant and AQI arrays.
Every array must have the same length as `hourly.time`.

## Clean hourly v1.0

Logical key:

`point_id + forecast_time + source`

Required columns:

`point_id`, `location_id`, `point_name`, `point_type`, `latitude`,
`longitude`, `forecast_time`, six pollutant columns, seven AQI columns,
`source`, `batch_id`, `schema_version`, `ingested_at`.

All pollutant and AQI values are required and non-negative.

## Mart contracts

### mart_current_aqi v1.0

One row per `point_id`. It represents the nearest forecast record to the mart
snapshot hour and includes AQI classification plus source lineage.

### mart_location_summary v1.0

One row per `location_id`. It aggregates the current records from all active
monitoring points in a province-level location.

### mart_daily_summary v1.0

Logical key:

`forecast_date + point_id`

It contains hourly coverage, AQI category hour counts, average and maximum
pollutants, worst forecast time and source lineage.

## Public snapshot v1.0

Required envelope fields:

- `status`
- `batch_id` when data is non-empty
- `record_count`
- `data`

`record_count` must exactly equal the number of records in `data`.

The public latest-air-quality record retains point, location, coordinates,
forecast time, pollutant values, AQI values and lineage fields.

## Drift protection

The targeted unit tests verify that:

- Clean contract columns match the existing data-quality layer.
- The clean logical key matches `DUPLICATE_KEY_COLUMNS`.
- Mart input requirements match the mart builder.
- The machine-readable JSON catalog matches the Python declaration.
- `location_id="NA"` remains a valid string.
- Raw and public snapshot envelopes reject structural drift.
