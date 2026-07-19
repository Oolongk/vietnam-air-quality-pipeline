from pathlib import Path

import pandas as pd
import pytest

from src.load.dimension_loader import (
    DimensionLoaderError,
    prepare_locations,
    prepare_monitoring_points,
)


def write_csv(
    path: Path,
    dataframe: pd.DataFrame,
) -> None:
    dataframe.to_csv(
        path,
        index=False,
        encoding="utf-8",
    )


def test_prepare_locations_valid(
    tmp_path: Path,
) -> None:
    csv_path = (
        tmp_path
        / "locations.csv"
    )

    dataframe = pd.DataFrame(
        [
            {
                "location_id": "hn",
                "location_name": "Hà Nội",
                "region": "Miền Bắc",
                "admin_type": "Thành phố",
                "is_active": True,
            }
        ]
    )

    write_csv(
        path=csv_path,
        dataframe=dataframe,
    )

    result = prepare_locations(
        csv_path
    )

    assert len(result) == 1

    assert (
        result.iloc[0]["location_id"]
        == "HN"
    )

    assert (
        result.iloc[0]["location_name"]
        == "Hà Nội"
    )


def test_reject_duplicate_location_id(
    tmp_path: Path,
) -> None:
    csv_path = (
        tmp_path
        / "locations.csv"
    )

    dataframe = pd.DataFrame(
        [
            {
                "location_id": "HN",
                "location_name": "Hà Nội",
                "region": "Miền Bắc",
                "admin_type": "Thành phố",
                "is_active": True,
            },
            {
                "location_id": "HN",
                "location_name": "Hà Nội 2",
                "region": "Miền Bắc",
                "admin_type": "Thành phố",
                "is_active": True,
            },
        ]
    )

    write_csv(
        path=csv_path,
        dataframe=dataframe,
    )

    with pytest.raises(
        DimensionLoaderError
    ):
        prepare_locations(
            csv_path
        )


def test_reject_invalid_region(
    tmp_path: Path,
) -> None:
    csv_path = (
        tmp_path
        / "locations.csv"
    )

    dataframe = pd.DataFrame(
        [
            {
                "location_id": "HN",
                "location_name": "Hà Nội",
                "region": "Phía Bắc",
                "admin_type": "Thành phố",
                "is_active": True,
            }
        ]
    )

    write_csv(
        path=csv_path,
        dataframe=dataframe,
    )

    with pytest.raises(
        DimensionLoaderError
    ):
        prepare_locations(
            csv_path
        )


def test_prepare_monitoring_points_valid(
    tmp_path: Path,
) -> None:
    csv_path = (
        tmp_path
        / "monitoring_points.csv"
    )

    dataframe = pd.DataFrame(
        [
            {
                "point_id": "hn_center",
                "location_id": "hn",
                "point_name": "Trung tâm Hà Nội",
                "point_type": "urban_center",
                "latitude": 21.0285,
                "longitude": 105.8542,
                "is_active": True,
            }
        ]
    )

    write_csv(
        path=csv_path,
        dataframe=dataframe,
    )

    result = prepare_monitoring_points(
        csv_path=csv_path,
        valid_location_ids={
            "HN",
        },
    )

    assert len(result) == 1

    assert (
        result.iloc[0]["point_id"]
        == "HN_CENTER"
    )

    assert (
        result.iloc[0]["location_id"]
        == "HN"
    )


def test_reject_unknown_location_id(
    tmp_path: Path,
) -> None:
    csv_path = (
        tmp_path
        / "monitoring_points.csv"
    )

    dataframe = pd.DataFrame(
        [
            {
                "point_id": "ABC_CENTER",
                "location_id": "ABC",
                "point_name": "Điểm ABC",
                "point_type": "urban_center",
                "latitude": 10.0,
                "longitude": 106.0,
                "is_active": True,
            }
        ]
    )

    write_csv(
        path=csv_path,
        dataframe=dataframe,
    )

    with pytest.raises(
        DimensionLoaderError
    ):
        prepare_monitoring_points(
            csv_path=csv_path,
            valid_location_ids={
                "HN",
            },
        )


def test_reject_invalid_latitude(
    tmp_path: Path,
) -> None:
    csv_path = (
        tmp_path
        / "monitoring_points.csv"
    )

    dataframe = pd.DataFrame(
        [
            {
                "point_id": "HN_CENTER",
                "location_id": "HN",
                "point_name": "Trung tâm Hà Nội",
                "point_type": "urban_center",
                "latitude": 200.0,
                "longitude": 105.8542,
                "is_active": True,
            }
        ]
    )

    write_csv(
        path=csv_path,
        dataframe=dataframe,
    )

    with pytest.raises(
        DimensionLoaderError
    ):
        prepare_monitoring_points(
            csv_path=csv_path,
            valid_location_ids={
                "HN",
            },
        )


def test_reject_duplicate_coordinates(
    tmp_path: Path,
) -> None:
    csv_path = (
        tmp_path
        / "monitoring_points.csv"
    )

    dataframe = pd.DataFrame(
        [
            {
                "point_id": "HN_POINT_1",
                "location_id": "HN",
                "point_name": "Điểm 1",
                "point_type": "urban_center",
                "latitude": 21.0285,
                "longitude": 105.8542,
                "is_active": True,
            },
            {
                "point_id": "HN_POINT_2",
                "location_id": "HN",
                "point_name": "Điểm 2",
                "point_type": "residential",
                "latitude": 21.0285,
                "longitude": 105.8542,
                "is_active": True,
            },
        ]
    )

    write_csv(
        path=csv_path,
        dataframe=dataframe,
    )

    with pytest.raises(
        DimensionLoaderError
    ):
        prepare_monitoring_points(
            csv_path=csv_path,
            valid_location_ids={
                "HN",
            },
        )