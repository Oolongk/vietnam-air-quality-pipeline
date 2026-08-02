# Architecture Decision Records

Thư mục này lưu các quyết định kiến trúc quan trọng của project. ADR đã
`Accepted` không được sửa để thay đổi lịch sử quyết định; nếu kiến trúc đổi,
tạo ADR mới và đánh dấu ADR cũ là `Superseded`.

| ADR | Quyết định | Trạng thái |
|---|---|---|
| [0001](0001-single-production-pipeline.md) | Airflow + MinIO là production write path duy nhất | Accepted |
| [0002](0002-deterministic-batch-context.md) | Một batch context xuyên suốt DAG | Accepted |
| [0003](0003-minio-mart-serving.md) | Public AQI snapshot đọc từ MinIO Mart | Accepted |
| [0004](0004-private-s3-immutable-releases.md) | Private S3 + immutable release + Lambda reader | Accepted |

## Template cho ADR mới

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
