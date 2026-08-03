<div align="center">

# Vietnam Air Quality Monitoring & Forecasting Data Pipeline

**End-to-end Data Engineering pipeline for collecting, validating, storing, serving, and visualizing air-quality model data across Vietnam.**

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![CI](https://github.com/Oolongk/vietnam-air-quality-pipeline/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Oolongk/vietnam-air-quality-pipeline/actions/workflows/ci.yml)
[![Apache Airflow](https://img.shields.io/badge/Apache%20Airflow-2.11.2-017CEE?logo=apacheairflow&logoColor=white)](https://airflow.apache.org/)
[![TimescaleDB](https://img.shields.io/badge/TimescaleDB-PostgreSQL%2017-FDB515?logo=postgresql&logoColor=white)](https://www.timescale.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

## Tổng quan

Dự án xây dựng một pipeline Data Engineering hoàn chỉnh để thu thập dữ liệu chất lượng không khí từ **Open-Meteo Air Quality API**, xử lý dữ liệu theo kiến trúc **Raw / Clean / Mart**, kiểm tra chất lượng, lưu dữ liệu chuỗi thời gian vào TimescaleDB, phát hiện cảnh báo AQI và xuất bản snapshot an toàn cho dashboard công khai.

Phạm vi cấu hình hiện tại:

- **34 tỉnh/thành phố** của Việt Nam.
- **102 điểm theo dõi**, gồm 3 tọa độ đại diện cho mỗi tỉnh/thành.
- Pipeline được Airflow lập lịch chạy **mỗi 30 phút**.
- Dữ liệu gồm PM2.5, PM10, CO, NO₂, SO₂, O₃ và US AQI.
- Dashboard có bản đồ, phân tích, lịch sử, cảnh báo và trạng thái vận hành.

> **Lưu ý dữ liệu:** Open-Meteo cung cấp dữ liệu mô hình và dự báo theo tọa độ. Dữ liệu trong dự án không phải phép đo trực tiếp từ trạm quan trắc tại toàn bộ tỉnh/thành và không thay thế cảnh báo môi trường hoặc y tế chính thức.

## Điểm nổi bật

- Data lake ba tầng **Raw / Clean / Mart** trên MinIO.
- Apache Airflow điều phối 10 stage với retry, timeout và callback khi lỗi.
- Data Quality kiểm tra schema, trường bắt buộc, giá trị âm, tọa độ, batch, duplicate và freshness.
- TimescaleDB hypertable lưu dữ liệu AQI theo thời gian.
- Hệ thống phân loại mức AQI và tạo cảnh báo từ ngưỡng `AQI >= 101`.
- FastAPI nội bộ, read-only, tách biệt khỏi Internet công khai.
- Snapshot Publisher xuất dữ liệu JSON theo release bất biến.
- Amazon S3 private kết hợp Lambda Snapshot Reader để phân phối dữ liệu công khai.
- Streamlit dashboard hỗ trợ tìm kiếm, bộ lọc AQI, so sánh tỉnh, lịch sử và tải CSV.
- Bộ unit/integration test được tổ chức theo từng lớp hệ thống và chạy tự động trong CI.
- Runtime inventory và data-contract catalog giúp kiểm soát các thành phần đang hoạt động.

## Kiến trúc hệ thống

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
    B --> Q[Pipeline Health Logs]
    Q --> G
````

Luồng phục vụ dữ liệu công khai hiện tại:

````text
TimescaleDB
    ↓
FastAPI nội bộ, read-only
    ↓
Snapshot Publisher
    ↓
JSON snapshot release
    ↓
Amazon S3 private
    ↓
AWS Lambda Snapshot Reader
    ↓
Streamlit Dashboard
````

FastAPI được bind vào `127.0.0.1` trên máy host và chỉ được các container nội bộ truy cập qua Docker network. Dashboard không kết nối trực tiếp tới database.

Tầng Mart được lưu trên MinIO và là nguồn AQI trực tiếp của Snapshot Publisher.

Xem tài liệu chi tiết tại [docs/architecture.md](docs/architecture.md).

## Airflow DAG

DAG chính:

````text
vietnam_air_quality_minio_pipeline
````

Lịch chạy:

````text
*/30 * * * *
````

Thứ tự xử lý:

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

Cấu hình vận hành chính:

- Tối đa một DAG run hoạt động tại một thời điểm.
- Mỗi task retry tối đa hai lần với exponential backoff.
- Có execution timeout riêng cho từng task.
- Có callback cho task failure, task retry và DAG failure.
- Sự kiện vận hành được ghi ở dạng JSON Lines và có thể gửi tới webhook.

## Data lake layout

### Raw Zone

Lưu payload JSON gốc từ Open-Meteo.

````text
air-quality-raw/
└── open_meteo/air_quality/
    └── date=YYYY-MM-DD/
        └── hour=HH/
            └── batch_id=<batch_id>/
````

### Clean Zone

Lưu dữ liệu đã chuẩn hóa và vượt qua quy trình kiểm tra chất lượng.

````text
air-quality-clean/
├── clean/air_quality/hourly/
│   └── date=YYYY-MM-DD/hour=HH/batch_id=<batch_id>/data.parquet
└── pipeline/quality/
    └── date=YYYY-MM-DD/hour=HH/batch_id=<batch_id>/quality_summary.json
````

### Mart Zone

Lưu dữ liệu tổng hợp và artifact cảnh báo.

````text
air-quality-mart/
├── mart/air_quality/current_aqi/
├── mart/air_quality/location_summary/
├── mart/air_quality/daily_summary/
└── alerts/air_quality/hourly/
````

## Data Quality

Một số rule quan trọng:

- Các trường định danh, nguồn dữ liệu, batch và schema version không được rỗng.
- Tọa độ phải nằm trong giới hạn latitude/longitude hợp lệ.
- Pollutant và AQI không được âm.
- `source` phải khớp nguồn dữ liệu dự kiến.
- `batch_id` trong bản ghi phải khớp batch đang được kiểm tra.
- Không được trùng logical key `(point_id, forecast_time, source)`.
- `ingested_at` phải timezone-aware.
- Số giờ dự báo và độ tươi dữ liệu phải đạt ngưỡng cấu hình.

Data contract dạng máy đọc được nằm tại:

- [`contracts/air_quality_contracts.v1.json`](contracts/air_quality_contracts.v1.json)
- [`docs/data_contracts.md`](docs/data_contracts.md)

## Dashboard

Dashboard Streamlit hiện có sáu trang:

1. **Bản đồ AQI** — bản đồ Carto, tìm tỉnh/thành, lọc theo ngưỡng AQI và zoom theo khu vực.
2. **Phân tích** — xu hướng AQI, so sánh nhiều tỉnh, dải màu ngưỡng và thời gian Việt Nam.
3. **Điểm theo dõi** — chọn và phân tích từng tọa độ đại diện.
4. **Lịch sử AQI** — chọn khoảng ngày và tải dữ liệu lịch sử.
5. **Cảnh báo** — lọc cảnh báo theo mức độ và tải CSV.
6. **Trạng thái hệ thống** — pipeline health, data quality và trạng thái các stage.

Dashboard còn cung cấp:

- Nút làm mới dữ liệu.
- Hiển thị thời điểm cập nhật và cảnh báo dữ liệu cũ.
- Health recommendation theo từng mức AQI.
- URL query parameters cho một số bộ lọc.
- Tải CSV ở các khu vực phân tích chính.

## Screenshots

Ảnh chạy thật sẽ được lưu trong [`docs/screenshots/`](docs/screenshots/). Danh sách tên file và hướng dẫn chụp nằm tại [`docs/screenshots/README.md`](docs/screenshots/README.md).

Sau khi có ảnh, sử dụng bốn ảnh chính sau trong README:

````text
docs/screenshots/01-dashboard-map.png
docs/screenshots/02-dashboard-analytics.png
docs/screenshots/03-dashboard-history.png
docs/screenshots/04-dashboard-operations.png
````

<!--
Bỏ dấu comment này sau khi bốn ảnh trên đã được thêm vào repository.

| AQI Map | Analytics |
|---|---|
| ![AQI map](docs/screenshots/01-dashboard-map.png) | ![Analytics](docs/screenshots/02-dashboard-analytics.png) |

| AQI History | Pipeline Operations |
|---|---|
| ![AQI history](docs/screenshots/03-dashboard-history.png) | ![Pipeline operations](docs/screenshots/04-dashboard-operations.png) |
-->

## Technology stack

| Layer | Technology | Vai trò |
|---|---|---|
| Data source | Open-Meteo Air Quality API | Dữ liệu mô hình và dự báo theo tọa độ |
| Orchestration | Apache Airflow 2.11.2 | Lập lịch, retry, timeout và theo dõi pipeline |
| Object storage | MinIO | Raw, Clean, Mart và operational artifacts |
| Processing | Python, pandas, PyArrow | Transform, validation và Parquet |
| Time-series database | TimescaleDB trên PostgreSQL 17 | Lưu và truy vấn dữ liệu AQI theo thời gian |
| Internal API | FastAPI | API nội bộ, read-only cho health, dimensions và operational metadata |
| Public delivery | Amazon S3 private, AWS Lambda | Xuất bản snapshot mà không mở database ra Internet |
| Dashboard | Streamlit, Altair, PyDeck | Bản đồ, biểu đồ, lịch sử và trạng thái hệ thống |
| Containers | Docker Compose | Môi trường chạy đồng nhất |
| Testing | pytest, pytest-cov | Unit và integration tests |
| Code quality | Ruff | Lint và format Python |

## Repository structure

````text
vietnam-air-quality-pipeline/
├── api/                       # FastAPI nội bộ
├── configs/                   # 34 tỉnh/thành và 102 monitoring points
├── contracts/                 # Runtime inventory và data contracts
├── dags/                      # Airflow DAG
├── dashboard/                 # Streamlit dashboard và snapshot client
├── docker/                    # Dockerfiles cho Airflow, API, dashboard
├── docs/                      # Architecture, dictionary và hướng dẫn
├── infra/aws/lambda/          # Lambda Snapshot Reader
├── scripts/                   # Entrypoint và maintenance commands
├── sql/                       # Schema, indexes và migrations
├── src/                       # Business logic theo từng pipeline layer
├── tests/                     # Unit và integration tests
├── docker-compose.yml
├── pyproject.toml
└── requirements*.txt
````

## Chạy project bằng Docker Compose

### Yêu cầu

- Windows 11, Linux hoặc macOS.
- Docker Desktop hoặc Docker Engine có Docker Compose.
- Git.
- AWS credentials và một S3 bucket private nếu chạy đầy đủ stage xuất bản public snapshot.
- Lambda Function URL hoặc CloudFront URL cho `PUBLIC_SNAPSHOT_BASE_URL` nếu chạy dashboard theo kiến trúc hiện tại.

### 1. Clone repository

````powershell
git clone https://github.com/Oolongk/vietnam-air-quality-pipeline.git
cd vietnam-air-quality-pipeline
````

### 2. Tạo file môi trường

Windows PowerShell:

````powershell
Copy-Item .env.example .env
````

Linux/macOS:

````bash
cp .env.example .env
````

Mở `.env` và thay tối thiểu các giá trị sau:

````text
POSTGRES_PASSWORD
MINIO_ROOT_USER
MINIO_ROOT_PASSWORD
MINIO_ACCESS_KEY
MINIO_SECRET_KEY
AIRFLOW_FERNET_KEY
AIRFLOW_WEBSERVER_SECRET_KEY
AIRFLOW_ADMIN_PASSWORD
AWS_SNAPSHOT_BUCKET
AWS_SNAPSHOT_REGION
AWS_SNAPSHOT_PROFILE
PUBLIC_SNAPSHOT_BASE_URL
````

`MINIO_ACCESS_KEY` và `MINIO_SECRET_KEY` phải khớp với tài khoản MinIO được cấu hình trong container.

### 3. Build và khởi động

````powershell
docker compose up -d --build
````

Kiểm tra container:

````powershell
docker compose ps
````

Các giao diện local:

| Service | URL |
|---|---|
| Streamlit Dashboard | `http://localhost:8501` |
| Airflow | `http://localhost:8080` |
| FastAPI Swagger UI | `http://localhost:8000/docs` |
| MinIO Console | `http://localhost:9001` |
| TimescaleDB | `localhost:5432` |

DAG được tạo ở trạng thái paused. Mở Airflow, tìm `vietnam_air_quality_minio_pipeline`, bật DAG và trigger lần chạy đầu tiên.

### 4. Xem log

````powershell
docker compose logs -f airflow-scheduler
docker compose logs -f airflow-webserver
docker compose logs -f api
docker compose logs -f dashboard
````

### 5. Dừng hệ thống

````powershell
docker compose down
````

Để xóa cả database và object-storage volume local:

````powershell
docker compose down -v
````

> Lệnh `docker compose down -v` xóa toàn bộ dữ liệu local trong TimescaleDB, MinIO và metadata database của Airflow.

## Chạy test và kiểm tra code

Tạo virtual environment:

````powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt -r dashboard/requirements.txt
````

Chạy toàn bộ test và đo coverage cho backend:

````powershell
.\scripts\run_backend_tests_with_coverage.ps1
````

Coverage phải đạt tối thiểu **60%** cho `src/` và `api/`. Báo cáo HTML được tạo tại:

````text
htmlcov/index.html
````

Chạy toàn bộ kiểm tra chất lượng backend:

````powershell
.\scripts\check_backend_code_quality.ps1
````

Lệnh trên kiểm tra Ruff lint, Ruff format, dependency consistency, data contract catalog và runtime inventory.

GitHub Actions tự động chạy cùng các kiểm tra này khi push vào `main` hoặc mở pull request. Xem thêm [tài liệu Continuous Integration](docs/continuous_integration.md).

## API nội bộ

Các endpoint chính:

| Method | Endpoint | Mục đích |
|---|---|---|
| GET | `/health` | Kiểm tra API và database |
| GET | `/api/v1/locations` | Danh sách tỉnh/thành |
| GET | `/api/v1/monitoring-points` | Danh sách điểm theo dõi |
| GET | `/api/v1/air-quality/latest` | Dữ liệu AQI mới nhất |
| GET | `/api/v1/air-quality/top-polluted` | Các khu vực ô nhiễm cao |
| GET | `/api/v1/air-quality/locations/{location_id}` | AQI theo tỉnh/thành |
| GET | `/api/v1/air-quality/points/{point_id}` | AQI theo điểm theo dõi |
| GET | `/api/v1/air-quality/history` | Dữ liệu lịch sử |
| GET | `/api/v1/alerts/latest` | Cảnh báo mới nhất |
| GET | `/api/v1/pipeline/health/latest` | Trạng thái pipeline |
| GET | `/api/v1/data-quality/latest` | Kết quả Data Quality |

FastAPI là dịch vụ nội bộ phục vụ Snapshot Publisher và không được thiết kế làm public Internet API.

## Tài liệu

- [Kiến trúc hệ thống](docs/architecture.md)
- [Data dictionary](docs/data_dictionary.md)
- [Data contracts](docs/data_contracts.md)
- [FastAPI và runtime inventory](docs/fastapi_runtime_inventory.md)
- [Legacy local pipeline retirement](docs/legacy_local_pipeline_retirement.md)
- [Hướng dẫn screenshot](docs/screenshots/README.md)
- [Continuous Integration](docs/continuous_integration.md)

## Giới hạn hiện tại và roadmap

Các cải tiến kiến trúc đang được ưu tiên:

- Truyền một `batch_id` cố định xuyên suốt DAG thay vì mỗi stage tự tìm batch mới nhất.
- Cho Snapshot Publisher và Dashboard sử dụng trực tiếp dữ liệu Mart.
- Xóa pipeline local legacy sau khi full test và runtime review hoàn tất.
- Hoàn thiện thêm runbook vận hành, ADR và ước tính chi phí AWS.

Ngoài phạm vi hiện tại:

- Không sử dụng Kafka.
- Không xây dựng mô hình Machine Learning riêng.
- Không thu thập nhiệt độ hoặc độ ẩm.
- Không thay thế hệ thống quan trắc môi trường chính thức.

## License

Dự án được phát hành theo [MIT License](LICENSE).

## Author

**Nguyen Ngoc Tuan Khanh**

GitHub: [Oolongk](https://github.com/Oolongk)

<!-- PART5_LEGACY_RETIREMENT_BEGIN -->
## Legacy local pipeline retirement

Production hiện chỉ còn một pipeline:

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

Các entrypoint và implementation local-filesystem cũ đã được xóa sau khi full
test suite, DAG runtime và Mart snapshot verification thành công.

`scripts.sync_local_lake_to_minio` vẫn được giữ như công cụ migration một chiều
cho artifact lịch sử; nó không thuộc production DAG.

Runtime inventory v2 kiểm tra rằng:

- DAG chỉ dùng 10 entrypoint MinIO đang hoạt động.
- File và import thuộc pipeline đã retire không còn trong repository.
- FastAPI vẫn read-only và chỉ phục vụ operational metadata.
- Public AQI snapshot được lấy từ MinIO Mart.

Tài liệu chi tiết:
[Legacy local pipeline retirement](docs/legacy_local_pipeline_retirement.md).

Ưu tiên tiếp theo là runbook vận hành, ADR và ước tính chi phí AWS.

## Operations governance

Project đã bổ sung lớp vận hành và governance có thể kiểm tra tự động:

- [Operations runbook](docs/operations_runbook.md) cho startup, monitoring,
  incident response, backup/restore và release checklist.
- [Architecture Decision Records](docs/adr/README.md) lưu bốn quyết định kiến
  trúc cốt lõi.
- [AWS cost management](docs/aws_cost_management.md) mô tả cost drivers,
  lifecycle, budget, tagging và monthly review.
- `scripts.estimate_aws_snapshot_cost` đo file/bytes từ snapshot thật và tạo
  estimate theo assumption có version.
- `scripts.check_operations_documentation` kiểm tra tài liệu, ADR, lifecycle,
  cost config và catalog SHA-256 trong local quality gate lẫn CI.

<!-- PART6_OPERATIONS_GOVERNANCE_END -->

<!-- DOCUMENTATION_BOOK_BEGIN -->
## Tài liệu hệ thống

Toàn bộ tài liệu trong `docs/` được tổ chức thành một documentation book:

- [Trang tài liệu và mục lục](docs/README.md)
- [Đọc toàn bộ tài liệu dưới dạng một bài liên tục](docs/PROJECT_DOCUMENTATION.md)

Các file riêng trong `docs/` là source chapter. Sau khi sửa chapter, chạy:

````powershell
python -m scripts.build_unified_documentation
python -m scripts.check_documentation_book
````
<!-- DOCUMENTATION_BOOK_END -->
