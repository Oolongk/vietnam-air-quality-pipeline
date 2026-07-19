from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from dotenv import load_dotenv


load_dotenv()


class DimensionLoaderError(RuntimeError):
    """Lỗi kiểm tra hoặc đồng bộ dimension."""


LOCATION_REQUIRED_COLUMNS = {
    "location_id",
    "location_name",
    "region",
    "admin_type",
    "is_active",
}


MONITORING_POINT_REQUIRED_COLUMNS = {
    "point_id",
    "location_id",
    "point_name",
    "point_type",
    "latitude",
    "longitude",
    "is_active",
}


VALID_REGIONS = {
    "Miền Bắc",
    "Miền Trung",
    "Miền Nam",
}


VALID_ADMIN_TYPES = {
    "Tỉnh",
    "Thành phố",
}


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    database: str
    user: str
    password: str

    @classmethod
    def from_environment(
        cls,
    ) -> "DatabaseSettings":
        host = os.getenv(
            "POSTGRES_HOST",
            "localhost",
        ).strip()

        port_text = os.getenv(
            "POSTGRES_PORT",
            "5432",
        ).strip()

        database = os.getenv(
            "POSTGRES_DB",
            "",
        ).strip()

        user = os.getenv(
            "POSTGRES_USER",
            "",
        ).strip()

        password = os.getenv(
            "POSTGRES_PASSWORD",
            "",
        )

        missing_variables: list[str] = []

        if not database:
            missing_variables.append(
                "POSTGRES_DB"
            )

        if not user:
            missing_variables.append(
                "POSTGRES_USER"
            )

        if not password:
            missing_variables.append(
                "POSTGRES_PASSWORD"
            )

        if missing_variables:
            raise DimensionLoaderError(
                "Thiếu biến môi trường: "
                + ", ".join(
                    missing_variables
                )
            )

        try:
            port = int(
                port_text
            )

        except ValueError as error:
            raise DimensionLoaderError(
                "POSTGRES_PORT phải là số nguyên."
            ) from error

        return cls(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
        )

    def connect(
        self,
    ) -> psycopg.Connection[Any]:
        return psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
            connect_timeout=10,
        )


def normalize_boolean(
    value: Any,
) -> bool:
    if isinstance(
        value,
        bool,
    ):
        return value

    normalized_value = str(
        value
    ).strip().lower()

    true_values = {
        "true",
        "1",
        "yes",
        "y",
    }

    false_values = {
        "false",
        "0",
        "no",
        "n",
    }

    if normalized_value in true_values:
        return True

    if normalized_value in false_values:
        return False

    raise DimensionLoaderError(
        "Giá trị boolean không hợp lệ: "
        f"{value!r}"
    )


def check_required_columns(
    dataframe: pd.DataFrame,
    required_columns: set[str],
    file_name: str,
) -> None:
    actual_columns = set(
        dataframe.columns
    )

    missing_columns = (
        required_columns
        - actual_columns
    )

    if missing_columns:
        raise DimensionLoaderError(
            f"{file_name} thiếu các cột: "
            f"{sorted(missing_columns)}"
        )


def clean_required_text_columns(
    dataframe: pd.DataFrame,
    columns: list[str],
    file_name: str,
) -> pd.DataFrame:
    result = dataframe.copy()

    for column in columns:
        if result[column].isna().any():
            raise DimensionLoaderError(
                f"{file_name}: cột {column} "
                "có giá trị null."
            )

        result[column] = (
            result[column]
            .astype(str)
            .str.strip()
        )

        blank_count = int(
            result[column]
            .eq("")
            .sum()
        )

        if blank_count > 0:
            raise DimensionLoaderError(
                f"{file_name}: cột {column} "
                f"có {blank_count} giá trị rỗng."
            )

    return result


def prepare_locations(
    csv_path: str | Path,
) -> pd.DataFrame:
    path = Path(
        csv_path
    )

    if not path.exists():
        raise DimensionLoaderError(
            f"Không tìm thấy file: {path}"
        )

    dataframe = pd.read_csv(
        path,
        encoding="utf-8",
    )

    check_required_columns(
        dataframe=dataframe,
        required_columns=(
            LOCATION_REQUIRED_COLUMNS
        ),
        file_name=str(path),
    )

    dataframe = dataframe[
        [
            "location_id",
            "location_name",
            "region",
            "admin_type",
            "is_active",
        ]
    ].copy()

    dataframe = clean_required_text_columns(
        dataframe=dataframe,
        columns=[
            "location_id",
            "location_name",
            "region",
            "admin_type",
        ],
        file_name=str(path),
    )

    dataframe["location_id"] = (
        dataframe["location_id"]
        .str.upper()
    )

    duplicate_location_ids = int(
        dataframe["location_id"]
        .duplicated()
        .sum()
    )

    if duplicate_location_ids > 0:
        raise DimensionLoaderError(
            f"{path}: có "
            f"{duplicate_location_ids} "
            "location_id bị trùng."
        )

    duplicate_location_names = int(
        dataframe["location_name"]
        .duplicated()
        .sum()
    )

    if duplicate_location_names > 0:
        raise DimensionLoaderError(
            f"{path}: có "
            f"{duplicate_location_names} "
            "location_name bị trùng."
        )

    invalid_regions = sorted(
        set(
            dataframe["region"]
        )
        - VALID_REGIONS
    )

    if invalid_regions:
        raise DimensionLoaderError(
            f"{path}: region không hợp lệ: "
            f"{invalid_regions}"
        )

    invalid_admin_types = sorted(
        set(
            dataframe["admin_type"]
        )
        - VALID_ADMIN_TYPES
    )

    if invalid_admin_types:
        raise DimensionLoaderError(
            f"{path}: admin_type không hợp lệ: "
            f"{invalid_admin_types}"
        )

    dataframe["is_active"] = (
        dataframe["is_active"]
        .apply(
            normalize_boolean
        )
    )

    return dataframe


def prepare_monitoring_points(
    csv_path: str | Path,
    valid_location_ids: set[str],
) -> pd.DataFrame:
    path = Path(
        csv_path
    )

    if not path.exists():
        raise DimensionLoaderError(
            f"Không tìm thấy file: {path}"
        )

    dataframe = pd.read_csv(
        path,
        encoding="utf-8",
    )

    check_required_columns(
        dataframe=dataframe,
        required_columns=(
            MONITORING_POINT_REQUIRED_COLUMNS
        ),
        file_name=str(path),
    )

    dataframe = dataframe[
        [
            "point_id",
            "location_id",
            "point_name",
            "point_type",
            "latitude",
            "longitude",
            "is_active",
        ]
    ].copy()

    dataframe = clean_required_text_columns(
        dataframe=dataframe,
        columns=[
            "point_id",
            "location_id",
            "point_name",
            "point_type",
        ],
        file_name=str(path),
    )

    dataframe["point_id"] = (
        dataframe["point_id"]
        .str.upper()
    )

    dataframe["location_id"] = (
        dataframe["location_id"]
        .str.upper()
    )

    duplicate_point_ids = int(
        dataframe["point_id"]
        .duplicated()
        .sum()
    )

    if duplicate_point_ids > 0:
        raise DimensionLoaderError(
            f"{path}: có "
            f"{duplicate_point_ids} "
            "point_id bị trùng."
        )

    dataframe["latitude"] = (
        pd.to_numeric(
            dataframe["latitude"],
            errors="coerce",
        )
    )

    dataframe["longitude"] = (
        pd.to_numeric(
            dataframe["longitude"],
            errors="coerce",
        )
    )

    if dataframe[
        [
            "latitude",
            "longitude",
        ]
    ].isna().any().any():
        raise DimensionLoaderError(
            f"{path}: latitude hoặc longitude "
            "không phải số hợp lệ."
        )

    invalid_latitudes = dataframe[
        ~dataframe["latitude"].between(
            -90,
            90,
        )
    ]

    if not invalid_latitudes.empty:
        invalid_point_ids = (
            invalid_latitudes["point_id"]
            .tolist()
        )

        raise DimensionLoaderError(
            f"{path}: latitude không hợp lệ "
            f"tại các point: {invalid_point_ids}"
        )

    invalid_longitudes = dataframe[
        ~dataframe["longitude"].between(
            -180,
            180,
        )
    ]

    if not invalid_longitudes.empty:
        invalid_point_ids = (
            invalid_longitudes["point_id"]
            .tolist()
        )

        raise DimensionLoaderError(
            f"{path}: longitude không hợp lệ "
            f"tại các point: {invalid_point_ids}"
        )

    duplicate_coordinates = dataframe[
        dataframe.duplicated(
            subset=[
                "location_id",
                "latitude",
                "longitude",
            ],
            keep=False,
        )
    ]

    if not duplicate_coordinates.empty:
        duplicate_point_ids = (
            duplicate_coordinates["point_id"]
            .tolist()
        )

        raise DimensionLoaderError(
            f"{path}: các point bị trùng "
            "location và tọa độ: "
            f"{duplicate_point_ids}"
        )

    referenced_location_ids = set(
        dataframe["location_id"]
    )

    missing_location_ids = sorted(
        referenced_location_ids
        - valid_location_ids
    )

    if missing_location_ids:
        raise DimensionLoaderError(
            f"{path}: các location_id "
            "không tồn tại trong locations.csv: "
            f"{missing_location_ids}"
        )

    dataframe["is_active"] = (
        dataframe["is_active"]
        .apply(
            normalize_boolean
        )
    )

    return dataframe


def upsert_locations(
    connection: psycopg.Connection[Any],
    dataframe: pd.DataFrame,
) -> int:
    query = """
        INSERT INTO dim_location (
            location_id,
            location_name,
            region,
            admin_type,
            is_active
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s
        )
        ON CONFLICT (
            location_id
        )
        DO UPDATE SET
            location_name =
                EXCLUDED.location_name,
            region =
                EXCLUDED.region,
            admin_type =
                EXCLUDED.admin_type,
            is_active =
                EXCLUDED.is_active,
            updated_at =
                NOW()
    """

    rows = [
        (
            row.location_id,
            row.location_name,
            row.region,
            row.admin_type,
            bool(
                row.is_active
            ),
        )
        for row in dataframe.itertuples(
            index=False
        )
    ]

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            rows,
        )

    return len(
        rows
    )


def upsert_monitoring_points(
    connection: psycopg.Connection[Any],
    dataframe: pd.DataFrame,
) -> int:
    query = """
        INSERT INTO dim_monitoring_point (
            point_id,
            location_id,
            point_name,
            point_type,
            latitude,
            longitude,
            is_active
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        ON CONFLICT (
            point_id
        )
        DO UPDATE SET
            location_id =
                EXCLUDED.location_id,
            point_name =
                EXCLUDED.point_name,
            point_type =
                EXCLUDED.point_type,
            latitude =
                EXCLUDED.latitude,
            longitude =
                EXCLUDED.longitude,
            is_active =
                EXCLUDED.is_active,
            updated_at =
                NOW()
    """

    rows = [
        (
            row.point_id,
            row.location_id,
            row.point_name,
            row.point_type,
            float(
                row.latitude
            ),
            float(
                row.longitude
            ),
            bool(
                row.is_active
            ),
        )
        for row in dataframe.itertuples(
            index=False
        )
    ]

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            rows,
        )

    return len(
        rows
    )


def sync_dimensions(
    locations_csv_path: str | Path = (
        "configs/locations.csv"
    ),
    monitoring_points_csv_path: str | Path = (
        "configs/monitoring_points.csv"
    ),
) -> dict[str, Any]:
    locations = prepare_locations(
        locations_csv_path
    )

    valid_location_ids = set(
        locations["location_id"]
    )

    monitoring_points = (
        prepare_monitoring_points(
            csv_path=(
                monitoring_points_csv_path
            ),
            valid_location_ids=(
                valid_location_ids
            ),
        )
    )

    settings = (
        DatabaseSettings
        .from_environment()
    )

    with settings.connect() as connection:
        try:
            locations_upserted = (
                upsert_locations(
                    connection=connection,
                    dataframe=locations,
                )
            )

            monitoring_points_upserted = (
                upsert_monitoring_points(
                    connection=connection,
                    dataframe=monitoring_points,
                )
            )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

    return {
        "status": "SUCCESS",
        "locations_upserted": (
            locations_upserted
        ),
        "monitoring_points_upserted": (
            monitoring_points_upserted
        ),
    }