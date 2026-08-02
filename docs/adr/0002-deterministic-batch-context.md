# ADR-0002 — Dùng một deterministic batch context xuyên suốt DAG

- Status: Accepted
- Date: 2026-08-02
- Deciders: Project owner

## Context

Khi mỗi stage tự tìm object "mới nhất", retry hoặc manual run có thể khiến
Transform, Quality, Load, Mart và Snapshot chọn các batch khác nhau. Điều này
đặc biệt nguy hiểm khi hai DAG run gần nhau hoặc một task bị retry.

## Decision

DAG tạo một batch context gồm `batch_id`, partition date/hour và timestamp
bắt đầu. Mọi task nhận cùng context và phải kiểm tra summary/artifact đúng
batch trước khi xử lý.

Manual override chỉ được chấp nhận nếu giá trị an toàn và toàn bộ partition
khớp timestamp đã khai báo.

## Consequences

Tích cực:

- Retry và backfill có tính quyết định.
- Summary, Parquet, database load và snapshot có thể truy vết cùng batch.
- Giảm race condition do "latest object".

Đánh đổi:

- Entrypoint phải nhận và validate thêm context.
- Một artifact sai batch làm task fail sớm thay vì tự chọn batch khác.

## Alternatives considered

1. Luôn tìm object có timestamp lớn nhất: bị loại vì không ổn định khi chạy
   song song/retry.
2. Chỉ truyền `batch_id` mà không truyền partition: bị loại vì không đủ để
   tạo exact object path và validate thời gian.

## Validation

Unit test kiểm tra mọi Python task nhận đủ context và batch ID deterministic.
Các stage từ Transform tới S3 uploader từ chối artifact không đúng expected
batch.
