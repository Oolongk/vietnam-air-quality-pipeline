from __future__ import annotations

import json
import sys
from typing import Any

from src.snapshot import (
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

        if callable(
            reconfigure
        ):
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
    print(
        "Snapshot Publisher hoàn tất."
    )
    print(
        f"Status: {result.get('status')}"
    )
    print(
        "Snapshot ID: "
        f"{result.get('snapshot_id')}"
    )
    print(
        "Generated at: "
        f"{result.get('generated_at')}"
    )
    print(
        "Latest batch ID: "
        f"{result.get('latest_batch_id')}"
    )
    print(
        "Output directory: "
        f"{result.get('output_directory')}"
    )
    print(
        "Số location: "
        f"{result.get('location_count')}"
    )
    print(
        "Số monitoring point: "
        f"{result.get('point_count')}"
    )
    print(
        "Tổng số JSON file: "
        f"{result.get('file_count')}"
    )
    print()


def main() -> int:
    configure_console_encoding()

    print(
        "Bắt đầu tạo public snapshots..."
    )

    try:
        result = publish_snapshots()

    except SnapshotConfigurationError as error:
        print(
            "Snapshot Publisher thất bại "
            "do cấu hình không hợp lệ:",
            file=sys.stderr,
        )
        print(
            str(error),
            file=sys.stderr,
        )

        return 1

    except SnapshotAPIError as error:
        print(
            "Snapshot Publisher thất bại "
            "khi gọi FastAPI:",
            file=sys.stderr,
        )
        print(
            str(error),
            file=sys.stderr,
        )

        return 1

    except SnapshotValidationError as error:
        print(
            "Snapshot Publisher thất bại "
            "do API response không đúng contract:",
            file=sys.stderr,
        )
        print(
            str(error),
            file=sys.stderr,
        )

        return 1

    except SnapshotPublishError as error:
        print(
            "Snapshot Publisher thất bại "
            "khi ghi hoặc thay thế snapshot:",
            file=sys.stderr,
        )
        print(
            str(error),
            file=sys.stderr,
        )

        return 1

    except Exception as error:
        print(
            "Snapshot Publisher gặp lỗi "
            "ngoài dự kiến:",
            file=sys.stderr,
        )
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )

        return 2

    if result.get(
        "status"
    ) != "SUCCESS":
        print(
            "Publisher hoàn tất nhưng status "
            "không phải SUCCESS.",
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

    print_publish_summary(
        result
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )