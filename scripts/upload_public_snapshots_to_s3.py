from __future__ import annotations

import json
import sys
from typing import Any

from src.snapshot import (
    S3SnapshotConfigurationError,
    S3SnapshotUploadError,
    S3SnapshotValidationError,
    upload_public_snapshots_to_s3,
)


def configure_console_encoding() -> None:
    """
    Cấu hình stdout và stderr dùng UTF-8
    khi môi trường hiện tại hỗ trợ.
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


def print_upload_summary(
    result: dict[str, Any],
) -> None:
    """
    In kết quả upload ngắn gọn.
    """

    print()
    print("S3 Snapshot Uploader hoàn tất.")
    print(f"Status: {result.get('status')}")
    print(f"Bucket: {result.get('bucket_name')}")
    print(f"Region: {result.get('region_name')}")
    print(f"Snapshot ID: {result.get('snapshot_id')}")
    print(f"Release prefix: {result.get('release_prefix')}")
    print(f"Pointer key: {result.get('pointer_key')}")
    print(f"Số file local: {result.get('local_file_count')}")
    print(f"Số file đã upload: {result.get('uploaded_file_count')}")
    print(f"Số file được bỏ qua: {result.get('skipped_file_count')}")
    print(f"current.json đã cập nhật: {result.get('pointer_uploaded')}")
    print()


def main() -> int:
    configure_console_encoding()

    print("Bắt đầu upload public snapshots lên Amazon S3...")

    try:
        result = upload_public_snapshots_to_s3()

    except S3SnapshotConfigurationError as error:
        print(
            "S3 Snapshot Uploader thất bại do cấu hình không hợp lệ:",
            file=sys.stderr,
        )

        print(
            str(error),
            file=sys.stderr,
        )

        return 1

    except S3SnapshotValidationError as error:
        print(
            "S3 Snapshot Uploader thất bại do snapshot local không hợp lệ:",
            file=sys.stderr,
        )

        print(
            str(error),
            file=sys.stderr,
        )

        return 1

    except S3SnapshotUploadError as error:
        print(
            "S3 Snapshot Uploader thất bại khi thao tác với Amazon S3:",
            file=sys.stderr,
        )

        print(
            str(error),
            file=sys.stderr,
        )

        return 1

    except Exception as error:
        print(
            "S3 Snapshot Uploader gặp lỗi ngoài dự kiến:",
            file=sys.stderr,
        )

        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )

        return 2

    if result.get("status") != "SUCCESS":
        print(
            "Uploader hoàn tất nhưng status không phải SUCCESS.",
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

    print_upload_summary(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
