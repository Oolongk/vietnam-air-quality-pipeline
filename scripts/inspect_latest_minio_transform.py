from __future__ import annotations

from src.transform.minio_batch_transformer import (
    build_transformed_prefix,
    find_latest_transformable_raw_batch,
)
from src.utils.minio_client import (
    MinioSettings,
)
from src.utils.minio_object_io import (
    get_parquet_object,
)


def main() -> None:
    settings = (
        MinioSettings.from_environment()
    )

    (
        _,
        raw_summary,
    ) = find_latest_transformable_raw_batch(
        settings=settings
    )

    transformed_prefix = (
        build_transformed_prefix(
            partition_date=(
                raw_summary[
                    "partition_date"
                ]
            ),
            partition_hour=(
                raw_summary[
                    "partition_hour"
                ]
            ),
            batch_id=(
                raw_summary[
                    "batch_id"
                ]
            ),
        )
    )

    parquet_object_name = (
        f"{transformed_prefix}/"
        "data.parquet"
    )

    dataframe = get_parquet_object(
        bucket_name=(
            settings.clean_bucket
        ),
        object_name=(
            parquet_object_name
        ),
        settings=settings,
    )

    print(
        "Bucket: "
        f"{settings.clean_bucket}"
    )

    print(
        "Object: "
        f"{parquet_object_name}"
    )

    print(
        "Rows: "
        f"{len(dataframe)}"
    )

    print(
        "Columns: "
        f"{len(dataframe.columns)}"
    )

    print()
    print("Schema:")
    print(dataframe.dtypes)

    print()
    print("Năm dòng đầu:")
    print(
        dataframe.head().to_string(
            index=False
        )
    )

    print()
    print("Số record theo point_id:")

    print(
        dataframe.groupby(
            "point_id"
        ).size()
    )

    print()
    print("Khoảng forecast_time:")

    print(
        "Min: "
        f"{dataframe['forecast_time'].min()}"
    )

    print(
        "Max: "
        f"{dataframe['forecast_time'].max()}"
    )


if __name__ == "__main__":
    main()