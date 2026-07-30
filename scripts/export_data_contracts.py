from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from src.contracts import contract_catalog

DEFAULT_OUTPUT = Path("contracts/air_quality_contracts.v1.json")


def serialize_catalog() -> str:
    return (
        json.dumps(
            contract_catalog(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export or verify the checked-in air-quality data contract catalog."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--check",
        action="store_true",
    )
    arguments = parser.parse_args()

    expected = serialize_catalog()

    if arguments.check:
        if not arguments.output.exists():
            print(
                f"Contract catalog does not exist: {arguments.output}",
                file=sys.stderr,
            )
            return 1

        actual = arguments.output.read_text(encoding="utf-8")
        if actual != expected:
            print(
                "Contract catalog is out of date. "
                "Run: python -m scripts."
                "export_data_contracts",
                file=sys.stderr,
            )
            return 1

        print("Data contract catalog is current.")
        return 0

    arguments.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    arguments.output.write_text(
        expected,
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote data contract catalog: {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
