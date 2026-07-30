from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd
import pytest

from src.contracts.air_quality_contracts import (
    AQI_COLUMNS,
    CLEAN_HOURLY_CONTRACT,
    MART_CURRENT_AQI_COLUMNS,
    MART_DAILY_SUMMARY_COLUMNS,
    MART_LOCATION_SUMMARY_COLUMNS,
    MART_SOURCE_REQUIRED_COLUMNS,
    POLLUTANT_COLUMNS,
    SNAPSHOT_AIR_QUALITY_RECORD_CONTRACT,
    DataContractError,
    assert_raw_envelope,
    assert_snapshot_payload,
    contract_catalog,
)


def read_sequence_constants(
    source_path: Path,
) -> dict[str, tuple[str, ...]]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    constants: dict[str, tuple[str, ...]] = {}

    for node in tree.body:
        target_name: str | None = None
        value_node: ast.expr | None = None

        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(
                node.targets[0],
                ast.Name,
            )
        ):
            target_name = node.targets[0].id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(
            node.target,
            ast.Name,
        ):
            target_name = node.target.id
            value_node = node.value

        if (
            target_name is None
            or value_node is None
            or not isinstance(
                value_node,
                (
                    ast.List,
                    ast.Tuple,
                    ast.Set,
                ),
            )
        ):
            continue

        values: list[str] = []
        supported = True

        for element in value_node.elts:
            if isinstance(
                element,
                ast.Constant,
            ) and isinstance(
                element.value,
                str,
            ):
                values.append(element.value)
            elif (
                isinstance(
                    element,
                    ast.Starred,
                )
                and isinstance(
                    element.value,
                    ast.Name,
                )
                and element.value.id in constants
            ):
                values.extend(constants[element.value.id])
            else:
                supported = False
                break

        if supported:
            constants[target_name] = tuple(values)

    return constants


QUALITY_CONSTANTS = read_sequence_constants(Path("src/quality/data_quality_checks.py"))
MART_CONSTANTS = read_sequence_constants(
    Path("src/mart/minio_air_quality_mart_builder.py")
)


def build_clean_dataframe() -> pd.DataFrame:
    row = {
        "point_id": "NA_VINH_CENTER",
        "location_id": "NA",
        "point_name": "Trung tâm Vinh",
        "point_type": "urban_center",
        "latitude": 18.6796,
        "longitude": 105.6813,
        "forecast_time": pd.Timestamp("2026-07-29T20:00:00+07:00"),
        "source": "open_meteo",
        "batch_id": "20260729T120000Z_test",
        "schema_version": "1.0",
        "ingested_at": pd.Timestamp("2026-07-29T12:00:00Z"),
    }

    for column in POLLUTANT_COLUMNS:
        row[column] = 10.0

    for column in AQI_COLUMNS:
        row[column] = 20

    return pd.DataFrame(
        [row],
        columns=(CLEAN_HOURLY_CONTRACT.column_names),
    )


def build_snapshot_record() -> dict[str, object]:
    record = {
        "point_id": "HN_CENTER",
        "location_id": "HN",
        "point_name": "Trung tâm Hà Nội",
        "point_type": "urban_center",
        "location_name": "Hà Nội",
        "region": "Red River Delta",
        "admin_type": "municipality",
        "latitude": 21.0285,
        "longitude": 105.8542,
        "forecast_time": ("2026-07-29T20:00:00+07:00"),
        "source": "open_meteo",
        "batch_id": "20260729T120000Z_test",
        "schema_version": "1.0",
        "ingested_at": ("2026-07-29T12:00:00+00:00"),
    }

    for column in POLLUTANT_COLUMNS:
        record[column] = 10.0

    for column in AQI_COLUMNS:
        record[column] = 20

    return record


def build_raw_envelope() -> dict[str, object]:
    times = [
        "2026-07-29T20:00",
        "2026-07-29T21:00",
    ]
    hourly: dict[str, object] = {
        "time": times,
    }

    for column in POLLUTANT_COLUMNS:
        hourly[column] = [10.0, 11.0]

    for column in AQI_COLUMNS:
        hourly[column] = [20, 21]

    return {
        "schema_version": "1.0",
        "batch_id": "20260729T120000Z_test",
        "source": "open_meteo",
        "extracted_at": ("2026-07-29T12:00:00+00:00"),
        "point": {
            "point_id": "NA_VINH_CENTER",
            "location_id": "NA",
            "point_name": "Trung tâm Vinh",
            "point_type": "urban_center",
            "latitude": 18.6796,
            "longitude": 105.6813,
        },
        "api_response": {
            "schema_version": "1.0",
            "source": "open_meteo",
            "ingested_at": ("2026-07-29T12:00:00+00:00"),
            "request": {
                "point_id": "NA_VINH_CENTER",
                "location_id": "NA",
            },
            "response": {
                "hourly": hourly,
            },
        },
    }


def test_clean_contract_matches_quality_layer() -> None:
    assert set(CLEAN_HOURLY_CONTRACT.column_names) == set(
        QUALITY_CONSTANTS["REQUIRED_COLUMNS"]
    )

    assert (
        CLEAN_HOURLY_CONTRACT.key_columns == QUALITY_CONSTANTS["DUPLICATE_KEY_COLUMNS"]
    )


def test_mart_source_contract_matches_builder() -> None:
    assert set(MART_SOURCE_REQUIRED_COLUMNS) == set(MART_CONSTANTS["REQUIRED_COLUMNS"])


def test_declared_mart_column_order_is_unique() -> None:
    for columns in (
        MART_CURRENT_AQI_COLUMNS,
        MART_LOCATION_SUMMARY_COLUMNS,
        MART_DAILY_SUMMARY_COLUMNS,
    ):
        assert len(columns) == len(set(columns))


def test_clean_contract_accepts_na_location_id() -> None:
    dataframe = build_clean_dataframe()

    CLEAN_HOURLY_CONTRACT.assert_valid(dataframe)

    assert (
        dataframe.loc[
            0,
            "location_id",
        ]
        == "NA"
    )


def test_clean_contract_rejects_missing_column() -> None:
    dataframe = build_clean_dataframe().drop(columns=["pm2_5"])

    with pytest.raises(
        DataContractError,
        match="MISSING_COLUMNS",
    ):
        CLEAN_HOURLY_CONTRACT.assert_valid(dataframe)


def test_clean_contract_rejects_na_coercion() -> None:
    dataframe = build_clean_dataframe()
    dataframe.loc[
        0,
        "location_id",
    ] = pd.NA

    issues = CLEAN_HOURLY_CONTRACT.validate(dataframe)

    assert any(
        issue.field == "location_id" and issue.code == ("NULL_NOT_ALLOWED")
        for issue in issues
    )


def test_raw_envelope_contract() -> None:
    assert_raw_envelope(build_raw_envelope())


def test_snapshot_payload_contract() -> None:
    record = build_snapshot_record()

    SNAPSHOT_AIR_QUALITY_RECORD_CONTRACT.assert_valid(pd.DataFrame([record]))

    assert_snapshot_payload(
        {
            "status": "SUCCESS",
            "batch_id": ("20260729T120000Z_test"),
            "record_count": 1,
            "data": [record],
        }
    )


def test_snapshot_record_count_must_match() -> None:
    record = build_snapshot_record()

    with pytest.raises(
        DataContractError,
        match="SNAPSHOT_COUNT_MISMATCH",
    ):
        assert_snapshot_payload(
            {
                "status": "SUCCESS",
                "batch_id": ("20260729T120000Z_test"),
                "record_count": 2,
                "data": [record],
            }
        )


def test_checked_in_catalog_matches_code() -> None:
    catalog_path = Path("contracts/air_quality_contracts.v1.json")
    checked_in = json.loads(catalog_path.read_text(encoding="utf-8"))

    assert checked_in == contract_catalog()
