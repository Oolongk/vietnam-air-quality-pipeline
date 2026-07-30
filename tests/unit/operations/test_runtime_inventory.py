from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_runtime_inventory import (
    extract_dag_modules,
    extract_fastapi_routes,
    validate_runtime_inventory,
)
from src.operations.legacy_runtime import (
    require_legacy_local_pipeline_enabled,
)
from src.operations.runtime_inventory import (
    ACTIVE_DAG_ENTRYPOINTS,
    LEGACY_LOCAL_ENTRYPOINTS,
    SNAPSHOT_REQUIRED_API_ROUTES,
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
    assert not set(dag_modules).intersection(LEGACY_LOCAL_ENTRYPOINTS)


def test_fastapi_is_read_only_and_supports_snapshot_publisher() -> None:
    routes = extract_fastapi_routes(Path("api/main.py"))
    assert set(SNAPSHOT_REQUIRED_API_ROUTES).issubset(routes)
    assert all(methods.issubset({"get", "head"}) for methods in routes.values())


def test_runtime_inventory_has_no_errors() -> None:
    assert validate_runtime_inventory() == []


def test_legacy_guard_blocks_by_default(monkeypatch) -> None:
    monkeypatch.delenv(
        "ALLOW_LEGACY_LOCAL_PIPELINE",
        raising=False,
    )
    with pytest.raises(SystemExit) as error:
        require_legacy_local_pipeline_enabled("scripts.load_latest_clean_batch")
    assert error.value.code == 2


def test_legacy_guard_can_be_explicitly_enabled(monkeypatch) -> None:
    monkeypatch.setenv(
        "ALLOW_LEGACY_LOCAL_PIPELINE",
        "true",
    )
    require_legacy_local_pipeline_enabled("scripts.load_latest_clean_batch")
