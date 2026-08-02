# ADR-0001 — Airflow và MinIO là production write path duy nhất

- Status: Accepted
- Date: 2026-08-02
- Deciders: Project owner

## Context

Repository từng có hai implementation song song: pipeline local-filesystem
và pipeline MinIO. Hai write path làm tăng nguy cơ chọn nhầm batch, sửa một
nơi nhưng quên nơi còn lại, tạo test trùng và khiến vận hành khó xác định
artifact nào là nguồn chính thức.

## Decision

Airflow điều phối pipeline MinIO là production write path duy nhất. Raw,
Clean, Mart và operational artifact được ghi vào các bucket MinIO. Code
local legacy đã bị xóa khỏi repository.

`scripts.sync_local_lake_to_minio` được giữ như migration utility một chiều
cho artifact lịch sử, không phải DAG stage và không được phép trở thành write
path thứ hai.

## Consequences

Tích cực:

- Một nguồn sự thật cho batch và object path.
- Runtime inventory có thể kiểm soát toàn bộ entrypoint active.
- Giảm code trùng, test trùng và ambiguity khi recovery.

Đánh đổi:

- MinIO trở thành dependency bắt buộc cho pipeline đầy đủ.
- Reset Docker volume sẽ xóa data lake local nếu không backup.
- Migration artifact cũ phải đi qua utility riêng.

## Alternatives considered

1. Giữ cả hai pipeline và dùng environment flag: bị loại vì vẫn duy trì hai
   implementation.
2. Chuyển hoàn toàn sang local filesystem: bị loại vì không phản ánh object
   storage architecture của portfolio Data Engineering.

## Validation

- Runtime inventory yêu cầu đúng 10 DAG entrypoint active.
- Automated check từ chối file/import legacy xuất hiện lại.
- Full pytest và runtime DAG đã pass sau khi retire code local.
