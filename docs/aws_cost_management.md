# AWS Cost Management — Public Snapshot Delivery

## 1. Phạm vi chi phí AWS

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

## 2. Cost drivers

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

## 3. Đo workload thực tế

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

## 4. Công thức estimator

### 4.1 S3 storage steady-state

````text
retained_releases = runs_per_day × retention_days
storage_GB = retained_releases × release_size_GB
storage_cost = storage_GB × S3_standard_rate
````

### 4.2 S3 request

````text
PUT/month = releases/month × (files_per_release + 1 pointer)
HEAD/month = releases/month × (files_per_release + 1 pointer)
GET/month = public_requests/month × reads_per_request
````

`HEAD` được estimator tính vào nhóm GET-like request để không bỏ qua
idempotency checks của uploader.

### 4.3 Lambda

````text
GB-seconds = requests × (memory_MB / 1024) × (duration_ms / 1000)
````

Estimator trừ free tier đã cấu hình trước khi tính request và compute cost.

### 4.4 Data transfer và logs

````text
transfer_GB = requests × average_response_KB / 1024 / 1024
log_GB = requests × log_KB_per_request / 1024 / 1024
````

## 5. Lifecycle bắt buộc cho immutable releases

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

## 6. Budget và cảnh báo

Tạo AWS Cost Budget với các ngưỡng:

| Alert | Ngưỡng đề xuất |
|---|---:|
| Actual | 50% monthly budget |
| Forecasted | 80% monthly budget |
| Actual | 100% monthly budget |

Với portfolio nhỏ, có thể bắt đầu bằng budget tổng tài khoản 5–10 USD/tháng,
sau đó điều chỉnh theo usage thật. AWS Budgets không cập nhật realtime; dữ
liệu có thể trễ nhiều giờ nên budget không thay thế hard quota.

## 7. Tagging

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

## 8. Kiểm soát chi phí theo service

### S3

- Giữ bucket private và cùng region với Lambda.
- Dùng lifecycle cho `releases/`.
- Không dùng Intelligent-Tiering cho nhiều JSON rất nhỏ nếu monitoring fee
  không có lợi.
- Không bật S3 data event CloudTrail toàn bucket nếu chưa cần.
- Theo dõi số object và tổng bytes, không chỉ GB storage.

### Lambda

- Bắt đầu với memory thấp phù hợp, đo duration thực tế rồi mới tăng.
- Giữ response dưới giới hạn code đang enforce.
- Đặt log retention hữu hạn, ví dụ 14 hoặc 30 ngày.
- Tránh public polling quá ngắn từ Dashboard.

### CloudWatch

- Không log full snapshot body.
- Log request path, status, latency và error code ở mức đủ chẩn đoán.
- Đặt retention cho log group thay vì giữ vô thời hạn.

## 9. Cost review hằng tháng

1. Cập nhật pricing date và rate trong config.
2. Chạy estimator bằng snapshot thật.
3. So sánh estimate với Cost Explorer/Bills.
4. Kiểm tra lifecycle vẫn `Enabled`.
5. Kiểm tra Lambda request, duration và error rate.
6. Kiểm tra CloudWatch log ingestion/retention.
7. Ghi chênh lệch và cập nhật assumption.

## 10. Nguồn AWS chính thức

- Amazon S3 Pricing: https://aws.amazon.com/s3/pricing/
- AWS Lambda Pricing: https://aws.amazon.com/lambda/pricing/
- Amazon CloudWatch Pricing: https://aws.amazon.com/cloudwatch/pricing/
- AWS Price List API: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html
- Cost allocation tags: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/cost-alloc-tags.html
- AWS Budgets: https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html
