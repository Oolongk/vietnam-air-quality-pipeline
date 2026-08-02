<!-- GENERATED DOCUMENTATION LANDING PAGE -->

# Vietnam Air Quality Pipeline — Tài liệu hệ thống

Kiến trúc, dữ liệu, vận hành, quyết định kỹ thuật và hướng dẫn portfolio trong một tài liệu thống nhất.

## Đọc tài liệu

**[Mở toàn bộ tài liệu dưới dạng một bài liên tục](PROJECT_DOCUMENTATION.md)**

Các file Markdown riêng vẫn được giữ làm source chapter để dễ bảo trì và review trên Git.

## Cấu trúc chương

### Phần I — Kiến trúc và luồng xử lý

1. [Kiến trúc tổng thể](architecture.md)
2. [Batch context và Airflow execution](batch_execution.md)
3. [MinIO Mart serving layer](mart_serving_layer.md)
4. [FastAPI và runtime inventory](fastapi_runtime_inventory.md)
### Phần II — Mô hình và chất lượng dữ liệu

5. [Data contracts](data_contracts.md)
6. [Data dictionary](data_dictionary.md)
### Phần III — Kiểm thử và vận hành

7. [Continuous Integration](continuous_integration.md)
8. [Operations runbook](operations_runbook.md)
9. [AWS cost management](aws_cost_management.md)
### Phần IV — Lịch sử và quyết định kiến trúc

10. [Legacy local pipeline retirement](legacy_local_pipeline_retirement.md)
11. [Architecture Decision Records](adr/README.md)
12. [ADR-0001 — Single production pipeline](adr/0001-single-production-pipeline.md)
13. [ADR-0002 — Deterministic batch context](adr/0002-deterministic-batch-context.md)
14. [ADR-0003 — MinIO Mart serving](adr/0003-minio-mart-serving.md)
15. [ADR-0004 — Private S3 immutable releases](adr/0004-private-s3-immutable-releases.md)
### Phần V — Portfolio và minh họa

16. [Screenshot guide](screenshots/README.md)

## Cập nhật bài gộp

Sau khi sửa một chapter:

````powershell
python -m scripts.build_unified_documentation
python -m scripts.build_unified_documentation --check
````

File `PROJECT_DOCUMENTATION.md` là generated artifact; mọi thay đổi nội dung phải được thực hiện ở source chapter tương ứng.
