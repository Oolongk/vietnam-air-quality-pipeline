from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys

from src.operations.runtime_inventory import (
    ACTIVE_DAG_ENTRYPOINTS,
    LEGACY_LOCAL_ENTRYPOINTS,
    SNAPSHOT_REQUIRED_API_ROUTES,
    module_to_path,
    runtime_catalog,
)

DEFAULT_CATALOG_PATH = Path("contracts/runtime_components.v1.json")


def serialize_catalog() -> str:
    return (
        json.dumps(
            runtime_catalog(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def extract_dag_modules(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "create_python_task"
        ):
            continue

        for keyword in node.keywords:
            if keyword.arg != "module_name":
                continue
            value = ast.literal_eval(keyword.value)
            modules.append(str(value))

    return tuple(modules)


def extract_fastapi_routes(
    path: Path,
) -> dict[str, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    routes: dict[str, set[str]] = {}

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue

        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "app"
            ):
                continue

            if not decorator.args:
                continue

            route = str(ast.literal_eval(decorator.args[0]))
            routes.setdefault(route, set()).add(decorator.func.attr.lower())

    return routes


def validate_runtime_inventory() -> list[str]:
    errors: list[str] = []

    dag_modules = extract_dag_modules(Path("dags/air_quality_pipeline_dag.py"))
    if dag_modules != ACTIVE_DAG_ENTRYPOINTS:
        errors.append("DAG entrypoints differ from runtime inventory.")

    legacy_in_dag = sorted(set(dag_modules).intersection(LEGACY_LOCAL_ENTRYPOINTS))
    if legacy_in_dag:
        errors.append(
            "Legacy entrypoints are referenced by the DAG: " + ", ".join(legacy_in_dag)
        )

    for module in (*ACTIVE_DAG_ENTRYPOINTS, *LEGACY_LOCAL_ENTRYPOINTS):
        path = Path(module_to_path(module))
        if not path.is_file():
            errors.append(f"Missing entrypoint file: {path}")

    routes = extract_fastapi_routes(Path("api/main.py"))
    required_routes = set(SNAPSHOT_REQUIRED_API_ROUTES)
    missing_routes = sorted(required_routes - set(routes))
    if missing_routes:
        errors.append(
            "FastAPI routes required by Snapshot Publisher are missing: "
            + ", ".join(missing_routes)
        )

    write_routes = sorted(
        f"{method.upper()} {route}"
        for route, methods in routes.items()
        for method in methods
        if method not in {"get", "head"}
    )
    if write_routes:
        errors.append("FastAPI must remain read-only: " + ", ".join(write_routes))

    compose_text = Path("docker-compose.yml").read_text(encoding="utf-8")
    if "127.0.0.1:${API_PORT:-8000}:8000" not in compose_text:
        errors.append("FastAPI is not bound to localhost in docker-compose.yml.")
    if "SNAPSHOT_API_BASE_URL: http://api:8000" not in compose_text:
        errors.append("Snapshot Publisher is not wired to the internal API service.")

    for module in LEGACY_LOCAL_ENTRYPOINTS:
        source = Path(module_to_path(module)).read_text(encoding="utf-8")
        if "require_legacy_local_pipeline_enabled" not in source:
            errors.append(f"Legacy guard missing from {module}.")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args()

    expected = serialize_catalog()

    if arguments.write:
        DEFAULT_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_CATALOG_PATH.write_text(expected, encoding="utf-8", newline="\n")
        print(f"Wrote runtime catalog: {DEFAULT_CATALOG_PATH}")
        return 0

    if not DEFAULT_CATALOG_PATH.exists():
        print(f"Missing runtime catalog: {DEFAULT_CATALOG_PATH}", file=sys.stderr)
        return 1

    actual = DEFAULT_CATALOG_PATH.read_text(encoding="utf-8")
    if actual != expected:
        print(
            "Runtime catalog is out of date. Run: "
            "python -m scripts.check_runtime_inventory --write",
            file=sys.stderr,
        )
        return 1

    errors = validate_runtime_inventory()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("FastAPI and runtime inventory checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
