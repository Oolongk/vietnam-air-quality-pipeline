from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]

LOCATIONS_PATH = PROJECT_ROOT / "configs" / "locations.csv"

MONITORING_POINTS_PATH = PROJECT_ROOT / "configs" / "monitoring_points.csv"


def _read_locations() -> pd.DataFrame:
    return pd.read_csv(
        LOCATIONS_PATH,
        encoding="utf-8-sig",
        keep_default_na=False,
    )


def _read_monitoring_points() -> pd.DataFrame:
    return pd.read_csv(
        MONITORING_POINTS_PATH,
        encoding="utf-8-sig",
        keep_default_na=False,
    )


def _active_rows(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    active_values = dataframe["is_active"].astype(str).str.strip().str.lower()

    return dataframe.loc[
        active_values.isin(
            {
                "true",
                "1",
                "yes",
            }
        )
    ].copy()


def test_project_has_34_active_locations() -> None:
    locations = _read_locations()
    active_locations = _active_rows(locations)

    assert len(locations) == 34
    assert len(active_locations) == 34

    assert locations["location_id"].astype(str).str.strip().ne("").all()

    assert not locations["location_id"].duplicated().any()


def test_project_has_102_active_monitoring_points() -> None:
    monitoring_points = _read_monitoring_points()

    active_points = _active_rows(monitoring_points)

    assert len(monitoring_points) == 102
    assert len(active_points) == 102

    assert monitoring_points["point_id"].astype(str).str.strip().ne("").all()

    assert not monitoring_points["point_id"].duplicated().any()


def test_each_location_has_exactly_three_points() -> None:
    locations = _active_rows(_read_locations())

    monitoring_points = _active_rows(_read_monitoring_points())

    point_counts = monitoring_points.groupby("location_id").size()

    assert set(point_counts.index) == set(locations["location_id"])

    assert (point_counts == 3).all()


def test_monitoring_points_reference_existing_locations() -> None:
    locations = _active_rows(_read_locations())

    monitoring_points = _active_rows(_read_monitoring_points())

    active_location_ids = set(locations["location_id"])

    point_location_ids = set(monitoring_points["location_id"])

    assert point_location_ids.issubset(active_location_ids)


def test_nghe_an_id_is_preserved_as_na_string() -> None:
    locations = _read_locations()

    monitoring_points = _read_monitoring_points()

    assert "NA" in set(locations["location_id"])

    nghe_an_points = monitoring_points.loc[monitoring_points["location_id"] == "NA"]

    assert len(nghe_an_points) == 3

    assert set(nghe_an_points["point_id"]) == {
        "NA_VINH",
        "NA_CUA_LO",
        "NA_THAI_HOA",
    }


def test_monitoring_point_coordinates_are_valid() -> None:
    monitoring_points = _read_monitoring_points()

    latitudes = pd.to_numeric(
        monitoring_points["latitude"],
        errors="raise",
    )

    longitudes = pd.to_numeric(
        monitoring_points["longitude"],
        errors="raise",
    )

    assert latitudes.between(
        -90,
        90,
        inclusive="both",
    ).all()

    assert longitudes.between(
        -180,
        180,
        inclusive="both",
    ).all()

    assert (
        not monitoring_points[
            [
                "latitude",
                "longitude",
            ]
        ]
        .duplicated()
        .any()
    )
