# Vietnam Air Quality Pipeline Architecture

## 1. Tổng quan

Vietnam Air Quality Monitoring & Forecasting Data Pipeline là một project Data Engineering dùng để thu thập, xử lý, lưu trữ và hiển thị dữ liệu chất lượng không khí tại Việt Nam.

Nguồn dữ liệu chính của project là Open-Meteo Air Quality API.

Dữ liệu Open-Meteo là dữ liệu mô hình và dự báo theo tọa độ, không phải dữ liệu đo trực tiếp từ trạm quan trắc tại tất cả tỉnh/thành.

## 2. Luồng dữ liệu tổng quát

```text
Open-Meteo Air Quality API
        ↓
Apache Airflow
        ↓
MinIO Raw Zone
        ↓
Transform và chuẩn hóa dữ liệu
        ↓
Data Quality Check
        ↓
MinIO Clean Zone
        ↓
TimescaleDB
        ↓
AQI Level và Alert System
        ↓
FastAPI Backend
        ↓
Streamlit Dashboard
```

## 3. Luồng xử lý chi tiết

```text
1. Airflow đọc danh sách điểm theo dõi từ file cấu hình.

2. Airflow chia các điểm theo dõi thành từng API batch.

3. Pipeline gọi Open-Meteo Air Quality API theo latitude và longitude.

4. Dữ liệu JSON gốc được lưu vào MinIO Raw Zone.

5. Dữ liệu được transform và chuẩn hóa thành cấu trúc chung.

6. Data Quality Check kiểm tra dữ liệu thiếu, dữ liệu âm và dữ liệu trùng.

7. Dữ liệu hợp lệ được lưu vào MinIO Clean Zone.

8. Dữ liệu tổng hợp được lưu vào MinIO Mart Zone.

9. Dữ liệu sạch được load vào TimescaleDB.

10. Hệ thống phân loại AQI level.

11. Hệ thống tạo alert khi AQI lớn hơn hoặc bằng 101.

12. FastAPI đọc dữ liệu từ TimescaleDB.

13. Streamlit gọi FastAPI để hiển thị dashboard.
```

## 4. Các thành phần chính

### Open-Meteo Air Quality API

Cung cấp dữ liệu chất lượng không khí theo tọa độ.

Các biến chính được sử dụng:

* `pm2_5`
* `pm10`
* `carbon_monoxide`
* `nitrogen_dioxide`
* `sulphur_dioxide`
* `ozone`
* `us_aqi`
* `us_aqi_pm2_5`
* `us_aqi_pm10`

### Apache Airflow

Dùng để:

* Chạy pipeline theo lịch.
* Điều phối thứ tự các task.
* Retry khi task gặp lỗi.
* Theo dõi trạng thái thành công hoặc thất bại.
* Lưu log của từng lần chạy pipeline.

Lịch chạy ban đầu:

```text
0 * * * *
```

Pipeline chạy một lần mỗi giờ.

Lịch nâng cấp:

```text
*/30 * * * *
```

Pipeline chạy mỗi 30 phút.

### MinIO

MinIO được sử dụng làm Data Lake local.

Project có ba lớp dữ liệu:

```text
Raw Zone
Clean Zone
Mart Zone
```

#### Raw Zone

Lưu dữ liệu JSON gốc nhận từ API.

```text
raw/open_meteo/air_quality/date=YYYY-MM-DD/hour=HH/batch_id=xxx/data.json
```

#### Clean Zone

Lưu dữ liệu đã làm sạch và chuẩn hóa.

```text
clean/air_quality/hourly/date=YYYY-MM-DD/hour=HH/data.parquet
```

#### Mart Zone

Lưu dữ liệu đã tổng hợp để dashboard truy vấn nhanh hơn.

```text
mart/air_quality/location_summary/date=YYYY-MM-DD/data.parquet
mart/air_quality/daily_summary/date=YYYY-MM-DD/data.parquet
```

### Data Quality Check

Kiểm tra dữ liệu trước khi load vào TimescaleDB.

Một số rule chính:

* `point_id` không được rỗng.
* `location_id` không được rỗng.
* `forecast_time` không được rỗng.
* `pm2_5` không được âm.
* `pm10` không được âm.
* `us_aqi` không được âm.
* `latitude` phải nằm trong khoảng từ `-90` đến `90`.
* `longitude` phải nằm trong khoảng từ `-180` đến `180`.
* `source` phải là `open_meteo`.
* Không được trùng theo `point_id`, `forecast_time` và `source`.

### TimescaleDB

TimescaleDB được dùng để lưu dữ liệu chất lượng không khí theo thời gian.

Database dự kiến gồm các bảng:

* `dim_location`
* `dim_monitoring_point`
* `fact_air_quality_hourly`
* `fact_air_quality_alerts`
* `pipeline_run_logs`
* `data_quality_logs`

### AQI Level và Alert System

Hệ thống sử dụng trường `us_aqi` từ Open-Meteo để phân loại mức chất lượng không khí.

Alert được tạo khi:

```text
AQI >= 101
```

Các mức cảnh báo:

* `MEDIUM`: AQI từ 101 đến 150.
* `HIGH`: AQI từ 151 đến 200.
* `CRITICAL`: AQI từ 201 trở lên.

### FastAPI

FastAPI là lớp backend trung gian giữa TimescaleDB và Streamlit.

Luồng truy vấn:

```text
TimescaleDB
    ↓
FastAPI
    ↓
Streamlit Dashboard
```

FastAPI dự kiến cung cấp các endpoint:

* `GET /health`
* `GET /locations`
* `GET /monitoring-points`
* `GET /current-aqi`
* `GET /current-aqi/{location_id}`
* `GET /history/{location_id}`
* `GET /alerts`
* `GET /top-polluted`
* `GET /pipeline-health`

### Streamlit

Streamlit dùng để xây dựng dashboard.

Dashboard dự kiến gồm:

* Overview Việt Nam.
* Chi tiết tỉnh/thành.
* Monitoring Points.
* AQI Alerts.
* Pipeline Health.

## 5. Phạm vi bản chính

Project bản chính bao gồm:

* Open-Meteo Air Quality API.
* Từ 5 đến 10 tỉnh/thành trong giai đoạn đầu.
* Mở rộng lên 34 tỉnh/thành.
* Từ 1 điểm lên 3 hoặc 5 điểm theo dõi cho mỗi tỉnh/thành.
* Apache Airflow.
* MinIO Raw, Clean và Mart.
* Data Quality Check.
* TimescaleDB.
* AQI Level.
* Alert System.
* FastAPI.
* Streamlit.

## 6. Ngoài phạm vi bản chính

Project bản chính không bao gồm:

* Machine Learning.
* Mô hình tự huấn luyện.
* Kafka.
* Nhiệt độ.
* Độ ẩm.
* Cảm biến vật lý thời gian thực.
* Email hoặc Telegram Alert.

Những thành phần này chỉ có thể được cân nhắc trong các phiên bản nâng cấp sau.

## 7. Giới hạn dữ liệu

Dữ liệu Open-Meteo Air Quality API là dữ liệu mô hình và dự báo theo tọa độ.

Dữ liệu này không đại diện cho dữ liệu đo trực tiếp từ trạm quan trắc tại tất cả tỉnh/thành Việt Nam.

Project được xây dựng cho mục đích học tập và portfolio Data Engineering. Project không dùng để thay thế cảnh báo môi trường hoặc y tế chính thức.
