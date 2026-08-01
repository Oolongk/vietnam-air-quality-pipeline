# Part 4 — MinIO Mart Serving Layer

## Mục tiêu

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

## Luồng dữ liệu

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

## Quy tắc nhất quán batch

`mart_summary.json` là nguồn định tuyến duy nhất. Reader không tự chọn từng Parquet độc lập.
Reader kiểm tra:

1. `status` phải là `SUCCESS`.
2. Summary path và tất cả `outputs` phải chứa cùng `batch_id`.
3. Số dòng Parquet phải bằng row count trong summary.
4. Logical key không được trùng.
5. `current_aqi.source_batch_id` phải bằng Mart `batch_id`.
6. Các cột bắt buộc phải đúng contract.

## Tương thích ngược

`SnapshotPublisher` vẫn hỗ trợ chế độ FastAPI cũ khi không truyền `mart_reader`.
Script production `scripts.publish_latest_snapshots` luôn khởi tạo Mart reader, vì vậy DAG dùng Mart.

Dashboard ưu tiên `air_quality/location_summary.json`. Nếu release cũ chưa có file này,
Dashboard quay về tổng hợp từ `air_quality/latest.json` để không làm website ngừng hoạt động.

Mỗi `air_quality/history/<point_id>.json` hiện được tạo từ `daily_summary` và có
`granularity = daily`.
