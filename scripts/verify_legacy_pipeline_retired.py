from __future__ import annotations

import importlib.util

from scripts.check_runtime_inventory import (
    PROJECT_ROOT,
    extract_dag_modules,
    validate_runtime_inventory,
)
from src.operations.runtime_inventory import (
    ACTIVE_DAG_ENTRYPOINTS,
    MAINTENANCE_ENTRYPOINTS,
    RETIRED_MODULES,
    module_to_path,
)


def main() -> int:
    errors = validate_runtime_inventory()

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    dag_path = PROJECT_ROOT / "dags" / "air_quality_pipeline_dag.py"
    dag_modules = extract_dag_modules(dag_path)

    if dag_modules != ACTIVE_DAG_ENTRYPOINTS:
        print("ERROR: DAG entrypoint sequence differs from runtime inventory.")
        return 1

    unresolved_modules = [
        module
        for module in (
            *ACTIVE_DAG_ENTRYPOINTS,
            *MAINTENANCE_ENTRYPOINTS,
        )
        if importlib.util.find_spec(module) is None
    ]

    if unresolved_modules:
        print("ERROR: Active modules cannot be resolved:")
        for module in unresolved_modules:
            print(f"- {module}")
        return 1

    remaining_retired_paths = [
        module_to_path(module)
        for module in RETIRED_MODULES
        if (PROJECT_ROOT / module_to_path(module)).exists()
    ]

    if remaining_retired_paths:
        print("ERROR: Retired files still exist:")
        for path in remaining_retired_paths:
            print(f"- {path}")
        return 1

    print("LEGACY PIPELINE RETIREMENT VERIFY SUCCESS")
    print(f"Active DAG entrypoints: {len(ACTIVE_DAG_ENTRYPOINTS)}")
    print(f"Maintenance entrypoints: {len(MAINTENANCE_ENTRYPOINTS)}")
    print(f"Retired modules absent: {len(RETIRED_MODULES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
