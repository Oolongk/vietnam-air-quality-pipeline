from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from scripts.estimate_aws_snapshot_cost import load_cost_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "contracts" / "operations_documentation.v1.json"

DOCUMENTS: tuple[tuple[str, str], ...] = (
    ("docs/architecture.md", "architecture"),
    ("docs/operations_runbook.md", "runbook"),
    ("docs/aws_cost_management.md", "cost_management"),
    ("docs/adr/README.md", "adr_index"),
    ("docs/adr/0001-single-production-pipeline.md", "adr"),
    ("docs/adr/0002-deterministic-batch-context.md", "adr"),
    ("docs/adr/0003-minio-mart-serving.md", "adr"),
    ("docs/adr/0004-private-s3-immutable-releases.md", "adr"),
    ("docs/legacy_local_pipeline_retirement.md", "retirement"),
    ("docs/mart_serving_layer.md", "serving"),
    ("docs/continuous_integration.md", "ci"),
    ("infra/aws/s3/snapshot-release-lifecycle.json", "aws_policy"),
    ("configs/aws_cost_assumptions.json", "cost_config"),
)

REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "docs/operations_runbook.md": (
        "## 1. Mục đích và phạm vi",
        "## 4. Quy tắc an toàn",
        "## 7. Trigger và theo dõi DAG",
        "## 10. Playbook sự cố",
        "## 11. Backup và restore",
        "## 12. Release checklist",
    ),
    "docs/aws_cost_management.md": (
        "## 2. Cost drivers",
        "## 3. Đo workload thực tế",
        "## 5. Lifecycle bắt buộc cho immutable releases",
        "## 6. Budget và cảnh báo",
        "## 9. Cost review hằng tháng",
    ),
}

ADR_PATTERN = re.compile(r"^# ADR-(?P<number>\d{4}) — .+$", re.MULTILINE)
STATUS_PATTERN = re.compile(r"^- Status: (?P<status>[A-Za-z]+)$", re.MULTILINE)
DATE_PATTERN = re.compile(r"^- Date: \d{4}-\d{2}-\d{2}$", re.MULTILINE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_title(path: Path) -> str:
    if path.suffix.lower() != ".md":
        return path.name

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    raise ValueError(f"Markdown document has no H1 title: {path}")


def _adr_status(path: Path) -> str | None:
    if path.parent.name != "adr" or not path.name[:4].isdigit():
        return None
    text = path.read_text(encoding="utf-8")
    match = STATUS_PATTERN.search(text)
    return match.group("status") if match else None


def operations_catalog() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for relative_path, document_type in DOCUMENTS:
        path = PROJECT_ROOT / relative_path
        if not path.is_file():
            continue
        entry: dict[str, Any] = {
            "path": relative_path,
            "type": document_type,
            "title": _extract_title(path),
            "sha256": _sha256(path),
        }
        status = _adr_status(path)
        if status is not None:
            entry["status"] = status
        entries.append(entry)

    return {
        "schema_version": "1.0",
        "project": "vietnam-air-quality-pipeline",
        "catalog_owner": "operations-governance",
        "documents": entries,
    }


def serialize_catalog() -> str:
    return (
        json.dumps(
            operations_catalog(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _validate_lifecycle_policy(errors: list[str]) -> None:
    path = PROJECT_ROOT / "infra" / "aws" / "s3" / "snapshot-release-lifecycle.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"Cannot read lifecycle policy: {error}")
        return

    rules = payload.get("Rules") if isinstance(payload, dict) else None
    if not isinstance(rules, list) or len(rules) != 1:
        errors.append("Lifecycle policy must contain exactly one rule.")
        return

    rule = rules[0]
    if not isinstance(rule, dict):
        errors.append("Lifecycle rule must be an object.")
        return

    prefix = rule.get("Filter", {}).get("Prefix")
    if prefix != "releases/":
        errors.append("Lifecycle rule must target only the releases/ prefix.")

    expiration_days = rule.get("Expiration", {}).get("Days")
    if not isinstance(expiration_days, int) or expiration_days <= 0:
        errors.append("Lifecycle expiration Days must be a positive integer.")

    if "current.json" in json.dumps(rule):
        errors.append("Lifecycle policy must not target current.json.")


def validate_operations_documentation() -> list[str]:
    errors: list[str] = []

    for relative_path, _document_type in DOCUMENTS:
        path = PROJECT_ROOT / relative_path
        if not path.is_file():
            errors.append(f"Missing required operations document: {relative_path}")

    if errors:
        return errors

    for relative_path, required_sections in REQUIRED_SECTIONS.items():
        text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        for section in required_sections:
            if section not in text:
                errors.append(f"Missing section in {relative_path}: {section}")

    adr_paths = [
        PROJECT_ROOT / relative_path
        for relative_path, document_type in DOCUMENTS
        if document_type == "adr"
    ]
    expected_numbers = [f"{index:04d}" for index in range(1, len(adr_paths) + 1)]
    actual_numbers: list[str] = []

    for path in adr_paths:
        text = path.read_text(encoding="utf-8")
        title_match = ADR_PATTERN.search(text)
        if title_match is None:
            errors.append(f"ADR title is invalid: {path.relative_to(PROJECT_ROOT)}")
            continue

        actual_numbers.append(title_match.group("number"))
        status_match = STATUS_PATTERN.search(text)
        if status_match is None or status_match.group("status") != "Accepted":
            errors.append(
                f"ADR must have Status: Accepted: {path.relative_to(PROJECT_ROOT)}"
            )
        if DATE_PATTERN.search(text) is None:
            errors.append(
                f"ADR date is missing or invalid: {path.relative_to(PROJECT_ROOT)}"
            )

        for section in (
            "## Context",
            "## Decision",
            "## Consequences",
            "## Alternatives considered",
            "## Validation",
        ):
            if section not in text:
                errors.append(
                    f"ADR missing {section}: {path.relative_to(PROJECT_ROOT)}"
                )

    if actual_numbers != expected_numbers:
        errors.append(
            "ADR numbers must be contiguous and ordered. "
            f"Expected={expected_numbers}; actual={actual_numbers}."
        )

    try:
        load_cost_config(PROJECT_ROOT / "configs" / "aws_cost_assumptions.json")
    except ValueError as error:
        errors.append(f"AWS cost configuration is invalid: {error}")

    _validate_lifecycle_policy(errors)

    readme_text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    if "<!-- PART6_OPERATIONS_GOVERNANCE_BEGIN -->" not in readme_text:
        errors.append("README is missing the Part 6 operations governance block.")
    for link in (
        "docs/operations_runbook.md",
        "docs/adr/README.md",
        "docs/aws_cost_management.md",
    ):
        if link not in readme_text:
            errors.append(f"README does not link to {link}.")

    architecture_text = (PROJECT_ROOT / "docs" / "architecture.md").read_text(
        encoding="utf-8"
    )
    if "<!-- PART6_GOVERNANCE_ARCHITECTURE_BEGIN -->" not in architecture_text:
        errors.append("Architecture document is missing the Part 6 governance block.")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args()

    errors = validate_operations_documentation()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    expected = serialize_catalog()
    if arguments.write:
        CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CATALOG_PATH.write_text(expected, encoding="utf-8", newline="\n")
        print(f"Wrote operations documentation catalog: {CATALOG_PATH}")
        return 0

    if not CATALOG_PATH.is_file():
        print(f"Missing catalog: {CATALOG_PATH}", file=sys.stderr)
        return 1

    actual = CATALOG_PATH.read_text(encoding="utf-8")
    if actual != expected:
        print(
            "Operations documentation catalog is out of date. Run: "
            "python -m scripts.check_operations_documentation --write",
            file=sys.stderr,
        )
        return 1

    print("Operations documentation checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
