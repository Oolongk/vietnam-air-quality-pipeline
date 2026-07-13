from __future__ import annotations

from minio.error import S3Error

from src.utils.minio_client import (
    MinioConfigurationError,
    MinioOperationError,
    MinioSettings,
    check_minio_connection,
    ensure_buckets,
)


def main() -> None:
    try:
        settings = (
            MinioSettings.from_environment()
        )

        bucket_result = ensure_buckets(
            settings=settings
        )

        connection_info = (
            check_minio_connection()
        )

    except (
        MinioConfigurationError,
        MinioOperationError,
        S3Error,
    ) as error:
        print(
            "Thiết lập MinIO thất bại: "
            f"{error}"
        )

        raise SystemExit(1) from error

    print(
        "Kết nối và thiết lập MinIO "
        "thành công."
    )

    print(
        "Endpoint: "
        f"{connection_info['endpoint']}"
    )

    print(
        "Secure: "
        f"{connection_info['secure']}"
    )

    print("Buckets vừa tạo:")

    if bucket_result["created_buckets"]:
        for bucket_name in (
            bucket_result[
                "created_buckets"
            ]
        ):
            print(
                f"- {bucket_name}"
            )
    else:
        print("- Không có bucket mới.")

    print("Buckets đã tồn tại:")

    if bucket_result["existing_buckets"]:
        for bucket_name in (
            bucket_result[
                "existing_buckets"
            ]
        ):
            print(
                f"- {bucket_name}"
            )
    else:
        print("- Không có.")

    print("Toàn bộ buckets trong MinIO:")

    for bucket_name in (
        connection_info[
            "existing_buckets"
        ]
    ):
        print(
            f"- {bucket_name}"
        )


if __name__ == "__main__":
    main()