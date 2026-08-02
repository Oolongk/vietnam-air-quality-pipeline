# Continuous Integration

Repository sử dụng GitHub Actions để tự động kiểm tra mã nguồn trên mỗi lần:

- Push vào nhánh `main`.
- Tạo hoặc cập nhật pull request hướng vào `main`.
- Chạy thủ công bằng nút **Run workflow**.

Workflow nằm tại:

````text
.github/workflows/ci.yml
````

## Các job trong workflow

### Code quality

Job này chạy:

1. Cài Python 3.11 và dependency phát triển.
2. Kiểm tra dependency bằng `pip check`.
3. Chạy Ruff lint.
4. Chạy Ruff format check.
5. Kiểm tra data contract catalog không bị lệch khỏi source code.
6. Kiểm tra runtime inventory không bị lệch khỏi repository.

### Tests and coverage

Job này chạy toàn bộ unit test và integration test trong `tests/`, sau đó đo coverage cho:

````text
src/
api/
````

Ngưỡng coverage tối thiểu ban đầu là **60%**. Workflow tạo hai loại báo cáo:

- `coverage.xml`: định dạng máy đọc.
- `htmlcov/`: báo cáo HTML có thể tải từ GitHub Actions artifact.

Coverage artifact được giữ trong 14 ngày.

## Chạy kiểm tra trên Windows trước khi push

Kích hoạt virtual environment:

````powershell
cd "C:\Users\kkk\Documents\DE\Air Quality Project\Project\vietnam-air-quality-pipeline"
.\.venv\Scripts\Activate.ps1
````

Cài dependency phát triển:

````powershell
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
````

Chạy kiểm tra chất lượng code:

````powershell
.\scripts\check_backend_code_quality.ps1
````

Chạy test và coverage:

````powershell
.\scripts\run_backend_tests_with_coverage.ps1
````

Mở báo cáo HTML:

````powershell
Start-Process ".\htmlcov\index.html"
````

## Ý nghĩa trạng thái workflow

- **Code quality xanh:** lint, format, dependency, contract và runtime inventory đều hợp lệ.
- **Tests and coverage xanh:** toàn bộ test pass và coverage đạt tối thiểu 60%.
- **Workflow đỏ:** mở job bị lỗi, đọc step đầu tiên có dấu đỏ và sửa lỗi từ step đó.

Không nên bỏ qua lỗi CI bằng cách xóa test, giảm coverage tùy tiện hoặc thêm `continue-on-error`. Chỉ giảm ngưỡng coverage khi có lý do kỹ thuật được ghi rõ trong commit hoặc tài liệu.

<!-- PART6_CI_DOCUMENTATION_BEGIN -->
## Operations documentation quality gate

Part 6 bổ sung command:

````powershell
python -m scripts.check_operations_documentation
````

Check này xác minh runbook, ADR, AWS cost config, S3 lifecycle policy và
`contracts/operations_documentation.v1.json`. Khi sửa tài liệu được catalog,
regenerate bằng:

````powershell
python -m scripts.check_operations_documentation --write
````
<!-- PART6_CI_DOCUMENTATION_END -->
