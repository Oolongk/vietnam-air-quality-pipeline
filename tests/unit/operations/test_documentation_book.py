from __future__ import annotations

from scripts.build_unified_documentation import (
    DEFAULT_MANIFEST,
    PROJECT_ROOT,
    build_book,
    build_landing_page,
    check_outputs,
    load_manifest,
)
from scripts.check_documentation_book import (
    _check_generated_links,
    _check_manifest_coverage,
)


def test_manifest_has_unique_chapters() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST)
    chapter_ids = [chapter["id"] for chapter in manifest["chapters"]]
    sources = [chapter["source"] for chapter in manifest["chapters"]]

    assert len(chapter_ids) == len(set(chapter_ids))
    assert len(sources) == len(set(sources))


def test_manifest_sources_exist() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST)

    missing = [
        chapter["source"]
        for chapter in manifest["chapters"]
        if not (PROJECT_ROOT / chapter["source"]).is_file()
    ]

    assert missing == []


def test_book_contains_every_explicit_anchor() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST)
    book = build_book(manifest)

    for chapter in manifest["chapters"]:
        assert f'id="chapter-{chapter["id"]}"' in book


def test_landing_page_links_to_book() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST)
    landing = build_landing_page(manifest)

    assert "PROJECT_DOCUMENTATION.md" in landing
    assert "Mở toàn bộ tài liệu" in landing


def test_generated_outputs_are_current() -> None:
    assert check_outputs() == []


def test_manifest_covers_docs_inventory() -> None:
    assert _check_manifest_coverage() == []


def test_generated_links_are_valid() -> None:
    assert _check_generated_links() == []
