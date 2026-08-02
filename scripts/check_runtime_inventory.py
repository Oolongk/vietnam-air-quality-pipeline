from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys

from src.operations.runtime_inventory import (
    ACTIVE_DAG_ENTRYPOINTS,
    MAINTENANCE_ENTRYPOINTS,
    RETIRED_MODULES,
    SNAPSHOT_REQUIRED_API_ROUTES,
    module_to_path,
    runtime_catalog,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "contracts" / "runtime_components.v1.json"
PYTHON_SCAN_ROOTS: tuple[Path, ...] = tuple(
    PROJECT_ROOT / path
    for path in (
        "api",
        "dags",
        "dashboard",
        "scripts",
        "src",
        "tests",
    )
)


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
            modules.append(str(ast.literal_eval(keyword.value)))

    return tuple(modules)


def extract_fastapi_routes(path: Path) -> dict[str, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    routes: dict[str, set[str]] = {}

    for node in tree.body:
        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue

        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "app"
                and decorator.args
            ):
                continue

            route = str(ast.literal_eval(decorator.args[0]))
            routes.setdefault(route, set()).add(decorator.func.attr.lower())

    return routes


def extract_imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
            continue

        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
            imported_modules.update(
                f"{node.module}.{alias.name}"
                for alias in node.names
                if alias.name != "*"
            )

    return imported_modules


def iter_project_python_files() -> list[Path]:
    files: list[Path] = []

    for root in PYTHON_SCAN_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if any(
                part
                in {
                    "__pycache__",
                    ".venv",
                    ".git",
                }
                for part in path.parts
            ):
                continue
            files.append(path)

    return sorted(files)


def _imports_retired_module(
    imported: str,
    retired: str,
) -> bool:
    return imported == retired or imported.startswith(retired + ".")


def validate_runtime_inventory() -> list[str]:
    errors: list[str] = []

    dag_path = PROJECT_ROOT / "dags" / "air_quality_pipeline_dag.py"
    dag_modules = extract_dag_modules(dag_path)

    if dag_modules != ACTIVE_DAG_ENTRYPOINTS:
        errors.append("DAG entrypoints differ from runtime inventory.")

    for module in (
        *ACTIVE_DAG_ENTRYPOINTS,
        *MAINTENANCE_ENTRYPOINTS,
    ):
        path = PROJECT_ROOT / module_to_path(module)
        if not path.is_file():
            errors.append(f"Missing active or maintenance entrypoint file: {path}")

    for module in RETIRED_MODULES:
        path = PROJECT_ROOT / module_to_path(module)
        if path.exists():
            errors.append(f"Retired component still exists: {path}")

    for path in iter_project_python_files():
        try:
            imported_modules = extract_imported_modules(path)
        except (
            OSError,
            SyntaxError,
            UnicodeError,
        ) as error:
            errors.append(f"Cannot scan imports in {path}: {error}")
            continue

        forbidden = sorted(
            {
                retired
                for imported in imported_modules
                for retired in RETIRED_MODULES
                if _imports_retired_module(
                    imported,
                    retired,
                )
            }
        )

        if forbidden:
            errors.append(f"Retired module imported by {path}: " + ", ".join(forbidden))

    api_path = PROJECT_ROOT / "api" / "main.py"
    routes = extract_fastapi_routes(api_path)

    required_routes = set(SNAPSHOT_REQUIRED_API_ROUTES)
    missing_routes = sorted(required_routes - set(routes))

    if missing_routes:
        errors.append(
            "FastAPI routes required by Snapshot Publisher "
            "are missing: " + ", ".join(missing_routes)
        )

    write_routes = sorted(
        f"{method.upper()} {route}"
        for route, methods in routes.items()
        for method in methods
        if method
        not in {
            "get",
            "head",
        }
    )

    if write_routes:
        errors.append("FastAPI must remain read-only: " + ", ".join(write_routes))

    compose_path = PROJECT_ROOT / "docker-compose.yml"
    compose_text = compose_path.read_text(encoding="utf-8")

    if "127.0.0.1:${API_PORT:-8000}:8000" not in compose_text:
        errors.append("FastAPI is not bound to localhost in docker-compose.yml.")

    if "SNAPSHOT_API_BASE_URL: http://api:8000" not in compose_text:
        errors.append("Snapshot Publisher is not wired to the internal API service.")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
    )
    arguments = parser.parse_args()

    expected = serialize_catalog()

    if arguments.write:
        DEFAULT_CATALOG_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        DEFAULT_CATALOG_PATH.write_text(
            expected,
            encoding="utf-8",
            newline="\n",
        )
        print(f"Wrote runtime catalog: {DEFAULT_CATALOG_PATH}")
        return 0

    if not DEFAULT_CATALOG_PATH.exists():
        print(
            f"Missing runtime catalog: {DEFAULT_CATALOG_PATH}",
            file=sys.stderr,
        )
        return 1

    actual = DEFAULT_CATALOG_PATH.read_text(encoding="utf-8")

    if actual != expected:
        print(
            "Runtime catalog is out of date. Run: "
            "python -m scripts.check_runtime_inventory "
            "--write",
            file=sys.stderr,
        )
        return 1

    errors = validate_runtime_inventory()

    if errors:
        for error in errors:
            print(
                f"ERROR: {error}",
                file=sys.stderr,
            )
        return 1

    print("FastAPI and runtime inventory checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
