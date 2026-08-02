<!-- GENERATED FILE: edit source chapters, then run `python -m scripts.build_unified_documentation` -->

# Vietnam Air Quality Pipeline — Tài liệu hệ thống

Kiến trúc, dữ liệu, vận hành, quyết định kỹ thuật và hướng dẫn portfolio trong một tài liệu thống nhất.

> Đây là bản đọc liên tục được tạo tự động từ các file nguồn trong `docs/`. Không sửa trực tiếp file này.

## Mục lục

### Phần I — Kiến trúc và luồng xử lý

1. [Kiến trúc tổng thể](#chapter-architecture)
2. [Batch context và Airflow execution](#chapter-batch-execution)
3. [MinIO Mart serving layer](#chapter-mart-serving)
4. [FastAPI và runtime inventory](#chapter-fastapi-runtime)
### Phần II — Mô hình và chất lượng dữ liệu

5. [Data contracts](#chapter-data-contracts)
6. [Data dictionary](#chapter-data-dictionary)
### Phần III — Kiểm thử và vận hành

7. [Continuous Integration](#chapter-continuous-integration)
8. [Operations runbook](#chapter-operations-runbook)
9. [AWS cost management](#chapter-aws-cost)
### Phần IV — Lịch sử và quyết định kiến trúc

10. [Legacy local pipeline retirement](#chapter-legacy-retirement)
11. [Architecture Decision Records](#chapter-adr-index)
12. [ADR-0001 — Single production pipeline](#chapter-adr-0001)
13. [ADR-0002 — Deterministic batch context](#chapter-adr-0002)
14. [ADR-0003 — MinIO Mart serving](#chapter-adr-0003)
15. [ADR-0004 — Private S3 immutable releases](#chapter-adr-0004)
### Phần V — Portfolio và minh họa

16. [Screenshot guide](#chapter-screenshots)

---

# Phần I — Kiến trúc và luồng xử lý

<a id="chapter-architecture"></a>

## Chương 1 — Kiến trúc tổng thể

*Nguồn: [`docs/architecture.md`](architecture.md)*

### 1. Mục tiêu

Vietnam Air Quality Monitoring & Forecasting Data Pipeline là một hệ thống Data Engineering dùng để:

- Thu thập dữ liệu chất lượng không khí theo tọa độ.
- Lưu dữ liệu gốc và dữ liệu đã xử lý trong data lake.
- Kiểm tra chất lượng trước khi load database.
- Lưu dữ liệu chuỗi thời gian để truy vấn hiệu quả.
- Phân loại AQI và tạo cảnh báo.
- Xuất bản snapshot công khai mà không mở database trực tiếp ra Internet.
- Hiển thị dữ liệu qua Streamlit dashboard.

Nguồn chính là Open-Meteo Air Quality API. Đây là dữ liệu mô hình và dự báo, không phải dữ liệu đo trực tiếp từ trạm quan trắc tại toàn bộ tỉnh/thành.

### 2. Kiến trúc tổng thể

````mermaid
graph TD
    A[Open-Meteo Air Quality API] --> B[Apache Airflow]
    B --> C[MinIO Raw Zone]
    C --> D[Transform & Standardize]
    D --> E[Data Quality Validation]
    E --> F[MinIO Clean Zone]
    F --> G[TimescaleDB]
    F --> H[MinIO Mart Zone]
    F --> I[AQI Alert Processing]
    I --> J[Alert records & MinIO artifacts]
    G --> K[Internal FastAPI]
    K --> L[Snapshot Publisher]
    L --> M[Immutable JSON release]
    M --> N[Private Amazon S3]
    N --> O[Lambda Snapshot Reader]
    O --> P[Streamlit Dashboard]
    B --> Q[Pipeline Health]
    Q --> G
````

### 3. Active runtime flow

Luồng production hiện tại:

````text
Open-Meteo
    ↓
Airflow MinIO pipeline
    ↓
Raw → Transform → Data Quality → Clean
    ├──→ TimescaleDB
    ├──→ AQI Alerts
    └──→ Mart datasets
             ↓
      Pipeline Health Sync
             ↓
TimescaleDB → FastAPI → Snapshot Publisher
             ↓
Local immutable JSON snapshot
             ↓
Private S3 release + current.json pointer
             ↓
Lambda Snapshot Reader
             ↓
Streamlit Dashboard
````

FastAPI là dịch vụ nội bộ, read-only. Docker Compose chỉ publish API trên loopback `127.0.0.1`, còn Airflow truy cập API qua private Docker network bằng `http://api:8000`.

Dashboard nhận dữ liệu từ Lambda/CloudFront snapshot base URL, không truy cập trực tiếp TimescaleDB và không gọi FastAPI nội bộ từ Internet.

### 4. Airflow orchestration

DAG ID:

````text
vietnam_air_quality_minio_pipeline
````

Schedule:

````text
*/30 * * * *
````

Active entrypoints:

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

Dependency graph:

````text
sync_dimensions
    ↓
extract_to_minio
    ↓
transform_minio_batch
    ↓
run_data_quality
    ↓
load_timescaledb ─────────→ process_aqi_alerts
    └─────────────────────→ build_minio_mart
                                  ↓
                         sync_pipeline_health
                                  ↓
                      publish_public_snapshots
                                  ↓
                   upload_public_snapshots_to_s3
````

Operational controls:

- `max_active_runs=1`
- `max_active_tasks=2`
- Two retries per task.
- Exponential retry backoff.
- Task execution timeout.
- DAG run timeout.
- Task failure, retry and DAG failure callbacks.
- Optional webhook delivery.

### 5. Data lake layers

#### Raw Zone

Bucket:

````text
air-quality-raw
````

Mục đích:

- Giữ payload JSON gần với dữ liệu nguồn.
- Hỗ trợ kiểm tra, tái xử lý và truy vết batch.

Partition chính:

````text
open_meteo/air_quality/date=YYYY-MM-DD/hour=HH/batch_id=<batch_id>/
````

#### Clean Zone

Bucket:

````text
air-quality-clean
````

Mục đích:

- Lưu dữ liệu đã chuẩn hóa thành Parquet.
- Lưu transform summary và quality summary.
- Chỉ cho phép batch đạt Data Quality đi tiếp tới load và downstream processing.

#### Mart Zone

Bucket:

````text
air-quality-mart
````

Datasets:

- `current_aqi`
- `location_summary`
- `daily_summary`
- AQI alert artifacts

Mart được tạo trong Airflow, lưu trên MinIO và là nguồn AQI trực tiếp của Snapshot Publisher.

### 6. Data Quality layer

Các nhóm kiểm tra chính:

- Required columns và required values.
- Numeric type và non-negative pollutant/AQI values.
- Latitude/longitude range.
- Expected source.
- Expected `batch_id`.
- Duplicate logical key `(point_id, forecast_time, source)`.
- Timezone-aware timestamps.
- Forecast coverage.
- Freshness.

Kết quả kiểm tra được lưu thành quality summary và đồng bộ vào `data_quality_logs`.

### 7. TimescaleDB

Các bảng chính:

- `dim_location`
- `dim_monitoring_point`
- `fact_air_quality_hourly`
- `fact_air_quality_alerts`
- `pipeline_run_logs`
- `data_quality_logs`

`fact_air_quality_hourly` là hypertable phục vụ truy vấn dữ liệu AQI theo thời gian.

SQL schema, indexes và migrations nằm trong `sql/`.

### 8. AQI alert processing

Alert được tạo khi:

````text
AQI >= 101
````

Mức cảnh báo:

- `MEDIUM`: 101–150
- `HIGH`: 151–200
- `CRITICAL`: từ 201 trở lên

Alert records được cập nhật vào TimescaleDB. Summary và artifacts của batch được upload vào MinIO Mart bucket dưới prefix:

````text
alerts/air_quality/hourly/date=YYYY-MM-DD/hour=HH/batch_id=<batch_id>/
````

### 9. Internal FastAPI

FastAPI là lớp query nội bộ giữa TimescaleDB và Snapshot Publisher.

Các nhóm endpoint:

- Health
- Locations
- Monitoring points
- Latest AQI
- Location and point AQI
- AQI history
- Top polluted locations
- Latest alerts
- Pipeline health
- Data-quality results

FastAPI không phải public website backend và không nên expose trực tiếp ra Internet.

### 10. Snapshot publishing và public delivery

Snapshot Publisher đọc AQI từ MinIO Mart, đọc operational metadata từ FastAPI và ghi các file JSON như:

````text
health.json
locations.json
monitoring_points.json
air_quality/latest.json
air_quality/top_polluted.json
air_quality/locations/<location_id>.json
air_quality/points/<point_id>.json
air_quality/history/<point_id>.json
alerts/latest.json
pipeline/health.json
data_quality/latest.json
manifest.json
````

S3 uploader:

1. Upload toàn bộ file vào một immutable release prefix.
2. Xác minh release và manifest.
3. Cập nhật `current.json` pointer sau cùng.

Lambda Snapshot Reader đọc pointer và chỉ trả về các đường dẫn snapshot hợp lệ. S3 bucket vẫn private.

### 11. Dashboard

Dashboard Streamlit đọc snapshot public qua `PUBLIC_SNAPSHOT_BASE_URL`.

Các trang:

1. Bản đồ AQI
2. Phân tích
3. Điểm theo dõi
4. Lịch sử AQI
5. Cảnh báo
6. Trạng thái hệ thống

Dashboard sử dụng Altair cho biểu đồ và PyDeck cho bản đồ.

### 12. Runtime inventory và legacy pipeline

Source of truth:

````text
src/operations/runtime_inventory.py
````

Generated catalog:

````text
contracts/runtime_components.v1.json
````

Pipeline local filesystem cũ được giữ tạm thời để recovery và historical verification, nhưng bị vô hiệu hóa mặc định. Muốn chạy có chủ đích phải đặt:

````text
ALLOW_LEGACY_LOCAL_PIPELINE=true
````

### 13. Current architectural improvements

Các hạng mục đang được ưu tiên:

1. Truyền `batch_id` xuyên suốt DAG và hỗ trợ retry/backfill đúng batch.
2. Đưa Mart datasets vào Snapshot Publisher và Dashboard.
3. Thêm CI, coverage và automated quality gates.
4. Xóa legacy pipeline sau khi full-suite test xác nhận an toàn.

<!-- PART5_ARCHITECTURE_BEGIN -->
### Part 5 — Production pipeline after legacy retirement

````text
Open-Meteo
    ↓
Airflow DAG with one deterministic batch context
    ↓
MinIO Raw → Transform → Data Quality → MinIO Clean
    ├──→ TimescaleDB
    │       └──→ FastAPI read-only operational endpoints ──┐
    ├──→ AQI Alerts                                        │
    └──→ MinIO Mart                                        │
              └─────────────────────────────────────────────┤
                                                            ↓
                                                   Snapshot Publisher
                                                            ↓
                                              Immutable local JSON release
                                                            ↓
                                              Private S3 → Lambda → Dashboard
````

#### Runtime ownership

- MinIO/Airflow là production write path duy nhất.
- Public AQI snapshot đọc từ `current_aqi`, `location_summary` và
  `daily_summary` trong MinIO Mart.
- FastAPI tiếp tục phục vụ health, dimensions, alerts, pipeline health và
  data-quality metadata.
- Pipeline local-filesystem và environment guard
  `ALLOW_LEGACY_LOCAL_PIPELINE` đã bị xóa.
- `scripts.sync_local_lake_to_minio` chỉ là migration utility cho dữ liệu lịch
  sử và không được DAG gọi.

#### Enforcement

`src/operations/runtime_inventory.py` và
`contracts/runtime_components.v1.json` là catalog nguồn. Các automated check
ngăn entrypoint/file/import đã retire xuất hiện trở lại.
<!-- PART5_ARCHITECTURE_END -->

<!-- PART6_GOVERNANCE_ARCHITECTURE_BEGIN -->
### Part 6 — Operations and architecture governance

Architecture hiện được quản lý bằng ba lớp tài liệu:

1. `docs/architecture.md` mô tả cấu trúc hiện tại.
2. `docs/adr/` lưu lý do và đánh đổi của các quyết định đã Accepted.
3. `docs/operations_runbook.md` mô tả cách vận hành và phục hồi hệ thống.

AWS public delivery có cost model được version tại
`configs/aws_cost_assumptions.json`. Immutable release dưới `releases/` phải có
lifecycle; `current.json` nằm ngoài prefix và không được expire.

`contracts/operations_documentation.v1.json` lưu catalog và SHA-256 của tài liệu
quan trọng. Local quality gate và CI từ chối catalog stale, ADR thiếu section,
lifecycle sai prefix hoặc cost config không hợp lệ.
<!-- PART6_GOVERNANCE_ARCHITECTURE_END -->

[↑ Về mục lục](#mục-lục)

---

<a id="chapter-batch-execution"></a>

## Chương 2 — Batch context và Airflow execution

*Nguồn: [`docs/batch_execution.md`](batch_execution.md)*

### Mục tiêu

Mỗi DAG run phải xử lý đúng một batch từ đầu đến cuối. Retry của một task không được tự quét MinIO rồi chọn một batch mới hơn.

DAG truyền bốn biến môi trường giống nhau vào mọi task:

| Biến | Ý nghĩa |
|---|---|
| `PIPELINE_BATCH_ID` | ID cố định của batch trong DAG run |
| `PIPELINE_PARTITION_DATE` | Partition ngày theo `Asia/Ho_Chi_Minh` |
| `PIPELINE_PARTITION_HOUR` | Partition giờ theo `Asia/Ho_Chi_Minh` |
| `PIPELINE_STARTED_AT` | Logical time của DAG run, có timezone |

Batch mặc định được tạo từ `logical_date` của Airflow:

````text
20260731T140000Z_airflow
````

Với logical time `2026-07-31T14:00:00+00:00`, partition tương ứng tại Việt Nam là:

````text
partition_date=2026-07-31
partition_hour=21
````

### Luồng batch

````text
Airflow logical_date
        ↓
Pipeline batch context
        ↓
Extract đúng batch_id
        ↓
Transform đọc đúng run_summary.json
        ↓
Data Quality đọc đúng transform_summary.json
        ↓
Load / Alerts / Mart đọc đúng quality summary
        ↓
Pipeline Health gom đúng summary của batch
        ↓
Snapshot kiểm tra FastAPI đang phục vụ đúng batch
        ↓
S3 uploader kiểm tra manifest đúng batch
````

Các object quan trọng được khóa theo cùng đường dẫn:

````text
Raw:
open_meteo/air_quality/date=<date>/hour=<hour>/batch_id=<batch_id>/run_summary.json

Transform:
transformed/air_quality/hourly/date=<date>/hour=<hour>/batch_id=<batch_id>/transform_summary.json

Data Quality:
quality/air_quality/hourly/date=<date>/hour=<hour>/batch_id=<batch_id>/data_quality_summary.json

Load:
pipeline/load/timescaledb/date=<date>/hour=<hour>/batch_id=<batch_id>/load_summary.json
````

### Chế độ chạy

#### Airflow batch mode

Khi đủ bốn biến môi trường, script chạy ở chế độ:

````text
AIRFLOW_BATCH
````

Script chỉ đọc và ghi batch được chỉ định. Nếu một summary hoặc object trỏ sang batch khác, task dừng ngay.

#### Manual latest mode

Khi chạy script trực tiếp mà không truyền biến batch context, hành vi cũ vẫn được giữ:

````powershell
python -m scripts.transform_latest_minio_batch
````

Script chạy ở chế độ:

````text
LATEST_MANUAL
````

Chế độ này vẫn tìm batch hợp lệ mới nhất, phù hợp cho kiểm tra thủ công. Airflow không sử dụng chế độ này.

### Trigger thủ công với batch context

Khi trigger DAG bằng Airflow UI hoặc API, có thể truyền toàn bộ context trong `dag_run.conf`:

````json
{
  "batch_id": "20260731T140000Z_replay",
  "partition_date": "2026-07-31",
  "partition_hour": "21",
  "started_at": "2026-07-31T14:00:00+00:00"
}
````

Bốn giá trị phải thống nhất với nhau. `partition_date` và `partition_hour` phải đúng với `started_at` sau khi đổi sang timezone `Asia/Ho_Chi_Minh`.

Không nên chỉ override một phần context. Nếu muốn xử lý lại một Raw batch đã tồn tại, hãy dùng đúng metadata của batch đó và chạy lại các task từ `transform_minio_batch` trở đi, tránh chạy lại extraction nếu không muốn ghi đè Raw object.

### Retry và idempotency

- Retry của Transform, Data Quality, Load, Alerts, Mart, Pipeline Health, Snapshot và S3 upload tiếp tục dùng cùng `batch_id`.
- TimescaleDB loader vẫn dùng upsert theo logical key nên chạy lại batch không tạo bản ghi fact trùng.
- Pipeline Health dùng upsert theo batch và stage/check.
- MinIO summary được ghi vào đúng object path của batch.
- Snapshot và S3 uploader từ chối xuất bản nếu batch mới nhất từ API hoặc manifest không khớp batch context.

Lưu ý: một lần retry Snapshot Publisher có thể tạo một `snapshot_id` phát hành mới, nhưng dữ liệu nghiệp vụ vẫn phải thuộc cùng `batch_id`.

### Kiểm tra cục bộ

````powershell
python -m pytest `
    tests/unit/operations/test_batch_context.py `
    tests/unit/operations/test_airflow_batch_context.py `
    -v
````

Kiểm tra toàn bộ source:

````powershell
python -m compileall dags scripts src tests
python -m scripts.check_runtime_inventory
.\scripts\check_backend_code_quality.ps1
python -m pytest tests -v
````

### Kiểm tra một DAG run

Sau khi DAG chạy thành công, đối chiếu cùng một `batch_id` tại:

1. Log của từng Airflow task.
2. Raw `run_summary.json`.
3. Transform `transform_summary.json`.
4. Data Quality `data_quality_summary.json`.
5. Load `load_summary.json`.
6. Alert `alert_summary.json`.
7. Mart `mart_summary.json`.
8. `pipeline_run_logs` và `data_quality_logs`.
9. Snapshot `manifest.json`.
10. S3 `current.json` và release manifest.

[↑ Về mục lục](#mục-lục)

---

<a id="chapter-mart-serving"></a>

## Chương 3 — MinIO Mart serving layer

*Nguồn: [`docs/mart_serving_layer.md`](mart_serving_layer.md)*

### Mục tiêu

Snapshot Publisher dùng ba Mart dataset thuộc cùng một `batch_id` làm nguồn AQI:

- `current_aqi`
- `location_summary`
- `daily_summary`

FastAPI tiếp tục cung cấp dữ liệu vận hành:

- health
- locations và monitoring points
- alerts
- pipeline health
- data quality

### Luồng dữ liệu

````text
MinIO clean
    ↓
Mart Builder
    ├── current_aqi/data.parquet
    ├── location_summary/data.parquet
    ├── daily_summary/data.parquet
    └── mart_summary.json
             ↓
MinioMartSnapshotReader
             ↓
Snapshot Publisher
             ├── air_quality/latest.json
             ├── air_quality/top_polluted.json
             ├── air_quality/location_summary.json
             ├── air_quality/daily_summary.json
             ├── air_quality/locations/<location_id>.json
             ├── air_quality/points/<point_id>.json
             └── air_quality/history/<point_id>.json
             ↓
S3 release → Lambda/CloudFront → Streamlit Dashboard
````

### Quy tắc nhất quán batch

`mart_summary.json` là nguồn định tuyến duy nhất. Reader không tự chọn từng Parquet độc lập.
Reader kiểm tra:

1. `status` phải là `SUCCESS`.
2. Summary path và tất cả `outputs` phải chứa cùng `batch_id`.
3. Số dòng Parquet phải bằng row count trong summary.
4. Logical key không được trùng.
5. `current_aqi.source_batch_id` phải bằng Mart `batch_id`.
6. Các cột bắt buộc phải đúng contract.

### Tương thích ngược

`SnapshotPublisher` vẫn hỗ trợ chế độ FastAPI cũ khi không truyền `mart_reader`.
Script production `scripts.publish_latest_snapshots` luôn khởi tạo Mart reader, vì vậy DAG dùng Mart.

Dashboard ưu tiên `air_quality/location_summary.json`. Nếu release cũ chưa có file này,
Dashboard quay về tổng hợp từ `air_quality/latest.json` để không làm website ngừng hoạt động.

Mỗi `air_quality/history/<point_id>.json` hiện được tạo từ `daily_summary` và có
`granularity = daily`.

[↑ Về mục lục](#mục-lục)

---

<a id="chapter-fastapi-runtime"></a>

## Chương 4 — FastAPI và runtime inventory

*Nguồn: [`docs/fastapi_runtime_inventory.md`](fastapi_runtime_inventory.md)*

### Decision

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

### Active Airflow entrypoints

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

### Legacy local-lake pipeline retirement

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

### Maintenance utilities

`scripts.sync_local_lake_to_minio` remains as a one-way migration utility for
old local artifacts. It is not a DAG stage and cannot create a second
production write path.

### Machine-readable inventory

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

[↑ Về mục lục](#mục-lục)

---

# Phần II — Mô hình và chất lượng dữ liệu

<a id="chapter-data-contracts"></a>

## Chương 5 — Data contracts

*Nguồn: [`docs/data_contracts.md`](data_contracts.md)*

### Purpose

These contracts define the stable interfaces between ingestion, clean
storage, data quality, TimescaleDB, mart datasets, API responses and public
snapshots.

The contracts are executable. Their machine-readable catalog is generated
from `src/contracts/air_quality_contracts.py` and stored at:

`contracts/air_quality_contracts.v1.json`

### Version policy

Current contract version: **1.0**

- Adding an optional field without changing existing meaning requires a minor
  version.
- Removing or renaming a field requires a major version.
- Changing type, unit, nullability, logical key or meaning requires a major
  version.
- A producer must not silently publish a breaking schema under the same
  version.
- Consumers must reject unsupported major versions instead of guessing.

### Identifier policy

All identifiers are strings.

`location_id="NA"` is the valid identifier for Nghệ An. It must never be
converted to a missing value by CSV readers. Configuration CSV files must
continue to use `keep_default_na=False` or an equivalent explicit string
dtype.

### Time policy

- `forecast_time` must be timezone-aware.
- Clean forecast values use `Asia/Ho_Chi_Minh`.
- `ingested_at`, `source_ingested_at` and `mart_created_at` must be
  timezone-aware and normalized to UTC when persisted.
- Public JSON timestamps must include a UTC offset or `Z`.

### Units

- PM2.5, PM10, CO, NO2, SO2 and O3 use `µg/m³`.
- Latitude and longitude use decimal degrees.
- US AQI and component AQI columns are non-negative integer indexes.

### Raw envelope v1.0

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

### Clean hourly v1.0

Logical key:

`point_id + forecast_time + source`

Required columns:

`point_id`, `location_id`, `point_name`, `point_type`, `latitude`,
`longitude`, `forecast_time`, six pollutant columns, seven AQI columns,
`source`, `batch_id`, `schema_version`, `ingested_at`.

All pollutant and AQI values are required and non-negative.

### Mart contracts

#### mart_current_aqi v1.0

One row per `point_id`. It represents the nearest forecast record to the mart
snapshot hour and includes AQI classification plus source lineage.

#### mart_location_summary v1.0

One row per `location_id`. It aggregates the current records from all active
monitoring points in a province-level location.

#### mart_daily_summary v1.0

Logical key:

`forecast_date + point_id`

It contains hourly coverage, AQI category hour counts, average and maximum
pollutants, worst forecast time and source lineage.

### Public snapshot v1.0

Required envelope fields:

- `status`
- `batch_id` when data is non-empty
- `record_count`
- `data`

`record_count` must exactly equal the number of records in `data`.

The public latest-air-quality record retains point, location, coordinates,
forecast time, pollutant values, AQI values and lineage fields.

### Drift protection

The targeted unit tests verify that:

- Clean contract columns match the existing data-quality layer.
- The clean logical key matches `DUPLICATE_KEY_COLUMNS`.
- Mart input requirements match the mart builder.
- The machine-readable JSON catalog matches the Python declaration.
- `location_id="NA"` remains a valid string.
- Raw and public snapshot envelopes reject structural drift.

[↑ Về mục lục](#mục-lục)

---

<a id="chapter-data-dictionary"></a>

## Chương 6 — Data dictionary

*Nguồn: [`docs/data_dictionary.md`](data_dictionary.md)*

### 1. Mục đích

File này mô tả các bảng và trường dữ liệu dự kiến sử dụng trong Vietnam Air Quality Monitoring & Forecasting Data Pipeline.

Cấu trúc bảng có thể được điều chỉnh khi triển khai TimescaleDB, nhưng phải giữ đúng ý nghĩa nghiệp vụ được mô tả trong tài liệu này.

### 2. Bảng `dim_location`

Bảng lưu thông tin tỉnh/thành được theo dõi.

| Tên cột         | Kiểu dữ liệu dự kiến | Bắt buộc | Mô tả                                               |
| --------------- | -------------------- | -------: | --------------------------------------------------- |
| `location_id`   | VARCHAR              |       Có | Mã định danh duy nhất của tỉnh/thành                |
| `location_name` | VARCHAR              |       Có | Tên tỉnh/thành                                      |
| `region`        | VARCHAR              |       Có | Vùng miền: Miền Bắc, Miền Trung hoặc Miền Nam       |
| `admin_type`    | VARCHAR              |       Có | Loại đơn vị hành chính                              |
| `is_active`     | BOOLEAN              |       Có | Xác định tỉnh/thành có đang được theo dõi hay không |
| `created_at`    | TIMESTAMPTZ          |       Có | Thời gian tạo bản ghi                               |
| `updated_at`    | TIMESTAMPTZ          |       Có | Thời gian cập nhật gần nhất                         |

Ví dụ:

| location_id | location_name | region     | admin_type |
| ----------- | ------------- | ---------- | ---------- |
| `HN`        | Hà Nội        | Miền Bắc   | Thành phố  |
| `HCM`       | TP.HCM        | Miền Nam   | Thành phố  |
| `DN`        | Đà Nẵng       | Miền Trung | Thành phố  |

### 3. Bảng `dim_monitoring_point`

Bảng lưu các điểm theo dõi chất lượng không khí trong từng tỉnh/thành.

| Tên cột       | Kiểu dữ liệu dự kiến | Bắt buộc | Mô tả                                            |
| ------------- | -------------------- | -------: | ------------------------------------------------ |
| `point_id`    | VARCHAR              |       Có | Mã định danh duy nhất của điểm theo dõi          |
| `location_id` | VARCHAR              |       Có | Mã tỉnh/thành chứa điểm theo dõi                 |
| `point_name`  | VARCHAR              |       Có | Tên điểm theo dõi                                |
| `point_type`  | VARCHAR              |       Có | Loại điểm như trung tâm, khu đô thị hoặc ngoại ô |
| `latitude`    | DOUBLE PRECISION     |       Có | Vĩ độ của điểm theo dõi                          |
| `longitude`   | DOUBLE PRECISION     |       Có | Kinh độ của điểm theo dõi                        |
| `is_active`   | BOOLEAN              |       Có | Xác định điểm có đang được sử dụng hay không     |
| `created_at`  | TIMESTAMPTZ          |       Có | Thời gian tạo bản ghi                            |
| `updated_at`  | TIMESTAMPTZ          |       Có | Thời gian cập nhật gần nhất                      |

Ràng buộc dữ liệu:

```text
latitude nằm trong khoảng -90 đến 90
longitude nằm trong khoảng -180 đến 180
```

### 4. Bảng `fact_air_quality_hourly`

Bảng chính lưu dữ liệu chất lượng không khí theo thời gian.

| Tên cột            | Kiểu dữ liệu dự kiến | Bắt buộc | Mô tả                                     |
| ------------------ | -------------------- | -------: | ----------------------------------------- |
| `id`               | BIGSERIAL            |       Có | ID tự tăng của bản ghi                    |
| `point_id`         | VARCHAR              |       Có | Mã điểm theo dõi                          |
| `location_id`      | VARCHAR              |       Có | Mã tỉnh/thành                             |
| `forecast_time`    | TIMESTAMPTZ          |       Có | Thời điểm dữ liệu chất lượng không khí    |
| `pm2_5`            | DOUBLE PRECISION     |    Không | Nồng độ bụi mịn PM2.5                     |
| `pm10`             | DOUBLE PRECISION     |    Không | Nồng độ bụi PM10                          |
| `carbon_monoxide`  | DOUBLE PRECISION     |    Không | Nồng độ CO                                |
| `nitrogen_dioxide` | DOUBLE PRECISION     |    Không | Nồng độ NO2                               |
| `sulphur_dioxide`  | DOUBLE PRECISION     |    Không | Nồng độ SO2                               |
| `ozone`            | DOUBLE PRECISION     |    Không | Nồng độ Ozone                             |
| `us_aqi`           | INTEGER              |    Không | Chỉ số AQI theo chuẩn US AQI              |
| `us_aqi_pm2_5`     | INTEGER              |    Không | AQI thành phần của PM2.5                  |
| `us_aqi_pm10`      | INTEGER              |    Không | AQI thành phần của PM10                   |
| `aqi_level`        | VARCHAR              |    Không | Mức AQI bằng tiếng Việt                   |
| `aqi_severity`     | VARCHAR              |    Không | Mã mức độ AQI                             |
| `source`           | VARCHAR              |       Có | Nguồn dữ liệu, mặc định là `open_meteo`   |
| `ingested_at`      | TIMESTAMPTZ          |       Có | Thời điểm pipeline lấy dữ liệu            |
| `created_at`       | TIMESTAMPTZ          |       Có | Thời điểm bản ghi được tạo trong database |

Khóa chống trùng dự kiến:

```text
point_id + forecast_time + source
```

### 5. Bảng `fact_air_quality_alerts`

Bảng lưu cảnh báo khi AQI vượt ngưỡng.

| Tên cột       | Kiểu dữ liệu dự kiến | Bắt buộc | Mô tả                        |
| ------------- | -------------------- | -------: | ---------------------------- |
| `alert_id`    | BIGSERIAL            |       Có | ID của cảnh báo              |
| `point_id`    | VARCHAR              |       Có | Mã điểm phát sinh cảnh báo   |
| `location_id` | VARCHAR              |       Có | Mã tỉnh/thành                |
| `alert_time`  | TIMESTAMPTZ          |       Có | Thời điểm phát sinh cảnh báo |
| `aqi_value`   | INTEGER              |       Có | Giá trị AQI gây cảnh báo     |
| `aqi_level`   | VARCHAR              |       Có | Mức chất lượng không khí     |
| `severity`    | VARCHAR              |       Có | Mức cảnh báo                 |
| `message`     | TEXT                 |       Có | Nội dung cảnh báo            |
| `status`      | VARCHAR              |       Có | Trạng thái cảnh báo          |
| `created_at`  | TIMESTAMPTZ          |       Có | Thời gian tạo bản ghi        |

Các mức severity:

|  Khoảng AQI | Severity   |
| ----------: | ---------- |
|     101–150 | `MEDIUM`   |
|     151–200 | `HIGH`     |
| 201 trở lên | `CRITICAL` |

### 6. Bảng `pipeline_run_logs`

Bảng lưu trạng thái của từng lần chạy pipeline.

| Tên cột             | Kiểu dữ liệu dự kiến | Bắt buộc | Mô tả                              |
| ------------------- | -------------------- | -------: | ---------------------------------- |
| `run_id`            | UUID hoặc VARCHAR    |       Có | Mã duy nhất của lần chạy           |
| `pipeline_name`     | VARCHAR              |       Có | Tên pipeline                       |
| `source`            | VARCHAR              |       Có | Nguồn dữ liệu                      |
| `started_at`        | TIMESTAMPTZ          |       Có | Thời gian bắt đầu                  |
| `finished_at`       | TIMESTAMPTZ          |    Không | Thời gian kết thúc                 |
| `status`            | VARCHAR              |       Có | Trạng thái lần chạy                |
| `records_extracted` | INTEGER              |       Có | Số record lấy từ API               |
| `records_loaded`    | INTEGER              |       Có | Số record load vào database        |
| `error_message`     | TEXT                 |    Không | Nội dung lỗi nếu pipeline thất bại |
| `duration_seconds`  | DOUBLE PRECISION     |    Không | Tổng thời gian chạy tính bằng giây |

Các trạng thái dự kiến:

* `RUNNING`
* `SUCCESS`
* `FAILED`
* `PARTIAL_SUCCESS`

### 7. Bảng `data_quality_logs`

Bảng lưu kết quả của từng Data Quality Check.

| Tên cột             | Kiểu dữ liệu dự kiến | Bắt buộc | Mô tả                   |
| ------------------- | -------------------- | -------: | ----------------------- |
| `check_id`          | BIGSERIAL            |       Có | ID của lần kiểm tra     |
| `run_id`            | UUID hoặc VARCHAR    |       Có | Mã lần chạy pipeline    |
| `check_name`        | VARCHAR              |       Có | Tên rule kiểm tra       |
| `status`            | VARCHAR              |       Có | Kết quả kiểm tra        |
| `bad_records_count` | INTEGER              |       Có | Số record không hợp lệ  |
| `message`           | TEXT                 |    Không | Mô tả kết quả hoặc lỗi  |
| `created_at`        | TIMESTAMPTZ          |       Có | Thời gian chạy kiểm tra |

Các trạng thái dự kiến:

* `PASSED`
* `FAILED`
* `WARNING`

### 8. Quy tắc phân loại AQI

|  Khoảng AQI | AQI Level                   | AQI Severity          |
| ----------: | --------------------------- | --------------------- |
|        0–50 | Tốt                         | `GOOD`                |
|      51–100 | Trung bình                  | `MODERATE`            |
|     101–150 | Không tốt cho nhóm nhạy cảm | `UNHEALTHY_SENSITIVE` |
|     151–200 | Xấu                         | `UNHEALTHY`           |
|     201–300 | Rất xấu                     | `VERY_UNHEALTHY`      |
| 301 trở lên | Nguy hại                    | `HAZARDOUS`           |

### 9. Nguồn dữ liệu

Nguồn dữ liệu chính:

```text
Open-Meteo Air Quality API
```

Giá trị chuẩn của trường `source`:

```text
open_meteo
```

Open-Meteo cung cấp dữ liệu mô hình và dự báo theo tọa độ. Dữ liệu không phải dữ liệu đo trực tiếp từ trạm quan trắc tại tất cả tỉnh/thành.

[↑ Về mục lục](#mục-lục)

---

# Phần III — Kiểm thử và vận hành

<a id="chapter-continuous-integration"></a>

## Chương 7 — Continuous Integration

*Nguồn: [`docs/continuous_integration.md`](continuous_integration.md)*

Repository sử dụng GitHub Actions để tự động kiểm tra mã nguồn trên mỗi lần:

- Push vào nhánh `main`.
- Tạo hoặc cập nhật pull request hướng vào `main`.
- Chạy thủ công bằng nút **Run workflow**.

Workflow nằm tại:

````text
.github/workflows/ci.yml
````

### Các job trong workflow

#### Code quality

Job này chạy:

1. Cài Python 3.11 và dependency phát triển.
2. Kiểm tra dependency bằng `pip check`.
3. Chạy Ruff lint.
4. Chạy Ruff format check.
5. Kiểm tra data contract catalog không bị lệch khỏi source code.
6. Kiểm tra runtime inventory không bị lệch khỏi repository.

#### Tests and coverage

Job này chạy toàn bộ unit test và integration test trong `tests/`, sau đó đo coverage cho:

````text
src/
api/
````

Ngưỡng coverage tối thiểu ban đầu là **60%**. Workflow tạo hai loại báo cáo:

- `coverage.xml`: định dạng máy đọc.
- `htmlcov/`: báo cáo HTML có thể tải từ GitHub Actions artifact.

Coverage artifact được giữ trong 14 ngày.

### Chạy kiểm tra trên Windows trước khi push

Kích hoạt virtual environment:

````powershell
cd "C:\Users\kkk\Documents\DE\Air Quality Project\Project\vietnam-air-quality-pipeline"
.\.venv\Scripts\Activate.ps1
````

Cài dependency phát triển:

````powershell
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
````

Chạy kiểm tra chất lượng code:

````powershell
.\scripts\check_backend_code_quality.ps1
````

Chạy test và coverage:

````powershell
.\scripts\run_backend_tests_with_coverage.ps1
````

Mở báo cáo HTML:

````powershell
Start-Process ".\htmlcov\index.html"
````

### Ý nghĩa trạng thái workflow

- **Code quality xanh:** lint, format, dependency, contract và runtime inventory đều hợp lệ.
- **Tests and coverage xanh:** toàn bộ test pass và coverage đạt tối thiểu 60%.
- **Workflow đỏ:** mở job bị lỗi, đọc step đầu tiên có dấu đỏ và sửa lỗi từ step đó.

Không nên bỏ qua lỗi CI bằng cách xóa test, giảm coverage tùy tiện hoặc thêm `continue-on-error`. Chỉ giảm ngưỡng coverage khi có lý do kỹ thuật được ghi rõ trong commit hoặc tài liệu.

<!-- PART6_CI_DOCUMENTATION_BEGIN -->
### Operations documentation quality gate

Part 6 bổ sung command:

````powershell
python -m scripts.check_operations_documentation
````

Check này xác minh runbook, ADR, AWS cost config, S3 lifecycle policy và
`contracts/operations_documentation.v1.json`. Khi sửa tài liệu được catalog,
regenerate bằng:

````powershell
python -m scripts.check_operations_documentation --write
````
<!-- PART6_CI_DOCUMENTATION_END -->

[↑ Về mục lục](#mục-lục)

---

<a id="chapter-operations-runbook"></a>

## Chương 8 — Operations runbook

*Nguồn: [`docs/operations_runbook.md`](operations_runbook.md)*

### 1. Mục đích và phạm vi

Runbook này hướng dẫn vận hành pipeline chất lượng không khí từ lúc khởi
động, kiểm tra hằng ngày, xử lý sự cố, khôi phục dữ liệu cho đến phát hành
thay đổi mới.

Phạm vi hệ thống:

````text
Open-Meteo
    ↓
Airflow
    ↓
MinIO Raw → Transform → Data Quality → MinIO Clean
    ├──→ TimescaleDB → FastAPI operational metadata ──┐
    ├──→ AQI Alerts                                    │
    └──→ MinIO Mart ───────────────────────────────────┤
                                                       ↓
                                              Snapshot Publisher
                                                       ↓
                                         Private S3 → Lambda → Dashboard
````

Runbook không thay thế tài liệu AWS chính thức và không biến dữ liệu mô
hình Open-Meteo thành dữ liệu quan trắc y tế chính thức.

### 2. Mục tiêu vận hành

Đây là mục tiêu nội bộ của project, không phải SLA thương mại:

| Mục tiêu | Giá trị |
|---|---:|
| Lịch DAG | Mỗi 30 phút |
| Số DAG run hoạt động đồng thời | 1 |
| Ngưỡng cảnh báo freshness | 90 phút |
| Mục tiêu khôi phục sau khi dependency ổn định | Trong 60 phút |
| Nguồn public AQI | MinIO Mart |
| Production write path | Airflow + MinIO duy nhất |

### 3. Danh mục service

| Service | Container | Vai trò | URL/Port local |
|---|---|---|---|
| Airflow Scheduler | `air-quality-airflow-scheduler` | Lập lịch và chạy task | Nội bộ |
| Airflow Webserver | `air-quality-airflow-webserver` | UI vận hành | `http://localhost:8080` |
| Airflow PostgreSQL | `air-quality-airflow-postgres` | Metadata Airflow | Nội bộ |
| MinIO | `air-quality-minio` | Raw, Clean, Mart, artifacts | `9000`, console `9001` |
| TimescaleDB | `air-quality-timescaledb` | Time-series AQI | `5432` |
| FastAPI | `air-quality-api` | API read-only nội bộ | `http://localhost:8000` |
| Streamlit | `air-quality-dashboard` | Dashboard | `http://localhost:8501` |

### 4. Quy tắc an toàn

1. Không chạy `docker compose down -v` nếu chưa chủ động chấp nhận mất toàn
   bộ volume local.
2. Không restart hoặc force-recreate scheduler khi DAG đang chạy, đặc biệt
   lúc task upload S3 đang hoạt động. LocalExecutor sẽ gửi `SIGTERM` tới
   task con.
3. Không trigger thêm DAG khi một run đang `running`, `queued` hoặc
   `up_for_retry`.
4. Không sửa trực tiếp object immutable dưới `releases/<snapshot_id>/`.
5. Không cập nhật `current.json` trước khi toàn bộ release và manifest đã
   upload thành công.
6. Mọi thay đổi code phải qua Ruff, catalog check và full pytest trước khi
   merge vào `main`.

### 5. Preflight đầu ca vận hành

Đứng tại root repository và kích hoạt virtual environment:

````powershell
.\.venv\Scripts\Activate.ps1
git branch --show-current
git status --short
docker compose ps
````

Điều kiện bình thường:

- Branch vận hành là `main` hoặc branch feature đã biết rõ.
- Working tree sạch trước khi chạy installer hoặc release script.
- Các container chính có trạng thái `healthy`.
- Không có DAG run trùng đang hoạt động.

Kiểm tra DAG import:

````powershell
docker compose exec -T airflow-scheduler `
    airflow dags list-import-errors
````

Kết quả mong đợi:

````text
No data found
````

### 6. Khởi động và dừng hệ thống

#### 6.1 Khởi động bình thường

````powershell
docker compose up -d
docker compose ps
````

Chỉ build lại khi Dockerfile, requirements hoặc image configuration thay
đổi:

````powershell
docker compose up -d --build
````

#### 6.2 Dừng không xóa dữ liệu

````powershell
docker compose down
````

#### 6.3 Xóa volume — thao tác phá hủy

````powershell
docker compose down -v
````

Lệnh trên xóa MinIO, TimescaleDB và Airflow metadata local. Chỉ chạy khi có
kế hoạch reset rõ ràng và đã sao lưu dữ liệu cần giữ.

### 7. Trigger và theo dõi DAG

DAG ID:

````text
vietnam_air_quality_minio_pipeline
````

Trigger một run có ID dễ truy vết:

````powershell
$RunId = "manual__ops_$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))"

docker compose exec -T airflow-scheduler `
    airflow dags trigger `
    -r $RunId `
    vietnam_air_quality_minio_pipeline
````

Xem trạng thái run:

````powershell
docker compose exec -T airflow-scheduler `
    airflow dags list-runs `
    -d vietnam_air_quality_minio_pipeline `
    --no-backfill `
    2>$null |
    Select-String $RunId
````

Xem trạng thái từng task:

````powershell
docker compose exec -T airflow-scheduler `
    airflow tasks states-for-dag-run `
    vietnam_air_quality_minio_pipeline `
    $RunId
````

### 8. Kiểm tra sau mỗi run

#### 8.1 Legacy pipeline đã retire

````powershell
docker compose exec -T `
    -w /opt/airflow/project `
    airflow-scheduler `
    python -m scripts.verify_legacy_pipeline_retired
````

#### 8.2 Mart serving snapshots

````powershell
docker compose exec -T `
    -w /opt/airflow/project `
    airflow-scheduler `
    python -m scripts.verify_mart_serving_snapshots
````

Cần thấy cùng một `batch_id` cho `current_aqi`, `location_summary` và
`daily_summary`.

#### 8.3 S3 pointer

````powershell
aws s3api head-object `
    --bucket $env:AWS_SNAPSHOT_BUCKET `
    --key current.json `
    --region $env:AWS_SNAPSHOT_REGION `
    --profile $env:AWS_SNAPSHOT_PROFILE
````

### 9. Phân loại sự cố

| Mức | Ví dụ | Phản ứng |
|---|---|---|
| P1 | Toàn bộ pipeline không chạy, mất volume, public snapshot không đọc được | Dừng thay đổi mới, bảo toàn dữ liệu, xử lý ngay |
| P2 | Một stage thất bại hoặc dữ liệu stale nhưng snapshot cũ vẫn dùng được | Xử lý trong phiên vận hành hiện tại |
| P3 | Warning dependency, log noise, một test không ảnh hưởng runtime | Ghi issue và xử lý theo kế hoạch |

### 10. Playbook sự cố

#### 10.1 Airflow scheduler/webserver unhealthy

1. Kiểm tra container và log:

   ````powershell
   docker compose ps airflow-scheduler airflow-webserver
   docker compose logs --tail 200 airflow-scheduler
   docker compose logs --tail 200 airflow-webserver
   ````

2. Xác nhận không có task đang chạy trước khi recreate.
3. Restart từng service thay vì toàn bộ stack:

   ````powershell
   docker compose restart airflow-scheduler airflow-webserver
   ````

4. Kiểm tra DAG import lại.

#### 10.2 Task S3 nhận `SIGTERM`

Dấu hiệu:

````text
AirflowTaskTerminated: Task received SIGTERM signal
````

Nguyên nhân thường gặp là scheduler/container bị restart hoặc force-recreate,
không phải lỗi AWS. Hành động:

1. Dừng mọi script rebuild/restart.
2. Kiểm tra task ở `up_for_retry` hay `running`.
3. Để Airflow retry tự động.
4. Chỉ clear riêng task nếu đã qua retry delay mà không chạy lại.
5. Không trigger thêm DAG song song.

#### 10.3 AWS credential hoặc quyền S3 lỗi

Các lỗi điển hình:

````text
ProfileNotFound
NoCredentialsError
AccessDenied
NoSuchBucket
EndpointConnectionError
````

Kiểm tra biến môi trường và file profile trong container:

````powershell
docker compose exec -T airflow-scheduler `
    bash -lc 'echo "$AWS_SNAPSHOT_BUCKET $AWS_SNAPSHOT_REGION $AWS_SNAPSHOT_PROFILE"; ls -la /home/airflow/.aws'
````

Kiểm tra caller identity bằng boto3:

````powershell
docker compose exec -T airflow-scheduler `
    python -c "import os,boto3; s=boto3.Session(profile_name=os.getenv('AWS_SNAPSHOT_PROFILE')); print(s.client('sts').get_caller_identity())"
````

#### 10.4 MinIO báo `NoSuchBucket`

Tình huống thường xảy ra sau khi reset Docker volume.

````powershell
docker compose exec -T airflow-scheduler `
    python -m scripts.setup_minio_buckets
````

Tạo lại alias `mc` nếu cần:

````powershell
docker compose exec minio `
    sh -lc 'mc alias set local http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"'
````

Sau đó cần chạy lại pipeline để tạo Raw, Clean và Mart. Việc tạo bucket không
tự phục hồi dữ liệu cũ.

#### 10.5 Data Quality thất bại

1. Không bypass quality gate.
2. Xem `quality_summary.json` của đúng batch.
3. Kiểm tra schema, batch mismatch, duplicate logical key, dữ liệu âm,
   timezone và freshness.
4. Sửa nguồn hoặc transform; retry đúng batch khi có thể.
5. Không load batch fail vào TimescaleDB.

#### 10.6 TimescaleDB load thất bại

Kiểm tra:

- `batch_id` không rỗng và đồng nhất.
- `latitude`, `longitude` không null.
- logical key `(point_id, forecast_time, source)` không trùng.
- database container healthy.

Không xóa bảng hoặc truncate dữ liệu chỉ để task chuyển xanh.

#### 10.7 Mart hoặc snapshot không cùng batch

1. Đọc `mart_summary.json` của batch.
2. Xác nhận ba output path nằm trong cùng `batch_id`.
3. Chạy `scripts.verify_mart_serving_snapshots`.
4. Không cập nhật S3 pointer nếu manifest hoặc batch không khớp.

#### 10.8 Dashboard stale

Kiểm tra theo thứ tự:

1. DAG run mới nhất có `success` không.
2. Mart verifier có pass không.
3. `current.json` có trỏ tới release mới không.
4. Lambda có đọc được pointer và manifest không.
5. Dashboard cache có cần refresh không.

#### 10.9 Docker disk full hoặc filesystem read-only

1. Dừng trigger mới.
2. Kiểm tra Docker Desktop disk usage.
3. Sao lưu source Git và dữ liệu cần giữ.
4. Dọn image/build cache trước khi nghĩ tới reset volume.
5. Sau reset, tạo lại bucket và chạy pipeline từ đầu.

### 11. Backup và restore

#### 11.1 Source code

Git remote là bản sao lưu chính của source. Trước thay đổi lớn:

````powershell
git status --short
git log -3 --oneline
git push origin main
````

#### 11.2 TimescaleDB

Tạo logical backup:

````powershell
docker compose exec -T timescaledb `
    pg_dump `
    -U $env:POSTGRES_USER `
    -d $env:POSTGRES_DB `
    -Fc > backups\air_quality_db.dump
````

Restore phải thực hiện vào database thử nghiệm trước khi áp dụng production.

#### 11.3 MinIO

Dùng `mc mirror` sang một thư mục hoặc endpoint backup riêng. Không mirror
ngược vào bucket đang hoạt động nếu chưa kiểm tra prefix và quyền ghi.

#### 11.4 S3 public snapshot

Release là immutable. `current.json` chỉ là pointer nên có thể rollback bằng
cách cập nhật pointer tới một release đã xác minh, không sửa nội dung release.

### 12. Release checklist

Trước merge:

````powershell
.\scripts\format_backend_code.ps1
.\scripts\check_backend_code_quality.ps1
python -m pytest
git diff --check
````

Sau merge:

1. Pull `main` mới nhất.
2. Build/restart chỉ service bị ảnh hưởng.
3. Kiểm tra DAG import.
4. Trigger một manual run.
5. Xác minh legacy retirement, Mart snapshots và S3 pointer.
6. Kiểm tra dashboard.
7. Ghi lại run ID và commit hash.

### 13. Post-incident review

Sau P1/P2, ghi tối thiểu:

- Thời gian bắt đầu và kết thúc.
- Commit/DAG run/batch bị ảnh hưởng.
- Triệu chứng và nguyên nhân gốc.
- Hành động khôi phục.
- Dữ liệu có bị mất hoặc stale không.
- Biện pháp ngăn lặp lại.
- Test hoặc automated check mới cần bổ sung.

[↑ Về mục lục](#mục-lục)

---

<a id="chapter-aws-cost"></a>

## Chương 9 — AWS cost management

*Nguồn: [`docs/aws_cost_management.md`](aws_cost_management.md)*

### 1. Phạm vi chi phí AWS

Pipeline xử lý chính chạy local bằng Docker. Phần AWS hiện tại tập trung ở
public snapshot delivery:

````text
Local Snapshot Publisher
    ↓ PUT/HEAD
Private Amazon S3
    ↓ GET/HEAD
AWS Lambda Snapshot Reader
    ↓ HTTPS response
Streamlit Dashboard / user
    ↓ logs
Amazon CloudWatch Logs
````

Cost model không phải hóa đơn chính thức. Giá AWS thay đổi theo region, tier,
tax, free tier và thời điểm. Trước khi triển khai production, kiểm tra AWS
Pricing Calculator và trang pricing chính thức.

### 2. Cost drivers

| Thành phần | Driver chính |
|---|---|
| S3 storage | Kích thước release × số release được giữ |
| S3 PUT | Số JSON file upload cho mỗi release + pointer |
| S3 GET/HEAD | Lambda reads và uploader idempotency checks |
| Lambda requests | Số request dashboard/public client |
| Lambda compute | Request × memory GB × duration seconds |
| Data transfer out | Dung lượng JSON trả ra Internet |
| CloudWatch Logs | Dung lượng log ingestion và retention |

DAG chạy mỗi 30 phút nên tối đa khoảng:

````text
48 releases/day
≈ 1,461 releases/month với tháng trung bình 30.4375 ngày
````

Nếu không có lifecycle, immutable releases tăng không giới hạn.

### 3. Đo workload thực tế

Cost estimator ưu tiên đọc `data/public_snapshots/manifest.json` và tổng dung
lượng file thật:

````powershell
python -m scripts.estimate_aws_snapshot_cost
````

Xuất JSON để lưu lại baseline:

````powershell
python -m scripts.estimate_aws_snapshot_cost `
    --output-json artifacts\aws_cost_estimate.json
````

Chỉ kiểm tra cấu hình:

````powershell
python -m scripts.estimate_aws_snapshot_cost `
    --check-config
````

Các assumption và rate tham chiếu nằm tại:

````text
configs/aws_cost_assumptions.json
````

Rate trong file là input có thể chỉnh sửa, không phải source of truth. Trước
mỗi cost review, cập nhật theo region `ap-southeast-2` và ghi lại ngày giá.

### 4. Công thức estimator

#### 4.1 S3 storage steady-state

````text
retained_releases = runs_per_day × retention_days
storage_GB = retained_releases × release_size_GB
storage_cost = storage_GB × S3_standard_rate
````

#### 4.2 S3 request

````text
PUT/month = releases/month × (files_per_release + 1 pointer)
HEAD/month = releases/month × (files_per_release + 1 pointer)
GET/month = public_requests/month × reads_per_request
````

`HEAD` được estimator tính vào nhóm GET-like request để không bỏ qua
idempotency checks của uploader.

#### 4.3 Lambda

````text
GB-seconds = requests × (memory_MB / 1024) × (duration_ms / 1000)
````

Estimator trừ free tier đã cấu hình trước khi tính request và compute cost.

#### 4.4 Data transfer và logs

````text
transfer_GB = requests × average_response_KB / 1024 / 1024
log_GB = requests × log_KB_per_request / 1024 / 1024
````

### 5. Lifecycle bắt buộc cho immutable releases

Policy mẫu:

````text
infra/aws/s3/snapshot-release-lifecycle.json
````

Policy chỉ expire prefix `releases/` sau 30 ngày. `current.json` nằm ngoài
prefix nên không bị xóa.

Áp dụng:

````powershell
aws s3api put-bucket-lifecycle-configuration `
    --bucket $env:AWS_SNAPSHOT_BUCKET `
    --lifecycle-configuration file://infra/aws/s3/snapshot-release-lifecycle.json `
    --region $env:AWS_SNAPSHOT_REGION `
    --profile $env:AWS_SNAPSHOT_PROFILE
````

Xác minh:

````powershell
aws s3api get-bucket-lifecycle-configuration `
    --bucket $env:AWS_SNAPSHOT_BUCKET `
    --region $env:AWS_SNAPSHOT_REGION `
    --profile $env:AWS_SNAPSHOT_PROFILE
````

Trước khi áp dụng, cân nhắc thời gian cần rollback và portfolio demo. 30 ngày
là mặc định của project, không phải yêu cầu bắt buộc của AWS.

### 6. Budget và cảnh báo

Tạo AWS Cost Budget với các ngưỡng:

| Alert | Ngưỡng đề xuất |
|---|---:|
| Actual | 50% monthly budget |
| Forecasted | 80% monthly budget |
| Actual | 100% monthly budget |

Với portfolio nhỏ, có thể bắt đầu bằng budget tổng tài khoản 5–10 USD/tháng,
sau đó điều chỉnh theo usage thật. AWS Budgets không cập nhật realtime; dữ
liệu có thể trễ nhiều giờ nên budget không thay thế hard quota.

### 7. Tagging

Áp dụng tag nhất quán cho resource hỗ trợ tag:

| Key | Value mẫu |
|---|---|
| `Project` | `vietnam-air-quality-pipeline` |
| `Environment` | `portfolio` |
| `Owner` | `nguyen-ngoc-tuan-khanh` |
| `ManagedBy` | `manual` hoặc `iac` |

Sau khi tạo tag, cần activate user-defined cost allocation tags trong Billing
để dùng trong Cost Explorer/report. Không ghi secret hoặc thông tin nhạy cảm
vào tag.

### 8. Kiểm soát chi phí theo service

#### S3

- Giữ bucket private và cùng region với Lambda.
- Dùng lifecycle cho `releases/`.
- Không dùng Intelligent-Tiering cho nhiều JSON rất nhỏ nếu monitoring fee
  không có lợi.
- Không bật S3 data event CloudTrail toàn bucket nếu chưa cần.
- Theo dõi số object và tổng bytes, không chỉ GB storage.

#### Lambda

- Bắt đầu với memory thấp phù hợp, đo duration thực tế rồi mới tăng.
- Giữ response dưới giới hạn code đang enforce.
- Đặt log retention hữu hạn, ví dụ 14 hoặc 30 ngày.
- Tránh public polling quá ngắn từ Dashboard.

#### CloudWatch

- Không log full snapshot body.
- Log request path, status, latency và error code ở mức đủ chẩn đoán.
- Đặt retention cho log group thay vì giữ vô thời hạn.

### 9. Cost review hằng tháng

1. Cập nhật pricing date và rate trong config.
2. Chạy estimator bằng snapshot thật.
3. So sánh estimate với Cost Explorer/Bills.
4. Kiểm tra lifecycle vẫn `Enabled`.
5. Kiểm tra Lambda request, duration và error rate.
6. Kiểm tra CloudWatch log ingestion/retention.
7. Ghi chênh lệch và cập nhật assumption.

### 10. Nguồn AWS chính thức

- Amazon S3 Pricing: https://aws.amazon.com/s3/pricing/
- AWS Lambda Pricing: https://aws.amazon.com/lambda/pricing/
- Amazon CloudWatch Pricing: https://aws.amazon.com/cloudwatch/pricing/
- AWS Price List API: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html
- Cost allocation tags: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/cost-alloc-tags.html
- AWS Budgets: https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html

[↑ Về mục lục](#mục-lục)

---

# Phần IV — Lịch sử và quyết định kiến trúc

<a id="chapter-legacy-retirement"></a>

## Chương 10 — Legacy local pipeline retirement

*Nguồn: [`docs/legacy_local_pipeline_retirement.md`](legacy_local_pipeline_retirement.md)*

### Status

Completed after the MinIO pipeline, fixed batch context and Mart serving layer
passed full static and runtime verification.

### Decision

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

### Removed entrypoints

- `scripts.extract_all_monitoring_points`
- `scripts.transform_latest_raw_batch`
- `scripts.run_data_quality_latest_batch`
- `scripts.load_latest_clean_batch`
- `scripts.sync_latest_pipeline_health_logs`

### Removed implementation modules

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

### Retained migration utility

`scripts.sync_local_lake_to_minio` and `src.load.minio_lake_sync` remain
available only to migrate historical files already present under
`data/local_lake`.

They are not referenced by the Airflow DAG and do not write to TimescaleDB.

### Safety controls

Runtime inventory version 2 enforces:

1. The Airflow DAG uses exactly the ten active entrypoints.
2. Every retired component path is absent.
3. Retained Python code does not import retired modules.
4. Active and maintenance entrypoints resolve to real files.
5. FastAPI remains read-only and provides required operational routes.
6. Snapshot AQI datasets come from MinIO Mart.

### Rollback

The removed code remains recoverable from Git history. For historical
investigation, check out the commit before Part 5 in a separate branch or
worktree. Do not reconnect the old implementation to the active DAG.

### Verification

````powershell
python -m scripts.check_runtime_inventory
python -m scripts.verify_legacy_pipeline_retired
python -m pytest
.\scripts\check_backend_code_quality.ps1
````

[↑ Về mục lục](#mục-lục)

---

<a id="chapter-adr-index"></a>

## Chương 11 — Architecture Decision Records

*Nguồn: [`docs/adr/README.md`](adr/README.md)*

Thư mục này lưu các quyết định kiến trúc quan trọng của project. ADR đã
`Accepted` không được sửa để thay đổi lịch sử quyết định; nếu kiến trúc đổi,
tạo ADR mới và đánh dấu ADR cũ là `Superseded`.

| ADR | Quyết định | Trạng thái |
|---|---|---|
| [0001](adr/0001-single-production-pipeline.md) | Airflow + MinIO là production write path duy nhất | Accepted |
| [0002](adr/0002-deterministic-batch-context.md) | Một batch context xuyên suốt DAG | Accepted |
| [0003](adr/0003-minio-mart-serving.md) | Public AQI snapshot đọc từ MinIO Mart | Accepted |
| [0004](adr/0004-private-s3-immutable-releases.md) | Private S3 + immutable release + Lambda reader | Accepted |

### Template cho ADR mới

````text
# ADR-NNNN — Tên quyết định

- Status: Proposed | Accepted | Superseded | Rejected
- Date: YYYY-MM-DD
- Deciders: ...

## Context
## Decision
## Consequences
## Alternatives considered
## Validation
````

[↑ Về mục lục](#mục-lục)

---

<a id="chapter-adr-0001"></a>

## Chương 12 — ADR-0001 — Single production pipeline

*Nguồn: [`docs/adr/0001-single-production-pipeline.md`](adr/0001-single-production-pipeline.md)*

- Status: Accepted
- Date: 2026-08-02
- Deciders: Project owner

### Context

Repository từng có hai implementation song song: pipeline local-filesystem
và pipeline MinIO. Hai write path làm tăng nguy cơ chọn nhầm batch, sửa một
nơi nhưng quên nơi còn lại, tạo test trùng và khiến vận hành khó xác định
artifact nào là nguồn chính thức.

### Decision

Airflow điều phối pipeline MinIO là production write path duy nhất. Raw,
Clean, Mart và operational artifact được ghi vào các bucket MinIO. Code
local legacy đã bị xóa khỏi repository.

`scripts.sync_local_lake_to_minio` được giữ như migration utility một chiều
cho artifact lịch sử, không phải DAG stage và không được phép trở thành write
path thứ hai.

### Consequences

Tích cực:

- Một nguồn sự thật cho batch và object path.
- Runtime inventory có thể kiểm soát toàn bộ entrypoint active.
- Giảm code trùng, test trùng và ambiguity khi recovery.

Đánh đổi:

- MinIO trở thành dependency bắt buộc cho pipeline đầy đủ.
- Reset Docker volume sẽ xóa data lake local nếu không backup.
- Migration artifact cũ phải đi qua utility riêng.

### Alternatives considered

1. Giữ cả hai pipeline và dùng environment flag: bị loại vì vẫn duy trì hai
   implementation.
2. Chuyển hoàn toàn sang local filesystem: bị loại vì không phản ánh object
   storage architecture của portfolio Data Engineering.

### Validation

- Runtime inventory yêu cầu đúng 10 DAG entrypoint active.
- Automated check từ chối file/import legacy xuất hiện lại.
- Full pytest và runtime DAG đã pass sau khi retire code local.

[↑ Về mục lục](#mục-lục)

---

<a id="chapter-adr-0002"></a>

## Chương 13 — ADR-0002 — Deterministic batch context

*Nguồn: [`docs/adr/0002-deterministic-batch-context.md`](adr/0002-deterministic-batch-context.md)*

- Status: Accepted
- Date: 2026-08-02
- Deciders: Project owner

### Context

Khi mỗi stage tự tìm object "mới nhất", retry hoặc manual run có thể khiến
Transform, Quality, Load, Mart và Snapshot chọn các batch khác nhau. Điều này
đặc biệt nguy hiểm khi hai DAG run gần nhau hoặc một task bị retry.

### Decision

DAG tạo một batch context gồm `batch_id`, partition date/hour và timestamp
bắt đầu. Mọi task nhận cùng context và phải kiểm tra summary/artifact đúng
batch trước khi xử lý.

Manual override chỉ được chấp nhận nếu giá trị an toàn và toàn bộ partition
khớp timestamp đã khai báo.

### Consequences

Tích cực:

- Retry và backfill có tính quyết định.
- Summary, Parquet, database load và snapshot có thể truy vết cùng batch.
- Giảm race condition do "latest object".

Đánh đổi:

- Entrypoint phải nhận và validate thêm context.
- Một artifact sai batch làm task fail sớm thay vì tự chọn batch khác.

### Alternatives considered

1. Luôn tìm object có timestamp lớn nhất: bị loại vì không ổn định khi chạy
   song song/retry.
2. Chỉ truyền `batch_id` mà không truyền partition: bị loại vì không đủ để
   tạo exact object path và validate thời gian.

### Validation

Unit test kiểm tra mọi Python task nhận đủ context và batch ID deterministic.
Các stage từ Transform tới S3 uploader từ chối artifact không đúng expected
batch.

[↑ Về mục lục](#mục-lục)

---

<a id="chapter-adr-0003"></a>

## Chương 14 — ADR-0003 — MinIO Mart serving

*Nguồn: [`docs/adr/0003-minio-mart-serving.md`](adr/0003-minio-mart-serving.md)*

- Status: Accepted
- Date: 2026-08-02
- Deciders: Project owner

### Context

Snapshot Publisher từng gọi nhiều endpoint FastAPI để đọc AQI từ
TimescaleDB rồi tự tổng hợp lại dữ liệu mà Mart đã có. Cách này tăng query,
tăng thời gian publish và tạo hai nơi chứa aggregation logic.

### Decision

Snapshot Publisher đọc ba dataset AQI trực tiếp từ cùng một
`mart_summary.json`:

- `current_aqi`
- `location_summary`
- `daily_summary`

`mart_summary.json` là nguồn định tuyến cho object path và batch ID. FastAPI
tiếp tục cung cấp health, dimensions, alerts, pipeline health và data-quality
metadata.

### Consequences

Tích cực:

- Public AQI dùng đúng curated serving layer.
- Giảm query TimescaleDB và xử lý pandas trong Dashboard.
- Ba dataset được kiểm tra cùng batch và row count.

Đánh đổi:

- Snapshot Publisher phụ thuộc MinIO Mart và summary contract.
- Thay đổi schema Mart phải cập nhật reader, snapshot contract và dashboard.

### Alternatives considered

1. Giữ toàn bộ serving qua FastAPI: bị loại vì duplicate aggregation và query
   overhead.
2. Dashboard đọc MinIO trực tiếp: bị loại vì sẽ phải public object storage và
   làm client chịu trách nhiệm access control.

### Validation

Reader kiểm tra status, expected batch, schema, row count và logical key.
Runtime verifier xác nhận snapshot `current_aqi`, `location_summary` và
`daily_summary` cùng batch.

[↑ Về mục lục](#mục-lục)

---

<a id="chapter-adr-0004"></a>

## Chương 15 — ADR-0004 — Private S3 immutable releases

*Nguồn: [`docs/adr/0004-private-s3-immutable-releases.md`](adr/0004-private-s3-immutable-releases.md)*

- Status: Accepted
- Date: 2026-08-02
- Deciders: Project owner

### Context

Dashboard cần dữ liệu public nhưng database, MinIO và FastAPI không nên mở
trực tiếp ra Internet. Cập nhật snapshot tại cùng object key cũng có thể khiến
client đọc một release chưa hoàn chỉnh.

### Decision

Mỗi lần publish tạo một release bất biến dưới:

````text
releases/<snapshot_id>/...
````

Uploader ghi toàn bộ JSON và manifest trước, sau đó mới cập nhật
`current.json`. S3 bucket giữ private. Lambda Snapshot Reader chỉ hỗ trợ
`GET`/`HEAD`, validate path và đọc object được phép từ bucket cùng region.

Lifecycle chỉ được áp dụng cho prefix `releases/`; `current.json` không bị
expire.

### Consequences

Tích cực:

- Không public database hoặc S3 bucket.
- Cập nhật pointer có tính atomic ở mức release.
- Có thể rollback pointer tới release đã xác minh.
- Immutable cache-control phù hợp cho file release.

Đánh đổi:

- Số object tăng theo mỗi DAG run.
- Cần lifecycle, budget và theo dõi request để kiểm soát chi phí.
- Lambda thêm một hop và CloudWatch logs.

### Alternatives considered

1. Public S3 bucket: bị loại vì giảm kiểm soát truy cập.
2. Dashboard gọi FastAPI public: bị loại vì mở operational service và
   database path ra Internet.
3. Ghi đè cùng key cho mọi snapshot: bị loại vì không có immutable release và
   rollback rõ ràng.

### Validation

Uploader kiểm tra manifest, SHA-256 metadata, idempotency và chỉ cập nhật
pointer sau khi release thành công. Lambda từ chối method và object path không
hợp lệ.

[↑ Về mục lục](#mục-lục)

---

# Phần V — Portfolio và minh họa

<a id="chapter-screenshots"></a>

## Chương 16 — Screenshot guide

*Nguồn: [`docs/screenshots/README.md`](screenshots/README.md)*

Thư mục này chứa ảnh chạy thật dùng trong README và hồ sơ portfolio.

Không dùng ảnh giả lập hoặc ảnh có dữ liệu bí mật. Trước khi chụp, kiểm tra kỹ ảnh không chứa:

- Password, access key hoặc secret key.
- Lambda Function URL đầy đủ nếu URL không muốn công khai.
- AWS account ID.
- Địa chỉ email cá nhân không cần thiết.
- Terminal hiển thị file `.env`.

### Ảnh bắt buộc

#### 1. `01-dashboard-map.png`

Trang: **Bản đồ AQI**.

Nội dung nên có:

- Tiêu đề dashboard.
- Thời gian dữ liệu cập nhật.
- Bộ lọc tỉnh/thành và ngưỡng AQI.
- Nền bản đồ Việt Nam.
- Marker màu và AQI legend.
- Một tỉnh đang được chọn để thể hiện khả năng zoom.

Kích thước đề xuất: 1600 × 900 hoặc lớn hơn, tỷ lệ 16:9.

#### 2. `02-dashboard-analytics.png`

Trang: **Phân tích**.

Nội dung nên có:

- Bộ chọn khoảng thời gian.
- Biểu đồ Altair có dải màu AQI.
- Đường đánh dấu thời gian hiện tại.
- Hai hoặc ba tỉnh đang được so sánh.
- Metric AQI và delta nếu có dữ liệu.

#### 3. `03-dashboard-history.png`

Trang: **Lịch sử AQI**.

Nội dung nên có:

- Bộ chọn tỉnh và monitoring point.
- Khoảng ngày được chọn.
- Biểu đồ lịch sử.
- Nút tải CSV.

#### 4. `04-dashboard-operations.png`

Trang: **Trạng thái hệ thống**.

Nội dung nên có:

- Pipeline health.
- Trạng thái các stage.
- Data Quality summary.
- Batch ID hoặc thời gian chạy mới nhất, nhưng không để lộ secret.

### Ảnh bổ sung

#### 5. `05-airflow-dag.png`

Airflow Graph View của DAG:

````text
vietnam_air_quality_minio_pipeline
````

Ảnh nên hiển thị đầy đủ mười task và trạng thái thành công của một DAG run.

#### 6. `06-minio-data-lake.png`

MinIO Console hiển thị ba bucket:

````text
air-quality-raw
air-quality-clean
air-quality-mart
````

Có thể mở một partition để thể hiện cấu trúc `date/hour/batch_id`, nhưng không cần hiển thị credentials.

#### 7. `07-fastapi-docs.png`

FastAPI Swagger UI tại:

````text
http://localhost:8000/docs
````

Ảnh nên hiển thị các nhóm endpoint chính.

### Cách chụp trên Windows 11

1. Mở trang cần chụp và đặt trình duyệt ở mức zoom 90% hoặc 100%.
2. Ẩn bookmark bar và các tab không liên quan.
3. Nhấn `Win + Shift + S`.
4. Chọn vùng chứa giao diện chính.
5. Lưu file PNG đúng tên trong thư mục này.
6. Không đổi tên file sau khi README đã dùng đường dẫn ảnh.

### Kiểm tra trước khi commit

Chạy:

````powershell
Get-ChildItem docs\screenshots
````

Kết quả tối thiểu cần có:

````text
01-dashboard-map.png
02-dashboard-analytics.png
03-dashboard-history.png
04-dashboard-operations.png
README.md
````

Sau khi bốn ảnh bắt buộc đã có, mở `README.md` ở thư mục gốc và bỏ phần comment HTML bao quanh bảng screenshot.

Kiểm tra thay đổi:

````powershell
git status --short
git diff -- README.md docs/screenshots/README.md
````

Commit đề xuất:

````powershell
git add README.md docs/screenshots
git commit -m "docs: add portfolio README and project screenshots"
````

[↑ Về mục lục](#mục-lục)

---
