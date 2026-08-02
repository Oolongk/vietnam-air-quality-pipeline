# ADR-0003 — MinIO Mart là nguồn public AQI snapshot

- Status: Accepted
- Date: 2026-08-02
- Deciders: Project owner

## Context

Snapshot Publisher từng gọi nhiều endpoint FastAPI để đọc AQI từ
TimescaleDB rồi tự tổng hợp lại dữ liệu mà Mart đã có. Cách này tăng query,
tăng thời gian publish và tạo hai nơi chứa aggregation logic.

## Decision

Snapshot Publisher đọc ba dataset AQI trực tiếp từ cùng một
`mart_summary.json`:

- `current_aqi`
- `location_summary`
- `daily_summary`

`mart_summary.json` là nguồn định tuyến cho object path và batch ID. FastAPI
tiếp tục cung cấp health, dimensions, alerts, pipeline health và data-quality
metadata.

## Consequences

Tích cực:

- Public AQI dùng đúng curated serving layer.
- Giảm query TimescaleDB và xử lý pandas trong Dashboard.
- Ba dataset được kiểm tra cùng batch và row count.

Đánh đổi:

- Snapshot Publisher phụ thuộc MinIO Mart và summary contract.
- Thay đổi schema Mart phải cập nhật reader, snapshot contract và dashboard.

## Alternatives considered

1. Giữ toàn bộ serving qua FastAPI: bị loại vì duplicate aggregation và query
   overhead.
2. Dashboard đọc MinIO trực tiếp: bị loại vì sẽ phải public object storage và
   làm client chịu trách nhiệm access control.

## Validation

Reader kiểm tra status, expected batch, schema, row count và logical key.
Runtime verifier xác nhận snapshot `current_aqi`, `location_summary` và
`daily_summary` cùng batch.
