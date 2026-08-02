# ADR-0004 — Private S3, immutable release và Lambda Snapshot Reader

- Status: Accepted
- Date: 2026-08-02
- Deciders: Project owner

## Context

Dashboard cần dữ liệu public nhưng database, MinIO và FastAPI không nên mở
trực tiếp ra Internet. Cập nhật snapshot tại cùng object key cũng có thể khiến
client đọc một release chưa hoàn chỉnh.

## Decision

Mỗi lần publish tạo một release bất biến dưới:

````text
releases/<snapshot_id>/...
````

Uploader ghi toàn bộ JSON và manifest trước, sau đó mới cập nhật
`current.json`. S3 bucket giữ private. Lambda Snapshot Reader chỉ hỗ trợ
`GET`/`HEAD`, validate path và đọc object được phép từ bucket cùng region.

Lifecycle chỉ được áp dụng cho prefix `releases/`; `current.json` không bị
expire.

## Consequences

Tích cực:

- Không public database hoặc S3 bucket.
- Cập nhật pointer có tính atomic ở mức release.
- Có thể rollback pointer tới release đã xác minh.
- Immutable cache-control phù hợp cho file release.

Đánh đổi:

- Số object tăng theo mỗi DAG run.
- Cần lifecycle, budget và theo dõi request để kiểm soát chi phí.
- Lambda thêm một hop và CloudWatch logs.

## Alternatives considered

1. Public S3 bucket: bị loại vì giảm kiểm soát truy cập.
2. Dashboard gọi FastAPI public: bị loại vì mở operational service và
   database path ra Internet.
3. Ghi đè cùng key cho mọi snapshot: bị loại vì không có immutable release và
   rollback rõ ràng.

## Validation

Uploader kiểm tra manifest, SHA-256 metadata, idempotency và chỉ cập nhật
pointer sau khi release thành công. Lambda từ chối method và object path không
hợp lệ.
