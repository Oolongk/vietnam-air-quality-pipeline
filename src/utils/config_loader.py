from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

LOCATIONS_PATH = PROJECT_ROOT / "configs" / "locations.csv"
MONITORING_POINTS_PATH = (
    PROJECT_ROOT / "configs" / "monitoring_points.csv"
)

LOCATION_COLUMNS = {
    "location_id",
    "location_name",
    "region",
    "admin_type",
    "is_active",
}

MONITORING_POINT_COLUMNS = {
    "point_id",
    "location_id",
    "point_name",
    "point_type",
    "latitude",
    "longitude",
    "is_active",
}


def _validate_required_columns(
    dataframe: pd.DataFrame,
    required_columns: set[str],
    file_name: str,
) -> None:
    missing_columns = required_columns - set(dataframe.columns)

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))

        raise ValueError(
            f"{file_name} đang thiếu các cột bắt buộc: "
            f"{missing_text}"
        )


def _validate_not_blank(
    dataframe: pd.DataFrame,
    columns: list[str],
    file_name: str,
) -> None:
    for column in columns:
        blank_mask = (
            dataframe[column].isna()
            | dataframe[column]
            .astype(str)
            .str.strip()
            .eq("")
        )

        if blank_mask.any():
            row_numbers = (
                dataframe.index[blank_mask] + 2
            ).tolist()

            raise ValueError(
                f"{file_name}: cột '{column}' bị trống "
                f"tại dòng {row_numbers}"
            )


def _parse_boolean_column(
    series: pd.Series,
    column_name: str,
    file_name: str,
) -> pd.Series:
    boolean_mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "yes": True,
        "no": False,
    }

    normalized = (
        series.astype(str)
        .str.strip()
        .str.lower()
    )

    invalid_mask = ~normalized.isin(boolean_mapping)

    if invalid_mask.any():
        invalid_values = sorted(
            normalized[invalid_mask]
            .unique()
            .tolist()
        )

        raise ValueError(
            f"{file_name}: cột '{column_name}' có "
            f"giá trị boolean không hợp lệ: "
            f"{invalid_values}"
        )

    return normalized.map(boolean_mapping).astype(bool)


def load_locations(
    path: Path = LOCATIONS_PATH,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file: {path}"
        )

    dataframe = pd.read_csv(
        path,
        dtype=str,
        encoding="utf-8",
    )

    dataframe.columns = dataframe.columns.str.strip()

    _validate_required_columns(
        dataframe,
        LOCATION_COLUMNS,
        path.name,
    )

    text_columns = [
        "location_id",
        "location_name",
        "region",
        "admin_type",
    ]

    _validate_not_blank(
        dataframe,
        text_columns + ["is_active"],
        path.name,
    )

    for column in text_columns:
        dataframe[column] = (
            dataframe[column]
            .astype(str)
            .str.strip()
        )

    dataframe["is_active"] = _parse_boolean_column(
        dataframe["is_active"],
        "is_active",
        path.name,
    )

    duplicate_mask = dataframe[
        "location_id"
    ].duplicated(keep=False)

    if duplicate_mask.any():
        duplicate_ids = sorted(
            dataframe.loc[
                duplicate_mask,
                "location_id",
            ]
            .unique()
            .tolist()
        )

        raise ValueError(
            f"{path.name}: location_id bị trùng: "
            f"{duplicate_ids}"
        )

    return dataframe


def load_monitoring_points(
    path: Path = MONITORING_POINTS_PATH,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file: {path}"
        )

    dataframe = pd.read_csv(
        path,
        dtype=str,
        encoding="utf-8",
    )

    dataframe.columns = dataframe.columns.str.strip()

    _validate_required_columns(
        dataframe,
        MONITORING_POINT_COLUMNS,
        path.name,
    )

    text_columns = [
        "point_id",
        "location_id",
        "point_name",
        "point_type",
    ]

    _validate_not_blank(
        dataframe,
        text_columns
        + [
            "latitude",
            "longitude",
            "is_active",
        ],
        path.name,
    )

    for column in text_columns:
        dataframe[column] = (
            dataframe[column]
            .astype(str)
            .str.strip()
        )

    for column in ["latitude", "longitude"]:
        try:
            dataframe[column] = pd.to_numeric(
                dataframe[column],
                errors="raise",
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{path.name}: cột '{column}' "
                "phải là số"
            ) from error

    dataframe["is_active"] = _parse_boolean_column(
        dataframe["is_active"],
        "is_active",
        path.name,
    )

    duplicate_mask = dataframe[
        "point_id"
    ].duplicated(keep=False)

    if duplicate_mask.any():
        duplicate_ids = sorted(
            dataframe.loc[
                duplicate_mask,
                "point_id",
            ]
            .unique()
            .tolist()
        )

        raise ValueError(
            f"{path.name}: point_id bị trùng: "
            f"{duplicate_ids}"
        )

    invalid_latitude = ~dataframe[
        "latitude"
    ].between(-90, 90)

    if invalid_latitude.any():
        invalid_ids = dataframe.loc[
            invalid_latitude,
            "point_id",
        ].tolist()

        raise ValueError(
            f"{path.name}: latitude không hợp lệ "
            f"tại các point_id: {invalid_ids}"
        )

    invalid_longitude = ~dataframe[
        "longitude"
    ].between(-180, 180)

    if invalid_longitude.any():
        invalid_ids = dataframe.loc[
            invalid_longitude,
            "point_id",
        ].tolist()

        raise ValueError(
            f"{path.name}: longitude không hợp lệ "
            f"tại các point_id: {invalid_ids}"
        )

    return dataframe


def load_project_config(
) -> tuple[pd.DataFrame, pd.DataFrame]:
    locations = load_locations()
    monitoring_points = load_monitoring_points()

    valid_location_ids = set(
        locations["location_id"]
    )

    point_location_ids = set(
        monitoring_points["location_id"]
    )

    missing_location_ids = (
        point_location_ids - valid_location_ids
    )

    if missing_location_ids:
        missing_text = ", ".join(
            sorted(missing_location_ids)
        )

        raise ValueError(
            "monitoring_points.csv đang tham chiếu "
            "location_id không tồn tại: "
            f"{missing_text}"
        )

    return locations, monitoring_points


def main() -> None:
    locations, monitoring_points = (
        load_project_config()
    )

    active_locations = locations[
        locations["is_active"]
    ]

    active_points = monitoring_points[
        monitoring_points["is_active"]
    ]

    print("Kiểm tra cấu hình thành công.")
    print(
        f"Tổng số tỉnh/thành: {len(locations)}"
    )
    print(
        "Tỉnh/thành đang hoạt động: "
        f"{len(active_locations)}"
    )
    print(
        "Tổng số điểm theo dõi: "
        f"{len(monitoring_points)}"
    )
    print(
        "Điểm theo dõi đang hoạt động: "
        f"{len(active_points)}"
    )

    print()
    print("Số điểm theo từng tỉnh/thành:")

    point_counts = (
        active_points
        .groupby("location_id")["point_id"]
        .count()
        .sort_index()
    )

    print(point_counts.to_string())


if __name__ == "__main__":
    main()