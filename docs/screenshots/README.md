# Screenshot Guide

Thư mục này chứa ảnh chạy thật dùng trong README và hồ sơ portfolio.

Không dùng ảnh giả lập hoặc ảnh có dữ liệu bí mật. Trước khi chụp, kiểm tra kỹ ảnh không chứa:

- Password, access key hoặc secret key.
- Lambda Function URL đầy đủ nếu URL không muốn công khai.
- AWS account ID.
- Địa chỉ email cá nhân không cần thiết.
- Terminal hiển thị file `.env`.

## Ảnh bắt buộc

### 1. `01-dashboard-map.png`

Trang: **Bản đồ AQI**.

Nội dung nên có:

- Tiêu đề dashboard.
- Thời gian dữ liệu cập nhật.
- Bộ lọc tỉnh/thành và ngưỡng AQI.
- Nền bản đồ Việt Nam.
- Marker màu và AQI legend.
- Một tỉnh đang được chọn để thể hiện khả năng zoom.

Kích thước đề xuất: 1600 × 900 hoặc lớn hơn, tỷ lệ 16:9.

### 2. `02-dashboard-analytics.png`

Trang: **Phân tích**.

Nội dung nên có:

- Bộ chọn khoảng thời gian.
- Biểu đồ Altair có dải màu AQI.
- Đường đánh dấu thời gian hiện tại.
- Hai hoặc ba tỉnh đang được so sánh.
- Metric AQI và delta nếu có dữ liệu.

### 3. `03-dashboard-history.png`

Trang: **Lịch sử AQI**.

Nội dung nên có:

- Bộ chọn tỉnh và monitoring point.
- Khoảng ngày được chọn.
- Biểu đồ lịch sử.
- Nút tải CSV.

### 4. `04-dashboard-operations.png`

Trang: **Trạng thái hệ thống**.

Nội dung nên có:

- Pipeline health.
- Trạng thái các stage.
- Data Quality summary.
- Batch ID hoặc thời gian chạy mới nhất, nhưng không để lộ secret.

## Ảnh bổ sung

### 5. `05-airflow-dag.png`

Airflow Graph View của DAG:

````text
vietnam_air_quality_minio_pipeline
````

Ảnh nên hiển thị đầy đủ mười task và trạng thái thành công của một DAG run.

### 6. `06-minio-data-lake.png`

MinIO Console hiển thị ba bucket:

````text
air-quality-raw
air-quality-clean
air-quality-mart
````

Có thể mở một partition để thể hiện cấu trúc `date/hour/batch_id`, nhưng không cần hiển thị credentials.

### 7. `07-fastapi-docs.png`

FastAPI Swagger UI tại:

````text
http://localhost:8000/docs
````

Ảnh nên hiển thị các nhóm endpoint chính.

## Cách chụp trên Windows 11

1. Mở trang cần chụp và đặt trình duyệt ở mức zoom 90% hoặc 100%.
2. Ẩn bookmark bar và các tab không liên quan.
3. Nhấn `Win + Shift + S`.
4. Chọn vùng chứa giao diện chính.
5. Lưu file PNG đúng tên trong thư mục này.
6. Không đổi tên file sau khi README đã dùng đường dẫn ảnh.

## Kiểm tra trước khi commit

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
