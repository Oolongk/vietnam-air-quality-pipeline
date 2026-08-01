from __future__ import annotations

import json
import sys
from typing import Any

from src.operations.batch_context import (
    PipelineBatchContext,
    PipelineBatchContextError,
)
from src.snapshot import (
    MartSnapshotReaderError,
    MinioMartSnapshotReader,
    SnapshotAPIError,
    SnapshotConfigurationError,
    SnapshotPublishError,
    SnapshotValidationError,
    publish_snapshots,
)


def configure_console_encoding() -> None:
    """
    Cố gắng đặt stdout và stderr thành UTF-8.

    Việc này giúp tiếng Việt hiển thị đúng hơn
    khi script chạy trong PowerShell hoặc Airflow.
    """

    for stream in (
        sys.stdout,
        sys.stderr,
    ):
        reconfigure = getattr(
            stream,
            "reconfigure",
            None,
        )

        if callable(reconfigure):
            reconfigure(
                encoding="utf-8",
                errors="replace",
            )


def print_publish_summary(
    result: dict[str, Any],
) -> None:
    """
    In phần tổng kết ngắn sau khi publish thành công.
    """

    print()
    print("Snapshot Publisher hoàn tất.")
    print(f"Status: {result.get('status')}")
    print(f"Snapshot ID: {result.get('snapshot_id')}")
    print(f"Generated at: {result.get('generated_at')}")
    print(f"Latest batch ID: {result.get('latest_batch_id')}")
    print(f"Output directory: {result.get('output_directory')}")
    print(f"Số location: {result.get('location_count')}")
    print(f"Số monitoring point: {result.get('point_count')}")
    print(f"Tổng số JSON file: {result.get('file_count')}")
    print()


def main() -> int:
    configure_console_encoding()

    print("Bắt đầu tạo public snapshots...")

    try:
        batch_context = PipelineBatchContext.from_environment()
        expected_batch_id = (
            batch_context.batch_id if batch_context is not None else None
        )
        mart_reader = MinioMartSnapshotReader(
            expected_batch_id=expected_batch_id,
        )
        result = publish_snapshots(
            expected_batch_id=expected_batch_id,
            mart_reader=mart_reader,
        )

    except PipelineBatchContextError as error:
        print(
            "Snapshot Publisher thất bại do batch context không hợp lệ:",
            file=sys.stderr,
        )
        print(str(error), file=sys.stderr)
        return 1

    except MartSnapshotReaderError as error:
        print(
            "Snapshot Publisher thất bại khi đọc MinIO Mart:",
            file=sys.stderr,
        )
        print(str(error), file=sys.stderr)
        return 1

    except SnapshotConfigurationError as error:
        print(
            "Snapshot Publisher thất bại do cấu hình không hợp lệ:",
            file=sys.stderr,
        )
        print(
            str(error),
            file=sys.stderr,
        )

        return 1

    except SnapshotAPIError as error:
        print(
            "Snapshot Publisher thất bại khi gọi FastAPI:",
            file=sys.stderr,
        )
        print(
            str(error),
            file=sys.stderr,
        )

        return 1

    except SnapshotValidationError as error:
        print(
            "Snapshot Publisher thất bại do API response không đúng contract:",
            file=sys.stderr,
        )
        print(
            str(error),
            file=sys.stderr,
        )

        return 1

    except SnapshotPublishError as error:
        print(
            "Snapshot Publisher thất bại khi ghi hoặc thay thế snapshot:",
            file=sys.stderr,
        )
        print(
            str(error),
            file=sys.stderr,
        )

        return 1

    except Exception as error:
        print(
            "Snapshot Publisher gặp lỗi ngoài dự kiến:",
            file=sys.stderr,
        )
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )

        return 2

    if result.get("status") != "SUCCESS":
        print(
            "Publisher hoàn tất nhưng status không phải SUCCESS.",
            file=sys.stderr,
        )

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            file=sys.stderr,
        )

        return 1

    if batch_context is not None:
        actual_batch_id = str(result.get("latest_batch_id", "")).strip()
        if actual_batch_id != batch_context.batch_id:
            print(
                "Snapshot Publisher trả về sai batch_id. "
                f"Expected={batch_context.batch_id}; "
                f"actual={actual_batch_id or 'EMPTY'}.",
                file=sys.stderr,
            )
            return 1

    execution_mode = "AIRFLOW_BATCH" if batch_context is not None else "LATEST_MANUAL"
    print(f"Execution mode: {execution_mode}")
    print_publish_summary(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
