from __future__ import annotations

from pathlib import Path
import re
import sys

from scripts.build_unified_documentation import (
    DEFAULT_MANIFEST,
    PROJECT_ROOT,
    check_outputs,
    load_manifest,
)

LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)\s]+)")


def _is_external(target: str) -> bool:
    return target.startswith(
        (
            "#",
            "/",
            "http://",
            "https://",
            "mailto:",
            "data:",
        )
    )


def _check_manifest_coverage() -> list[str]:
    manifest = load_manifest(DEFAULT_MANIFEST)
    included = {
        Path(str(chapter["source"])).as_posix()
        for chapter in manifest["chapters"]
    }

    expected: set[str] = set()

    for path in (PROJECT_ROOT / "docs").glob("*.md"):
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if relative not in {
            "docs/README.md",
            "docs/PROJECT_DOCUMENTATION.md",
        }:
            expected.add(relative)

    for path in (PROJECT_ROOT / "docs" / "adr").glob("*.md"):
        expected.add(path.relative_to(PROJECT_ROOT).as_posix())

    screenshot_readme = (
        PROJECT_ROOT / "docs" / "screenshots" / "README.md"
    )
    if screenshot_readme.exists():
        expected.add(
            screenshot_readme.relative_to(PROJECT_ROOT).as_posix()
        )

    missing = sorted(expected - included)
    unexpected = sorted(included - expected)

    errors: list[str] = []
    if missing:
        errors.append(
            "Các source doc chưa được đưa vào book: "
            + ", ".join(missing)
        )
    if unexpected:
        errors.append(
            "Manifest trỏ tới source không thuộc docs inventory: "
            + ", ".join(unexpected)
        )

    return errors


def _check_generated_links() -> list[str]:
    manifest = load_manifest(DEFAULT_MANIFEST)
    generated_paths = [
        PROJECT_ROOT / str(manifest["output"]),
        PROJECT_ROOT / str(manifest["landing_page"]),
    ]
    errors: list[str] = []

    for document in generated_paths:
        if not document.exists():
            continue

        text = document.read_text(encoding="utf-8")

        for match in LINK_PATTERN.finditer(text):
            target = match.group("target")
            if _is_external(target):
                continue

            path_text = target.split("#", 1)[0].split("?", 1)[0]
            if not path_text:
                continue

            destination = (
                document.parent / path_text
            ).resolve(strict=False)

            if not destination.exists():
                errors.append(
                    f"Broken link trong "
                    f"{document.relative_to(PROJECT_ROOT)}: {target}"
                )

    return errors


def main() -> int:
    errors = [
        *check_outputs(),
        *_check_manifest_coverage(),
        *_check_generated_links(),
    ]

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("DOCUMENTATION BOOK CHECK SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
