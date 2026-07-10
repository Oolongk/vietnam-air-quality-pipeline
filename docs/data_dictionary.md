# Vietnam Air Quality Data Dictionary

## 1. Mục đích

File này mô tả các bảng và trường dữ liệu dự kiến sử dụng trong Vietnam Air Quality Monitoring & Forecasting Data Pipeline.

Cấu trúc bảng có thể được điều chỉnh khi triển khai TimescaleDB, nhưng phải giữ đúng ý nghĩa nghiệp vụ được mô tả trong tài liệu này.

## 2. Bảng `dim_location`

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

## 3. Bảng `dim_monitoring_point`

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

## 4. Bảng `fact_air_quality_hourly`

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

## 5. Bảng `fact_air_quality_alerts`

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

## 6. Bảng `pipeline_run_logs`

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

## 7. Bảng `data_quality_logs`

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

## 8. Quy tắc phân loại AQI

|  Khoảng AQI | AQI Level                   | AQI Severity          |
| ----------: | --------------------------- | --------------------- |
|        0–50 | Tốt                         | `GOOD`                |
|      51–100 | Trung bình                  | `MODERATE`            |
|     101–150 | Không tốt cho nhóm nhạy cảm | `UNHEALTHY_SENSITIVE` |
|     151–200 | Xấu                         | `UNHEALTHY`           |
|     201–300 | Rất xấu                     | `VERY_UNHEALTHY`      |
| 301 trở lên | Nguy hại                    | `HAZARDOUS`           |

## 9. Nguồn dữ liệu

Nguồn dữ liệu chính:

```text
Open-Meteo Air Quality API
```

Giá trị chuẩn của trường `source`:

```text
open_meteo
```

Open-Meteo cung cấp dữ liệu mô hình và dự báo theo tọa độ. Dữ liệu không phải dữ liệu đo trực tiếp từ trạm quan trắc tại tất cả tỉnh/thành.
