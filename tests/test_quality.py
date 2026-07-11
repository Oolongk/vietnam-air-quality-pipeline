from pathlib import Path

import pandas as pd

from src.quality.data_quality_checks import (
    run_air_quality_data_quality,
)
from src.quality.quality_processor import (
    process_transformed_batch_quality,
)


def build_valid_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "point_id": "HN_CENTER",
                "location_id": "HN",
                "forecast_time": pd.Timestamp(
                    "2026-07-11 12:00:00",
                    tz="Asia/Ho_Chi_Minh",
                ),
                "pm2_5": 18.5,
                "pm10": 27.4,
                "us_aqi": 61,
                "latitude": 21.0285,
                "longitude": 105.8542,
                "source": "open_meteo",
            },
            {
                "point_id": "HCM_CENTER",
                "location_id": "HCM",
                "forecast_time": pd.Timestamp(
                    "2026-07-11 12:00:00",
                    tz="Asia/Ho_Chi_Minh",
                ),
                "pm2_5": 20.1,
                "pm10": 30.2,
                "us_aqi": 65,
                "latitude": 10.7769,
                "longitude": 106.7009,
                "source": "open_meteo",
            },
        ]
    )


def test_valid_records_pass_all_checks() -> None:
    dataframe = build_valid_dataframe()

    result = run_air_quality_data_quality(
        dataframe
    )

    assert result.total_records == 2
    assert result.valid_count == 2
    assert result.bad_count == 0
    assert result.bad_records.empty

    assert all(
        check["status"] == "PASSED"
        for check in result.check_results
    )


def test_invalid_record_contains_error_reasons() -> None:
    dataframe = build_valid_dataframe()

    dataframe.loc[
        0,
        "point_id",
    ] = ""

    dataframe.loc[
        0,
        "pm2_5",
    ] = -10.0

    dataframe.loc[
        0,
        "source",
    ] = "invalid_source"

    result = run_air_quality_data_quality(
        dataframe
    )

    assert result.valid_count == 1
    assert result.bad_count == 1

    bad_record = result.bad_records.iloc[0]

    assert (
        "POINT_ID_REQUIRED"
        in bad_record["dq_error_codes"]
    )

    assert (
        "PM2_5_NON_NEGATIVE"
        in bad_record["dq_error_codes"]
    )

    assert (
        "SOURCE_OPEN_METEO"
        in bad_record["dq_error_codes"]
    )


def test_duplicate_rows_are_rejected() -> None:
    dataframe = build_valid_dataframe()

    duplicate_row = (
        dataframe.iloc[[0]].copy()
    )

    dataframe = pd.concat(
        [
            dataframe,
            duplicate_row,
        ],
        ignore_index=True,
    )

    result = run_air_quality_data_quality(
        dataframe
    )

    assert result.total_records == 3
    assert result.valid_count == 1
    assert result.bad_count == 2

    assert all(
        "UNIQUE_POINT_TIME_SOURCE"
        in value
        for value in result.bad_records[
            "dq_error_codes"
        ]
    )


def test_quality_processor_writes_clean_output(
    tmp_path: Path,
) -> None:
    transformed_batch = (
        tmp_path
        / "transformed"
        / "air_quality"
        / "hourly"
        / "date=2026-07-11"
        / "hour=12"
        / "batch_id=test_batch"
    )

    transformed_batch.mkdir(
        parents=True,
        exist_ok=True,
    )

    build_valid_dataframe().to_parquet(
        transformed_batch
        / "data.parquet",
        engine="pyarrow",
        index=False,
    )

    (
        transformed_batch
        / "transform_summary.json"
    ).write_text(
        """
{
  "status": "SUCCESS",
  "batch_id": "test_batch",
  "partition_date": "2026-07-11",
  "partition_hour": "12"
}
""".strip(),
        encoding="utf-8",
    )

    clean_root = tmp_path / "clean"
    quality_root = tmp_path / "quality"

    summary = (
        process_transformed_batch_quality(
            transformed_batch_directory=(
                transformed_batch
            ),
            clean_root=clean_root,
            quality_root=quality_root,
        )
    )

    assert summary["status"] == "SUCCESS"
    assert summary["input_records"] == 2
    assert summary["valid_records"] == 2
    assert summary["bad_records"] == 0

    clean_path = (
        clean_root
        / summary["clean_data_path"]
    )

    assert clean_path.exists()

    clean_dataframe = pd.read_parquet(
        clean_path
    )

    assert len(clean_dataframe) == 2