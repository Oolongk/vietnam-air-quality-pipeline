# Operations Runbook — Vietnam Air Quality Pipeline

## 1. Mục đích và phạm vi

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

## 2. Mục tiêu vận hành

Đây là mục tiêu nội bộ của project, không phải SLA thương mại:

| Mục tiêu | Giá trị |
|---|---:|
| Lịch DAG | Mỗi 30 phút |
| Số DAG run hoạt động đồng thời | 1 |
| Ngưỡng cảnh báo freshness | 90 phút |
| Mục tiêu khôi phục sau khi dependency ổn định | Trong 60 phút |
| Nguồn public AQI | MinIO Mart |
| Production write path | Airflow + MinIO duy nhất |

## 3. Danh mục service

| Service | Container | Vai trò | URL/Port local |
|---|---|---|---|
| Airflow Scheduler | `air-quality-airflow-scheduler` | Lập lịch và chạy task | Nội bộ |
| Airflow Webserver | `air-quality-airflow-webserver` | UI vận hành | `http://localhost:8080` |
| Airflow PostgreSQL | `air-quality-airflow-postgres` | Metadata Airflow | Nội bộ |
| MinIO | `air-quality-minio` | Raw, Clean, Mart, artifacts | `9000`, console `9001` |
| TimescaleDB | `air-quality-timescaledb` | Time-series AQI | `5432` |
| FastAPI | `air-quality-api` | API read-only nội bộ | `http://localhost:8000` |
| Streamlit | `air-quality-dashboard` | Dashboard | `http://localhost:8501` |

## 4. Quy tắc an toàn

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

## 5. Preflight đầu ca vận hành

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

## 6. Khởi động và dừng hệ thống

### 6.1 Khởi động bình thường

````powershell
docker compose up -d
docker compose ps
````

Chỉ build lại khi Dockerfile, requirements hoặc image configuration thay
đổi:

````powershell
docker compose up -d --build
````

### 6.2 Dừng không xóa dữ liệu

````powershell
docker compose down
````

### 6.3 Xóa volume — thao tác phá hủy

````powershell
docker compose down -v
````

Lệnh trên xóa MinIO, TimescaleDB và Airflow metadata local. Chỉ chạy khi có
kế hoạch reset rõ ràng và đã sao lưu dữ liệu cần giữ.

## 7. Trigger và theo dõi DAG

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

## 8. Kiểm tra sau mỗi run

### 8.1 Legacy pipeline đã retire

````powershell
docker compose exec -T `
    -w /opt/airflow/project `
    airflow-scheduler `
    python -m scripts.verify_legacy_pipeline_retired
````

### 8.2 Mart serving snapshots

````powershell
docker compose exec -T `
    -w /opt/airflow/project `
    airflow-scheduler `
    python -m scripts.verify_mart_serving_snapshots
````

Cần thấy cùng một `batch_id` cho `current_aqi`, `location_summary` và
`daily_summary`.

### 8.3 S3 pointer

````powershell
aws s3api head-object `
    --bucket $env:AWS_SNAPSHOT_BUCKET `
    --key current.json `
    --region $env:AWS_SNAPSHOT_REGION `
    --profile $env:AWS_SNAPSHOT_PROFILE
````

## 9. Phân loại sự cố

| Mức | Ví dụ | Phản ứng |
|---|---|---|
| P1 | Toàn bộ pipeline không chạy, mất volume, public snapshot không đọc được | Dừng thay đổi mới, bảo toàn dữ liệu, xử lý ngay |
| P2 | Một stage thất bại hoặc dữ liệu stale nhưng snapshot cũ vẫn dùng được | Xử lý trong phiên vận hành hiện tại |
| P3 | Warning dependency, log noise, một test không ảnh hưởng runtime | Ghi issue và xử lý theo kế hoạch |

## 10. Playbook sự cố

### 10.1 Airflow scheduler/webserver unhealthy

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

### 10.2 Task S3 nhận `SIGTERM`

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

### 10.3 AWS credential hoặc quyền S3 lỗi

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

### 10.4 MinIO báo `NoSuchBucket`

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

### 10.5 Data Quality thất bại

1. Không bypass quality gate.
2. Xem `quality_summary.json` của đúng batch.
3. Kiểm tra schema, batch mismatch, duplicate logical key, dữ liệu âm,
   timezone và freshness.
4. Sửa nguồn hoặc transform; retry đúng batch khi có thể.
5. Không load batch fail vào TimescaleDB.

### 10.6 TimescaleDB load thất bại

Kiểm tra:

- `batch_id` không rỗng và đồng nhất.
- `latitude`, `longitude` không null.
- logical key `(point_id, forecast_time, source)` không trùng.
- database container healthy.

Không xóa bảng hoặc truncate dữ liệu chỉ để task chuyển xanh.

### 10.7 Mart hoặc snapshot không cùng batch

1. Đọc `mart_summary.json` của batch.
2. Xác nhận ba output path nằm trong cùng `batch_id`.
3. Chạy `scripts.verify_mart_serving_snapshots`.
4. Không cập nhật S3 pointer nếu manifest hoặc batch không khớp.

### 10.8 Dashboard stale

Kiểm tra theo thứ tự:

1. DAG run mới nhất có `success` không.
2. Mart verifier có pass không.
3. `current.json` có trỏ tới release mới không.
4. Lambda có đọc được pointer và manifest không.
5. Dashboard cache có cần refresh không.

### 10.9 Docker disk full hoặc filesystem read-only

1. Dừng trigger mới.
2. Kiểm tra Docker Desktop disk usage.
3. Sao lưu source Git và dữ liệu cần giữ.
4. Dọn image/build cache trước khi nghĩ tới reset volume.
5. Sau reset, tạo lại bucket và chạy pipeline từ đầu.

## 11. Backup và restore

### 11.1 Source code

Git remote là bản sao lưu chính của source. Trước thay đổi lớn:

````powershell
git status --short
git log -3 --oneline
git push origin main
````

### 11.2 TimescaleDB

Tạo logical backup:

````powershell
docker compose exec -T timescaledb `
    pg_dump `
    -U $env:POSTGRES_USER `
    -d $env:POSTGRES_DB `
    -Fc > backups\air_quality_db.dump
````

Restore phải thực hiện vào database thử nghiệm trước khi áp dụng production.

### 11.3 MinIO

Dùng `mc mirror` sang một thư mục hoặc endpoint backup riêng. Không mirror
ngược vào bucket đang hoạt động nếu chưa kiểm tra prefix và quyền ghi.

### 11.4 S3 public snapshot

Release là immutable. `current.json` chỉ là pointer nên có thể rollback bằng
cách cập nhật pointer tới một release đã xác minh, không sửa nội dung release.

## 12. Release checklist

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

## 13. Post-incident review

Sau P1/P2, ghi tối thiểu:

- Thời gian bắt đầu và kết thúc.
- Commit/DAG run/batch bị ảnh hưởng.
- Triệu chứng và nguyên nhân gốc.
- Hành động khôi phục.
- Dữ liệu có bị mất hoặc stale không.
- Biện pháp ngăn lặp lại.
- Test hoặc automated check mới cần bổ sung.
