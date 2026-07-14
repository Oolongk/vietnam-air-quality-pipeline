from __future__ import annotations

from src.quality.minio_quality_processor import (
    find_latest_loadable_quality_batch,
)
from src.utils.minio_client import (
    MinioSettings,
)
from src.utils.minio_object_io import (
    get_json_object,
    get_parquet_object,
)


def main() -> None:
    settings = (
        MinioSettings.from_environment()
    )

    (
        quality_summary_object_name,
        quality_summary,
    ) = find_latest_loadable_quality_batch(
        settings=settings
    )

    clean_object_name = (
        quality_summary[
            "clean_object_name"
        ]
    )

    clean_dataframe = (
        get_parquet_object(
            bucket_name=(
                settings.clean_bucket
            ),
            object_name=(
                clean_object_name
            ),
            settings=settings,
        )
    )

    print(
        "Quality summary: "
        f"{quality_summary_object_name}"
    )

    print(
        "Status: "
        f"{quality_summary['status']}"
    )

    print(
        "Clean object: "
        f"{clean_object_name}"
    )

    print(
        "Rows: "
        f"{len(clean_dataframe)}"
    )

    print(
        "Columns: "
        f"{len(clean_dataframe.columns)}"
    )

    print()
    print("Schema:")

    print(
        clean_dataframe.dtypes
    )

    print()
    print("Năm dòng đầu:")

    print(
        clean_dataframe
        .head()
        .to_string(
            index=False
        )
    )

    print()
    print("Số record theo point_id:")

    print(
        clean_dataframe
        .groupby("point_id")
        .size()
    )

    print()
    print("Số giá trị null:")

    null_counts = (
        clean_dataframe
        .isna()
        .sum()
    )

    print(
        null_counts[
            null_counts > 0
        ]
    )

    bad_records_object_name = (
        quality_summary.get(
            "bad_records_object_name"
        )
    )

    if bad_records_object_name:
        bad_dataframe = (
            get_parquet_object(
                bucket_name=(
                    settings.clean_bucket
                ),
                object_name=(
                    bad_records_object_name
                ),
                settings=settings,
            )
        )

        print()
        print("Bad records:")

        print(
            bad_dataframe[
                [
                    "point_id",
                    "forecast_time",
                    "dq_error_codes",
                    "dq_error_messages",
                ]
            ]
            .head(20)
            .to_string(
                index=False
            )
        )


if __name__ == "__main__":
    main()