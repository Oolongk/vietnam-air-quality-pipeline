# Vietnam Air Quality Pipeline Architecture

## 1. Mục tiêu

Vietnam Air Quality Monitoring & Forecasting Data Pipeline là một hệ thống Data Engineering dùng để:

- Thu thập dữ liệu chất lượng không khí theo tọa độ.
- Lưu dữ liệu gốc và dữ liệu đã xử lý trong data lake.
- Kiểm tra chất lượng trước khi load database.
- Lưu dữ liệu chuỗi thời gian để truy vấn hiệu quả.
- Phân loại AQI và tạo cảnh báo.
- Xuất bản snapshot công khai mà không mở database trực tiếp ra Internet.
- Hiển thị dữ liệu qua Streamlit dashboard.

Nguồn chính là Open-Meteo Air Quality API. Đây là dữ liệu mô hình và dự báo, không phải dữ liệu đo trực tiếp từ trạm quan trắc tại toàn bộ tỉnh/thành.

## 2. Kiến trúc tổng thể

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

## 3. Active runtime flow

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

## 4. Airflow orchestration

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

## 5. Data lake layers

### Raw Zone

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

### Clean Zone

Bucket:

````text
air-quality-clean
````

Mục đích:

- Lưu dữ liệu đã chuẩn hóa thành Parquet.
- Lưu transform summary và quality summary.
- Chỉ cho phép batch đạt Data Quality đi tiếp tới load và downstream processing.

### Mart Zone

Bucket:

````text
air-quality-mart
````

Datasets:

- `current_aqi`
- `location_summary`
- `daily_summary`
- AQI alert artifacts

Hiện Mart được tạo trong Airflow và lưu trên MinIO. Snapshot Publisher chưa đọc trực tiếp Mart; đây là hạng mục cải tiến kiến trúc tiếp theo.

## 6. Data Quality layer

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

## 7. TimescaleDB

Các bảng chính:

- `dim_location`
- `dim_monitoring_point`
- `fact_air_quality_hourly`
- `fact_air_quality_alerts`
- `pipeline_run_logs`
- `data_quality_logs`

`fact_air_quality_hourly` là hypertable phục vụ truy vấn dữ liệu AQI theo thời gian.

SQL schema, indexes và migrations nằm trong `sql/`.

## 8. AQI alert processing

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

## 9. Internal FastAPI

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

## 10. Snapshot publishing và public delivery

Snapshot Publisher gọi FastAPI, chuẩn hóa payload và ghi các file JSON như:

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

## 11. Dashboard

Dashboard Streamlit đọc snapshot public qua `PUBLIC_SNAPSHOT_BASE_URL`.

Các trang:

1. Bản đồ AQI
2. Phân tích
3. Điểm theo dõi
4. Lịch sử AQI
5. Cảnh báo
6. Trạng thái hệ thống

Dashboard sử dụng Altair cho biểu đồ và PyDeck cho bản đồ.

## 12. Runtime inventory và legacy pipeline

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

## 13. Current architectural improvements

Các hạng mục đang được ưu tiên:

1. Truyền `batch_id` xuyên suốt DAG và hỗ trợ retry/backfill đúng batch.
2. Đưa Mart datasets vào Snapshot Publisher và Dashboard.
3. Thêm CI, coverage và automated quality gates.
4. Xóa legacy pipeline sau khi full-suite test xác nhận an toàn.
