# Batch-aware Airflow execution

## Mục tiêu

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

## Luồng batch

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

## Chế độ chạy

### Airflow batch mode

Khi đủ bốn biến môi trường, script chạy ở chế độ:

````text
AIRFLOW_BATCH
````

Script chỉ đọc và ghi batch được chỉ định. Nếu một summary hoặc object trỏ sang batch khác, task dừng ngay.

### Manual latest mode

Khi chạy script trực tiếp mà không truyền biến batch context, hành vi cũ vẫn được giữ:

````powershell
python -m scripts.transform_latest_minio_batch
````

Script chạy ở chế độ:

````text
LATEST_MANUAL
````

Chế độ này vẫn tìm batch hợp lệ mới nhất, phù hợp cho kiểm tra thủ công. Airflow không sử dụng chế độ này.

## Trigger thủ công với batch context

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

## Retry và idempotency

- Retry của Transform, Data Quality, Load, Alerts, Mart, Pipeline Health, Snapshot và S3 upload tiếp tục dùng cùng `batch_id`.
- TimescaleDB loader vẫn dùng upsert theo logical key nên chạy lại batch không tạo bản ghi fact trùng.
- Pipeline Health dùng upsert theo batch và stage/check.
- MinIO summary được ghi vào đúng object path của batch.
- Snapshot và S3 uploader từ chối xuất bản nếu batch mới nhất từ API hoặc manifest không khớp batch context.

Lưu ý: một lần retry Snapshot Publisher có thể tạo một `snapshot_id` phát hành mới, nhưng dữ liệu nghiệp vụ vẫn phải thuộc cùng `batch_id`.

## Kiểm tra cục bộ

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

## Kiểm tra một DAG run

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
