from __future__ import annotations

import json
from pathlib import Path

from scripts.check_runtime_inventory import (
    extract_dag_modules,
    extract_fastapi_routes,
    validate_runtime_inventory,
)
from src.operations.runtime_inventory import (
    ACTIVE_DAG_ENTRYPOINTS,
    MAINTENANCE_ENTRYPOINTS,
    RETIRED_COMPONENTS,
    RETIRED_MODULES,
    SNAPSHOT_REQUIRED_API_ROUTES,
    module_to_path,
    runtime_catalog,
)


def test_checked_in_runtime_catalog_matches_code() -> None:
    checked_in = json.loads(
        Path("contracts/runtime_components.v1.json").read_text(encoding="utf-8")
    )
    assert checked_in == runtime_catalog()


def test_dag_uses_only_active_entrypoints() -> None:
    dag_modules = extract_dag_modules(Path("dags/air_quality_pipeline_dag.py"))

    assert dag_modules == ACTIVE_DAG_ENTRYPOINTS
    assert not set(dag_modules).intersection(RETIRED_MODULES)


def test_retired_local_pipeline_files_are_absent() -> None:
    remaining_paths = [
        module_to_path(module)
        for module in RETIRED_MODULES
        if Path(module_to_path(module)).exists()
    ]

    assert remaining_paths == []
    assert len(RETIRED_COMPONENTS) == 13


def test_maintenance_entrypoints_still_exist() -> None:
    missing_paths = [
        module_to_path(module)
        for module in MAINTENANCE_ENTRYPOINTS
        if not Path(module_to_path(module)).is_file()
    ]

    assert missing_paths == []


def test_fastapi_is_read_only_and_supports_operational_snapshots() -> None:
    routes = extract_fastapi_routes(Path("api/main.py"))

    assert set(SNAPSHOT_REQUIRED_API_ROUTES).issubset(routes)
    assert all(methods.issubset({"get", "head"}) for methods in routes.values())


def test_runtime_inventory_has_no_errors() -> None:
    assert validate_runtime_inventory() == []
