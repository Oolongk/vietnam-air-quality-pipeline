from __future__ import annotations

import json

from scripts.check_operations_documentation import (
    CATALOG_PATH,
    PROJECT_ROOT,
    operations_catalog,
    validate_operations_documentation,
)


def test_operations_documentation_catalog_matches_code() -> None:
    checked_in = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert checked_in == operations_catalog()


def test_operations_documentation_has_no_validation_errors() -> None:
    assert validate_operations_documentation() == []


def test_lifecycle_policy_expires_only_release_prefix() -> None:
    path = PROJECT_ROOT / "infra" / "aws" / "s3" / "snapshot-release-lifecycle.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    rule = payload["Rules"][0]

    assert rule["Status"] == "Enabled"
    assert rule["Filter"]["Prefix"] == "releases/"
    assert rule["Expiration"]["Days"] == 30
    assert "current.json" not in json.dumps(rule)


def test_adr_index_references_all_accepted_adrs() -> None:
    index_text = (PROJECT_ROOT / "docs" / "adr" / "README.md").read_text(
        encoding="utf-8"
    )
    for number in range(1, 5):
        assert f"{number:04d}" in index_text
        adr_files = list((PROJECT_ROOT / "docs" / "adr").glob(f"{number:04d}-*.md"))
        assert len(adr_files) == 1
        assert "- Status: Accepted" in adr_files[0].read_text(encoding="utf-8")


def test_readme_links_operations_governance_documents() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/operations_runbook.md" in readme
    assert "docs/adr/README.md" in readme
    assert "docs/aws_cost_management.md" in readme
